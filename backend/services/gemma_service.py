"""Gemma 4 wrapper — the reasoning engine.

Grounded in the Kaggle notebook:
    from google import genai
    client = genai.Client(api_key=GOOGLE_API_KEY)
    client.models.generate_content(
        model="models/gemma-4-31b-it",
        contents=[image, prompt],   # PIL image + text
    )

Design notes:
  - Gemma (unlike Gemini) does NOT support system_instruction / response_schema,
    so we prompt for JSON and parse defensively via json_utils.extract_json.
  - Every JSON call retries with a stricter reminder if parsing fails.
  - API errors are classified into friendly exceptions for the router layer.
"""
from __future__ import annotations

import os
import time
from typing import List

from dotenv import load_dotenv
from google import genai
from PIL import Image

from models.schemas import AnalysisResult, FinalDiagnosis, QAPair
from services import prompt_service
from utils.json_utils import ModelJSONError, extract_json

load_dotenv()

PRIMARY_MODEL = os.getenv("GEMMA_MODEL", "models/gemma-4-31b-it")
FALLBACK_MODEL = os.getenv("GEMMA_FALLBACK_MODEL", "models/gemma-4-26b-a4b-it")
MAX_JSON_RETRIES = int(os.getenv("GEMMA_MAX_RETRIES", "2"))


# --------------------------------------------------------------------------- #
# Exceptions (mapped to HTTP status codes in the router)
# --------------------------------------------------------------------------- #
class GemmaError(Exception):
    """Base class for Gemma-layer failures."""


class GemmaConfigError(GemmaError):
    """API key missing or client cannot be created."""


class QuotaExceededError(GemmaError):
    """The Google GenAI quota/rate limit was hit (HTTP 429)."""


class ModelTimeoutError(GemmaError):
    """The model call timed out or the service was unavailable."""


class NoCropDetectedError(GemmaError):
    """No crop/plant could be identified in the image."""


# --------------------------------------------------------------------------- #
# Client
# --------------------------------------------------------------------------- #
_client: genai.Client | None = None


def get_client() -> genai.Client:
    global _client
    if _client is None:
        api_key = os.getenv("GOOGLE_API_KEY")
        if not api_key:
            raise GemmaConfigError(
                "GOOGLE_API_KEY is not set. Add it to backend/.env "
                "(see .env.example)."
            )
        _client = genai.Client(api_key=api_key)
    return _client


def is_api_key_configured() -> bool:
    return bool(os.getenv("GOOGLE_API_KEY"))


def _classify_api_error(exc: Exception) -> GemmaError:
    """Turn a raw SDK/network error into a friendly, typed error."""
    text = str(exc).lower()
    if any(s in text for s in ("429", "resource_exhausted", "quota", "rate limit")):
        return QuotaExceededError(
            "The AI service quota has been exceeded. Please wait a moment and "
            "try again."
        )
    if any(s in text for s in ("deadline", "timeout", "timed out", "503", "unavailable")):
        return ModelTimeoutError(
            "The AI service took too long to respond. Please try again."
        )
    return GemmaError(f"AI service error: {exc}")


# --------------------------------------------------------------------------- #
# Low-level generation
# --------------------------------------------------------------------------- #
def _generate_text(contents: list) -> str:
    """Single generate_content call with primary->fallback model handling."""
    client = get_client()
    try:
        resp = client.models.generate_content(model=PRIMARY_MODEL, contents=contents)
        return resp.text or ""
    except Exception as primary_exc:  # noqa: BLE001 - we re-classify below
        classified = _classify_api_error(primary_exc)
        # For transient/quota issues, try the lighter fallback model once.
        if isinstance(classified, (QuotaExceededError, ModelTimeoutError)):
            try:
                resp = client.models.generate_content(
                    model=FALLBACK_MODEL, contents=contents
                )
                return resp.text or ""
            except Exception:  # noqa: BLE001
                raise classified from primary_exc
        raise classified from primary_exc


def _generate_json(contents: list) -> dict:
    """Generate and parse a JSON object, retrying with a stricter reminder."""
    reminder = (
        "\n\nREMINDER: Output ONLY the raw JSON object. "
        "No markdown, no code fences, no commentary."
    )
    attempt_contents = list(contents)
    last_err: Exception | None = None

    for attempt in range(MAX_JSON_RETRIES + 1):
        text = _generate_text(attempt_contents)
        try:
            return extract_json(text)
        except ModelJSONError as exc:
            last_err = exc
            # Strengthen the instruction and retry.
            attempt_contents = list(contents) + [reminder]
            time.sleep(0.4 * (attempt + 1))

    raise GemmaError(
        f"The AI returned an invalid response after {MAX_JSON_RETRIES + 1} "
        f"attempts. {last_err}"
    )


