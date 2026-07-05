"""Prompt templates for KrishiMitra AI.

All prompts share the same guardrails, grounded in the notebook's working
vision prompt and extended for the multi-step reasoning workflow:
  - Always return ONLY valid JSON (no markdown, no prose).
  - Never guarantee a diagnosis — phrase as "possible" / "likely" / "AI-assisted".
  - Never invent details that are not visible or provided.
"""
import json
from typing import List

from models.schemas import AnalysisResult, QAPair

# Shared framing prepended to reasoning prompts.
_PERSONA = "You are an expert agricultural scientist and plant pathologist."

_JSON_RULES = (
    "Return ONLY a single valid JSON object. "
    "Do not include markdown, code fences, comments, or any text outside the JSON."
)

# Languages the app can respond in (kept in sync with the frontend selector).
SUPPORTED_LANGUAGES = [
    "English", "Hindi", "Bengali", "Marathi", "Telugu", "Tamil", "Gujarati",
    "Kannada", "Malayalam", "Punjabi", "Odia", "Urdu", "Assamese",
]


def _language_directive(language: str, fields: list[str]) -> str:
    """Instruction block that makes Gemma write user-facing values in `language`
    while keeping JSON keys and logic-critical enums in English."""
    if not language or language.strip().lower() == "english":
        return ""
    field_list = ", ".join(fields)
    return f"""

LANGUAGE INSTRUCTIONS (very important):
- Write the VALUES of these fields in {language}: {field_list}.
- Keep ALL JSON keys in English exactly as in the schema.
- Keep "severity" strictly as one of: Low, Medium, High (in ENGLISH).
- Keep "urgency" strictly as one of: Routine, Soon, Immediate (in ENGLISH).
- Keep "confidence" as a percentage such as "82%".
- If no crop/plant is visible, keep "crop" as "None" (in ENGLISH).
- Use simple, everyday {language} that an ordinary farmer can understand.
- Use the {language} script (not transliteration), except for technical
  chemical / active-ingredient names which may stay in their standard form.
"""


def vision_prompt(language: str = "English") -> str:
    """Step 1 — analyze the crop image. Matches the notebook schema."""
    base = f"""{_PERSONA}

Analyze the uploaded image carefully. FIRST decide whether the image actually
shows a plant / crop / leaf / fruit / stem / farm field. Many uploads may be
unrelated — a person, animal, vehicle, document, screenshot, food dish, or a
random object. Be honest: do NOT invent a crop that is not there.

{_JSON_RULES}

Schema:
{{
  "is_crop_image": true,
  "crop": "",
  "possible_disease": "",
  "confidence": "",
  "visible_symptoms": [],
  "severity": "",
  "reasoning": "",
  "followup_questions": ["", "", ""]
}}

Rules:
- "is_crop_image": boolean true/false. Set to FALSE if the image does not clearly
  show a plant, crop, leaf, fruit, stem, or farm field. If false, set "crop" to
  "None", leave the other fields empty/[], and briefly say in "reasoning" what the
  image appears to show instead.
- "crop": common name of the crop. If no crop/plant is visible, set to "None".
- "possible_disease": the most likely issue. Always phrase it as a POSSIBILITY.
  If the cause is not a pathogen, describe it (e.g. "Abiotic / Physical Damage").
- "confidence": a percentage string like "82%". Be honest and calibrated.
- "visible_symptoms": short bullet phrases of what is actually visible.
- "severity": exactly one of "Low", "Medium", "High".
- "reasoning": explain WHY, referencing the visible evidence. Never guarantee.
- "followup_questions": EXACTLY 3 questions tailored to THIS crop and THIS issue
  that would help confirm the diagnosis (probe timing, weather, spread, recent
  inputs). Never generic or fixed. If is_crop_image is false, use an empty list.
"""
    return base + _language_directive(
        language,
        ["crop", "possible_disease", "visible_symptoms", "reasoning",
         "followup_questions"],
    )


