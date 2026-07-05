"""Image loading and validation utilities.

The Gemma vision call in the notebook passes a PIL.Image directly as part of
`contents=[image, prompt]`. We reproduce that here, adding validation so the
API rejects non-images and oversized files with clear errors.
"""
import io
from PIL import Image, UnidentifiedImageError

# Content types the frontend / API will accept.
ALLOWED_CONTENT_TYPES = {
    "image/jpeg",
    "image/jpg",
    "image/png",
    "image/webp",
    "image/bmp",
}

# 12 MB hard cap — protects the model call and stays well under API limits.
MAX_IMAGE_BYTES = 12 * 1024 * 1024

# Downscale very large images before sending to the model (faster, cheaper).
MAX_DIMENSION = 1600


class ImageValidationError(ValueError):
    """Raised when the uploaded file is missing, too large, or not an image."""


def validate_content_type(content_type: str | None) -> None:
    if content_type and content_type.lower() not in ALLOWED_CONTENT_TYPES:
        raise ImageValidationError(
            f"Unsupported file type '{content_type}'. "
            "Please upload a JPG, PNG, WEBP or BMP image."
        )


def load_image(data: bytes, content_type: str | None = None) -> Image.Image:
    """Validate and decode raw bytes into an RGB PIL image.

    Mirrors the notebook: Image.open(BytesIO(bytes)).convert("RGB").
    """
    if not data:
        raise ImageValidationError("No image provided. Please upload a crop image.")

    if len(data) > MAX_IMAGE_BYTES:
        raise ImageValidationError(
            f"Image is too large ({len(data) // (1024 * 1024)} MB). "
            f"Maximum allowed is {MAX_IMAGE_BYTES // (1024 * 1024)} MB."
        )

    validate_content_type(content_type)

    try:
        image = Image.open(io.BytesIO(data)).convert("RGB")
        image.load()  # force decode so truncated files fail here, not later
    except (UnidentifiedImageError, OSError):
        raise ImageValidationError(
            "The uploaded file is not a valid image or is corrupted."
        )

    # Downscale to keep the model call fast while preserving detail.
    if max(image.size) > MAX_DIMENSION:
        image.thumbnail((MAX_DIMENSION, MAX_DIMENSION))

    return image
