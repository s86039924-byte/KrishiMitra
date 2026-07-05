"""Thin HTTP client for the KrishiMitra AI backend."""
import os

import requests


def _resolve(key: str, default: str) -> str:
    """Resolve config from Streamlit secrets (cloud) first, then env, then default.

    Streamlit Community Cloud exposes values via st.secrets, NOT os.environ, so we
    check both. This lets the same code run locally (env / .env) and on the cloud.
    """
    try:
        import streamlit as st  # available in the frontend runtime

        if key in st.secrets:
            return str(st.secrets[key])
    except Exception:
        pass
    return os.getenv(key, default)


BACKEND_URL = _resolve("BACKEND_URL", "http://localhost:8000").rstrip("/")
TIMEOUT = int(_resolve("BACKEND_TIMEOUT", "120"))


class APIError(Exception):
    """Raised with a user-friendly message when a backend call fails."""

    def __init__(self, message: str, code: str = "error"):
        super().__init__(message)
        self.message = message
        self.code = code


def _extract_error(resp: requests.Response) -> APIError:
    try:
        detail = resp.json().get("detail")
        if isinstance(detail, dict):
            return APIError(detail.get("detail", "Request failed"), detail.get("code", "error"))
        if isinstance(detail, str):
            return APIError(detail)
    except Exception:
        pass
    return APIError(f"Request failed ({resp.status_code}).")


def health() -> dict:
    resp = requests.get(f"{BACKEND_URL}/health", timeout=10)
    resp.raise_for_status()
    return resp.json()


def analyze_image(
    image_bytes: bytes, filename: str, content_type: str, language: str = "English"
) -> dict:
    """POST /api/analyze-image → assessment + 3 follow-up questions."""
    files = {"file": (filename, image_bytes, content_type)}
    data = {"language": language}
    resp = requests.post(
        f"{BACKEND_URL}/api/analyze-image", files=files, data=data, timeout=TIMEOUT
    )
    if not resp.ok:
        raise _extract_error(resp)
    return resp.json()


def final_diagnosis(
    image_bytes: bytes,
    filename: str,
    content_type: str,
    analysis: dict,
    answers: list[dict],
    language: str = "English",
) -> dict:
    """POST /api/final-diagnosis → full report."""
    import json

    files = {"file": (filename, image_bytes, content_type)}
    data = {
        "analysis": json.dumps(analysis),
        "answers": json.dumps(answers),
        "language": language,
    }
    resp = requests.post(
        f"{BACKEND_URL}/api/final-diagnosis", files=files, data=data, timeout=TIMEOUT
    )
    if not resp.ok:
        raise _extract_error(resp)
    return resp.json()


def translate(report: dict, language: str) -> dict:
    """POST /api/translate → report in the requested language."""
    resp = requests.post(
        f"{BACKEND_URL}/api/translate",
        json={"report": report, "language": language},
        timeout=TIMEOUT,
    )
    if not resp.ok:
        raise _extract_error(resp)
    return resp.json()["report"]


def generate_pdf(report: dict, language: str = "English") -> bytes:
    """POST /api/generate-pdf → PDF bytes."""
    resp = requests.post(
        f"{BACKEND_URL}/api/generate-pdf",
        params={"language": language},
        json=report,
        timeout=TIMEOUT,
    )
    if not resp.ok:
        raise _extract_error(resp)
    return resp.content


