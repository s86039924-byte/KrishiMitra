"""Translation service — regional-language rendering of the final report.

Uses Gemma itself (multilingual) to translate the report fields. English is a
pass-through. Structure (string vs. list, item count) is preserved so the PDF
and UI can render translated reports identically to the English one.
"""
from typing import List

from models.schemas import FinalDiagnosis
from services import gemma_service
from services.prompt_service import SUPPORTED_LANGUAGES as _LANGS

SUPPORTED_LANGUAGES = set(_LANGS)

# Fields we translate; crop, confidence, severity and urgency are left as-is
# (severity/urgency stay canonical English so badge colouring keeps working).
_STRING_FIELDS = ["possible_disease", "reasoning", "disclaimer"]
_LIST_FIELDS = ["treatment", "prevention", "monitoring"]


def translate_report(report: FinalDiagnosis, language: str) -> FinalDiagnosis:
    """Return a new FinalDiagnosis with human-readable fields in `language`."""
    language = (language or "English").strip().title()
    if language == "English":
        return report

    if language not in SUPPORTED_LANGUAGES:
        raise ValueError(
            f"Unsupported language '{language}'. "
            f"Choose one of: {', '.join(sorted(SUPPORTED_LANGUAGES))}."
        )

    source = report.model_dump()
    translated = gemma_service.translate_fields(source, language)

    merged = dict(source)

    # Merge translated strings, keeping originals if a field is missing/blank.
    for field in _STRING_FIELDS:
        value = translated.get(field)
        if isinstance(value, str) and value.strip():
            merged[field] = value

    # Merge lists item-by-item; only accept when counts line up to avoid drift.
    for field in _LIST_FIELDS:
        value = translated.get(field)
        original: List[str] = source.get(field, []) or []
        if isinstance(value, list) and len(value) == len(original):
            merged[field] = [str(v) for v in value]

    return FinalDiagnosis(**merged)
