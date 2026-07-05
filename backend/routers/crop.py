"""API routes for the crop-diagnosis workflow."""
import json

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import ValidationError

from models.schemas import (
    AnalysisResult,
    FinalDiagnosis,
    QAPair,
    TranslateRequest,
    TranslatedReport,
)
from services import gemma_service, pdf_service, translation_service
from services.gemma_service import (
    GemmaConfigError,
    GemmaError,
    ModelTimeoutError,
    NoCropDetectedError,
    QuotaExceededError,
)
from utils.image_utils import ImageValidationError, load_image

router = APIRouter(prefix="/api", tags=["crop"])


def _handle_gemma_error(exc: Exception) -> HTTPException:
    """Map internal errors to HTTP responses with a stable `code`."""
    if isinstance(exc, ImageValidationError):
        return HTTPException(status_code=400, detail={"code": "invalid_image", "detail": str(exc)})
    if isinstance(exc, NoCropDetectedError):
        return HTTPException(status_code=422, detail={"code": "no_crop_detected", "detail": str(exc)})
    if isinstance(exc, QuotaExceededError):
        return HTTPException(status_code=429, detail={"code": "quota_exceeded", "detail": str(exc)})
    if isinstance(exc, ModelTimeoutError):
        return HTTPException(status_code=504, detail={"code": "model_timeout", "detail": str(exc)})
    if isinstance(exc, GemmaConfigError):
        return HTTPException(status_code=500, detail={"code": "config_error", "detail": str(exc)})
    if isinstance(exc, GemmaError):
        return HTTPException(status_code=502, detail={"code": "model_error", "detail": str(exc)})
    return HTTPException(status_code=500, detail={"code": "internal_error", "detail": str(exc)})


@router.post("/analyze-image", response_model=AnalysisResult)
async def analyze_image(
    file: UploadFile = File(...),
    language: str = Form("English", description="Response language, e.g. Hindi"),
):
    """Step 1: analyze a crop image and return assessment + 3 questions."""
    try:
        data = await file.read()
        image = load_image(data, file.content_type)
        return gemma_service.analyze_image(image, language)
    except Exception as exc:  # noqa: BLE001 - centralised mapping
        raise _handle_gemma_error(exc)


@router.post("/final-diagnosis", response_model=FinalDiagnosis)
async def final_diagnosis(
    file: UploadFile = File(...),
    analysis: str = Form(..., description="AnalysisResult as a JSON string"),
    answers: str = Form("[]", description="List of {question, answer} as JSON"),
    language: str = Form("English", description="Response language, e.g. Hindi"),
):
    """Step 3: combine image + prior analysis + answers into the final report."""
    try:
        analysis_obj = AnalysisResult(**json.loads(analysis))
        answers_obj = [QAPair(**a) for a in json.loads(answers)]
    except (json.JSONDecodeError, ValidationError, TypeError) as exc:
        raise HTTPException(
            status_code=400,
            detail={"code": "bad_request", "detail": f"Invalid analysis/answers payload: {exc}"},
        )

    try:
        data = await file.read()
        image = load_image(data, file.content_type)
        return gemma_service.final_diagnosis(image, analysis_obj, answers_obj, language)
    except Exception as exc:  # noqa: BLE001
        raise _handle_gemma_error(exc)


@router.post("/translate", response_model=TranslatedReport)
async def translate(req: TranslateRequest):
    """Translate a final report into English / Hindi / Bengali."""
    try:
        translated = translation_service.translate_report(req.report, req.language)
        return TranslatedReport(language=req.language, report=translated)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail={"code": "bad_language", "detail": str(exc)})
    except Exception as exc:  # noqa: BLE001
        raise _handle_gemma_error(exc)


@router.post("/generate-pdf")
async def generate_pdf(report: FinalDiagnosis, language: str = "English"):
    """Generate a downloadable PDF report."""
    try:
        pdf_bytes = pdf_service.generate_pdf(report, language=language)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=500,
            detail={"code": "pdf_error", "detail": f"Could not generate PDF: {exc}"},
        )

    filename = f"KrishiMitra_Report_{report.crop.replace(' ', '_')}.pdf"
    return StreamingResponse(
        iter([pdf_bytes]),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
