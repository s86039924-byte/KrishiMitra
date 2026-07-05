"""Pydantic schemas — the JSON contracts for every KrishiMitra AI endpoint.

These models are the single source of truth for request/response shapes.
The Gemma layer is prompted to return JSON matching these fields; we validate
against these models so the API never leaks malformed model output.
"""
from typing import List
from pydantic import BaseModel, Field


class AnalysisResult(BaseModel):
    """Response of POST /analyze-image (vision pass + follow-up questions)."""
    crop: str = Field(..., description="Detected crop, e.g. 'Maize (Corn)'")
    possible_disease: str = Field(..., description="Possible disease OR abiotic damage")
    confidence: str = Field(..., description="Confidence as a percentage string, e.g. '85%'")
    severity: str = Field(..., description="Low | Medium | High")
    visible_symptoms: List[str] = Field(default_factory=list)
    reasoning: str = Field(..., description="Why the model reached this assessment")
    followup_questions: List[str] = Field(
        default_factory=list,
        description="Exactly 3 disease-specific questions",
    )


class QAPair(BaseModel):
    """A single follow-up question and the farmer's answer."""
    question: str
    answer: str


class FinalDiagnosisRequest(BaseModel):
    """Body used when the frontend already holds the analysis + answers as JSON.

    Note: the /final-diagnosis endpoint accepts multipart form fields
    (image + analysis + answers) so the image can be re-sent. This model
    documents the JSON shape of the `analysis` and `answers` form fields.
    """
    analysis: AnalysisResult
    answers: List[QAPair] = Field(default_factory=list)


class FinalDiagnosis(BaseModel):
    """Response of POST /final-diagnosis — the complete farmer report."""
    crop: str
    possible_disease: str
    confidence: str
    severity: str
    urgency: str = Field(..., description="Routine | Soon | Immediate")
    reasoning: str
    treatment: List[str] = Field(default_factory=list)
    prevention: List[str] = Field(default_factory=list)
    monitoring: List[str] = Field(default_factory=list)
    disclaimer: str = Field(
        default=(
            "This is an AI-assisted assessment, not a guaranteed diagnosis. "
            "Please confirm with a local agricultural expert before applying "
            "any chemical treatment."
        )
    )


class TranslateRequest(BaseModel):
    """Body of POST /translate."""
    report: FinalDiagnosis
    language: str = Field(..., description="English | Hindi | Bengali")


class TranslatedReport(BaseModel):
    """Response of POST /translate."""
    language: str
    report: FinalDiagnosis


class HealthResponse(BaseModel):
    status: str
    model: str
    api_key_configured: bool


class ErrorResponse(BaseModel):
    detail: str
    code: str