# --------------------------------------------------------------------------- #
# High-level workflow steps
# --------------------------------------------------------------------------- #
def analyze_image(image: Image.Image, language: str = "English") -> AnalysisResult:
    """Step 1 + 2: vision analysis, then 3 dynamic follow-up questions."""
    # --- Vision pass ---
    analysis_raw = _generate_json([image, prompt_service.vision_prompt(language)])

    # Reject non-crop images. Prefer the explicit boolean the model must set
    # (language-independent); fall back to the crop-name string for safety.
    crop = str(analysis_raw.get("crop", "")).strip()
    is_crop = _as_bool(analysis_raw.get("is_crop_image", True))
    if not is_crop or not crop or crop.lower() in {"none", "n/a", "unknown", ""}:
        hint = str(analysis_raw.get("reasoning", "")).strip()
        message = (
            "This image doesn't appear to show a crop or plant. Please upload a "
            "clear photo of the affected leaf, fruit, stem, or plant."
        )
        if hint:
            message += f" (The image looks like: {hint})"
        raise NoCropDetectedError(message)

    analysis = AnalysisResult(
        crop=crop,
        possible_disease=str(analysis_raw.get("possible_disease", "Undetermined")),
        confidence=str(analysis_raw.get("confidence", "N/A")),
        severity=str(analysis_raw.get("severity", "Medium")),
        visible_symptoms=list(analysis_raw.get("visible_symptoms", []) or []),
        reasoning=str(analysis_raw.get("reasoning", "")),
        followup_questions=[],
    )

    # Questions come from the SAME vision call (already in `language`), so they
    # never mismatch the analysis language and we avoid a second, rate-limit-prone
    # request. Only fall back if the model didn't return 3 usable questions.
    questions = [
        str(q) for q in (analysis_raw.get("followup_questions", []) or []) if str(q).strip()
    ]

    if len(questions) < 3:
        try:
            followups_raw = _generate_json(
                [prompt_service.followup_prompt(analysis, language)]
            )
            extra = [str(q) for q in followups_raw.get("questions", []) if str(q).strip()]
            questions = questions + [q for q in extra if q not in questions]
        except GemmaError:
            pass  # non-fatal; localized defaults below keep the flow working

    if len(questions) < 3:
        questions = (questions + _default_questions(analysis, language))[:3]

    analysis.followup_questions = questions[:3]
    return analysis


def final_diagnosis(
    image: Image.Image,
    analysis: AnalysisResult,
    answers: List[QAPair],
    language: str = "English",
) -> FinalDiagnosis:
    """Step 3: combine image + prior analysis + answers into the final report."""
    prompt = prompt_service.final_diagnosis_prompt(analysis, answers, language)
    raw = _generate_json([image, prompt])

    default_disclaimer = (
        "This is an AI-assisted assessment, not a guaranteed diagnosis. "
        "Please confirm with a local agricultural expert before applying any "
        "chemical treatment."
    )

    return FinalDiagnosis(
        crop=str(raw.get("crop", analysis.crop)),
        possible_disease=str(raw.get("possible_disease", analysis.possible_disease)),
        confidence=str(raw.get("confidence", analysis.confidence)),
        severity=str(raw.get("severity", analysis.severity)),
        urgency=str(raw.get("urgency", "Soon")),
        reasoning=str(raw.get("reasoning", analysis.reasoning)),
        treatment=[str(x) for x in (raw.get("treatment", []) or [])],
        prevention=[str(x) for x in (raw.get("prevention", []) or [])],
        monitoring=[str(x) for x in (raw.get("monitoring", []) or [])],
        disclaimer=str(raw.get("disclaimer") or default_disclaimer),
    )


def translate_fields(report: dict, language: str) -> dict:
    """Translate the human-readable report fields into `language`.

    Returns a dict of {field: translated_value}. Used by translation_service.
    English is a no-op handled by the caller.
    """
    prompt = prompt_service.translation_prompt(report, language)
    return _generate_json([prompt])


def _as_bool(value, default: bool = True) -> bool:
    """Coerce a model-provided flag (bool, or "true"/"false" string) to bool."""
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() not in {"false", "no", "0", "none", ""}
    if value is None:
        return default
    return bool(value)


def _default_questions(analysis: AnalysisResult, language: str = "English") -> List[str]:
    """Safe, context-aware fallbacks if the model's question pass fails.

    Localized best-effort: when a non-English language is requested we translate
    the defaults in one call so the farmer never sees stray English; if even that
    fails we return the English versions rather than nothing.
    """
    issue = analysis.possible_disease
    english = [
        f"How many days ago did you first notice the {issue} symptoms?",
        "Has there been unusual rainfall, heat, or wind in your area recently?",
        "Are neighbouring plants of the same crop also showing these symptoms?",
    ]
    if not language or language.strip().lower() == "english":
        return english

    try:
        prompt = (
            f"Translate these 3 short farmer questions into {language}. "
            "Keep them natural and simple. Return ONLY JSON: "
            '{"questions": ["...", "...", "..."]}.\n\n' + "\n".join(english)
        )
        data = _generate_json([prompt])
        localized = [str(q) for q in data.get("questions", []) if str(q).strip()]
        if len(localized) == 3:
            return localized
    except GemmaError:
        pass
    return english
