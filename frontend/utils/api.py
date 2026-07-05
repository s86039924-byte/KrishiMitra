"""Thin HTTP client for the KrishiMitra AI backend.

Resilient to Render free-tier cold starts: the backend spins down after ~15 min
idle, and the first request while it wakes returns 502/503/504 (or times out).
We transparently retry those transient failures with a short backoff so the user
just sees a slightly slower first request instead of an error.
"""
import json
import os
import time

import requests

# Gateway statuses that mean "backend waking / temporarily unavailable" — retry.
_TRANSIENT_STATUS = {502, 503, 504}
# Backoff (seconds) between retries — sized to cover a free-tier cold start.
_BACKOFF = [4, 10, 18]


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


def _request(method: str, path: str, *, retries: int = 3, timeout: int | None = None,
             **kwargs) -> requests.Response:
    """Send a request, retrying transient gateway errors and cold-start timeouts.

    Note: we pass request bodies as bytes/plain values (not file handles), so a
    retry safely re-sends the same payload.
    """
    url = f"{BACKEND_URL}{path}"
    timeout = timeout or TIMEOUT
    last_error: APIError | None = None

    for attempt in range(retries):
        try:
            resp = requests.request(method, url, timeout=timeout, **kwargs)
        except (requests.ConnectionError, requests.Timeout):
            last_error = APIError(
                "The backend is waking up (free hosting sleeps when idle). "
                "Please wait a moment and try again — the first request can take ~30–50s.",
                "backend_unreachable",
            )
        else:
            if resp.status_code not in _TRANSIENT_STATUS:
                return resp
            last_error = APIError(
                "The backend is starting up. Retrying automatically…", "backend_waking"
            )

        # Transient failure — back off and retry (unless this was the last try).
        if attempt < retries - 1:
            time.sleep(_BACKOFF[min(attempt, len(_BACKOFF) - 1)])

    raise last_error or APIError("Request failed after several retries.")


def health() -> dict:
    # Short timeout, no long retries — this runs on every rerun for the sidebar.
    resp = _request("GET", "/health", retries=1, timeout=8)
    resp.raise_for_status()
    return resp.json()


def analyze_image(
    image_bytes: bytes, filename: str, content_type: str, language: str = "English"
) -> dict:
    """POST /api/analyze-image → assessment + 3 follow-up questions."""
    files = {"file": (filename, image_bytes, content_type)}
    data = {"language": language}
    resp = _request("POST", "/api/analyze-image", files=files, data=data)
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
    files = {"file": (filename, image_bytes, content_type)}
    data = {
        "analysis": json.dumps(analysis),
        "answers": json.dumps(answers),
        "language": language,
    }
    resp = _request("POST", "/api/final-diagnosis", files=files, data=data)
    if not resp.ok:
        raise _extract_error(resp)
    return resp.json()


def translate(report: dict, language: str) -> dict:
    """POST /api/translate → report in the requested language."""
    resp = _request("POST", "/api/translate", json={"report": report, "language": language})
    if not resp.ok:
        raise _extract_error(resp)
    return resp.json()["report"]


def generate_pdf(report: dict, language: str = "English") -> bytes:
    """POST /api/generate-pdf → PDF bytes."""
    resp = _request("POST", "/api/generate-pdf", params={"language": language}, json=report)
    if not resp.ok:
        raise _extract_error(resp)
    return resp.content
