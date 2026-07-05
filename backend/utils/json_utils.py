"""Defensive JSON extraction for Gemma responses.

IMPORTANT (grounded in the Kaggle notebook): Gemma models on the Google GenAI
API do NOT support Gemini-only structured-output features
(`system_instruction`, `response_mime_type`, `response_schema`). They return
JSON wrapped in ```json ... ``` fences, sometimes with leading/trailing prose.

So we never rely on a JSON mode — we prompt for JSON and parse defensively:
strip code fences, slice from the first '{' to the last '}', then json.loads.
"""
import json
import re


class ModelJSONError(ValueError):
    """Raised when the model output cannot be parsed into JSON."""


_FENCE_RE = re.compile(r"```(?:json)?", re.IGNORECASE)


def extract_json(text: str) -> dict:
    """Parse a JSON object out of a raw model response.

    Handles:
      - ```json ... ``` fenced blocks (as seen in the notebook)
      - stray prose before/after the object
      - single trailing commas (a common model slip)
    """
    if not text or not text.strip():
        raise ModelJSONError("The model returned an empty response.")

    cleaned = _FENCE_RE.sub("", text).strip().strip("`").strip()

    # Slice to the outermost JSON object.
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ModelJSONError(f"No JSON object found in model output:\n{text[:400]}")

    candidate = cleaned[start : end + 1]

    try:
        return json.loads(candidate)
    except json.JSONDecodeError:
        # Second chance: remove trailing commas like {"a": 1,} or [1, 2,]
        repaired = re.sub(r",(\s*[}\]])", r"\1", candidate)
        try:
            return json.loads(repaired)
        except json.JSONDecodeError as exc:
            raise ModelJSONError(
                f"Could not parse JSON from model output: {exc}\n{candidate[:400]}"
            ) from exc