def followup_prompt(analysis: AnalysisResult, language: str = "English") -> str:
    """Step 2 — generate exactly 3 disease-specific follow-up questions."""
    symptoms = ", ".join(analysis.visible_symptoms) or "not specified"
    base = f"""{_PERSONA}

Context from the image analysis:
- Crop: {analysis.crop}
- Possible issue: {analysis.possible_disease}
- Severity: {analysis.severity}
- Visible symptoms: {symptoms}

Generate EXACTLY 3 follow-up questions that would most help confirm or refine
this specific assessment. The questions MUST be tailored to THIS crop and THIS
possible issue — never generic or fixed. Good questions probe timing, weather,
spread pattern, recent inputs, or field conditions relevant to this issue.

{_JSON_RULES}

Schema:
{{
  "questions": ["", "", ""]
}}
"""
    return base + _language_directive(language, ["questions"])


def final_diagnosis_prompt(
    analysis: AnalysisResult, answers: List[QAPair], language: str = "English"
) -> str:
    """Step 3 — combine image + prior reasoning + answers into a full report."""
    prior = analysis.model_dump()
    qa_block = "\n".join(
        f"- Q: {qa.question}\n  A: {qa.answer or '(no answer)'}" for qa in answers
    ) or "- (no answers provided)"

    base = f"""{_PERSONA}

You previously analyzed a crop image and produced this assessment:
{json.dumps(prior, ensure_ascii=False, indent=2)}

The farmer answered your follow-up questions:
{qa_block}

Now look at the image AGAIN together with these answers and produce a FINAL,
actionable, farmer-friendly report. Update your confidence and severity if the
answers change your assessment. Keep every recommendation practical and safe.

{_JSON_RULES}

Schema:
{{
  "crop": "",
  "possible_disease": "",
  "confidence": "",
  "severity": "",
  "urgency": "",
  "reasoning": "",
  "treatment": [],
  "prevention": [],
  "monitoring": [],
  "disclaimer": ""
}}

Rules:
- "possible_disease": still phrased as a POSSIBILITY (e.g. "Likely ...").
- "confidence": percentage string, updated using the farmer's answers.
- "severity": one of "Low", "Medium", "High".
- "urgency": one of "Routine", "Soon", "Immediate".
- "treatment": 3-5 concrete steps. Prefer safe, low-cost, locally available
  options first. If chemicals are suggested, name the active ingredient and
  advise following label rates.
- "prevention": 3-5 steps to avoid recurrence next season.
- "monitoring": 2-4 things the farmer should watch for over the coming days.
- "disclaimer": one sentence stating this is an AI-assisted assessment and a
  local expert should confirm before chemical treatment.
- Never guarantee a cure or a definite diagnosis.
"""
    return base + _language_directive(
        language,
        ["possible_disease", "reasoning", "treatment", "prevention",
         "monitoring", "disclaimer"],
    )


# Human-readable field labels used when translating a report.
# NOTE: severity/urgency are intentionally excluded — they stay canonical English
# ("Low/Medium/High", "Routine/Soon/Immediate") so badge colouring stays correct.
_TRANSLATABLE_FIELDS = [
    "possible_disease",
    "reasoning",
    "treatment",
    "prevention",
    "monitoring",
    "disclaimer",
]


def translation_prompt(report: dict, language: str) -> str:
    """Translate the human-readable fields of a report into `language`.

    We keep 'crop' and 'confidence' untranslated (proper noun / number) and ask
    for a JSON object preserving list vs. string structure.
    """
    payload = {k: report.get(k) for k in _TRANSLATABLE_FIELDS}
    return f"""You are a professional agricultural translator.

Translate the VALUES in the following JSON into {language}. Keep the JSON keys
and structure exactly the same (strings stay strings, lists stay lists with the
same number of items). Use simple, clear language a farmer can understand. Do
not add or remove information. Keep any chemical/active-ingredient names in
their standard form.

{_JSON_RULES}

JSON to translate:
{json.dumps(payload, ensure_ascii=False, indent=2)}
"""
