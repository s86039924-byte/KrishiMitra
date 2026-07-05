"""KrishiMitra AI — FastAPI application entrypoint.

Run:
    cd backend
    uvicorn app:app --reload --port 8000

Docs at http://localhost:8000/docs
"""
import os

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from models.schemas import HealthResponse
from routers import crop
from services import gemma_service

load_dotenv()

app = FastAPI(
    title="KrishiMitra AI",
    description=(
        "AI-powered multilingual crop disease assistant powered by Gemma 4. "
        "Built for the Build with Gemma Hackathon."
    ),
    version="1.0.0",
)

# Allow the Streamlit frontend (and local dev) to call the API.
_origins = os.getenv("CORS_ORIGINS", "*").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in _origins],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(crop.router)


@app.get("/", tags=["health"])
async def root():
    return {"service": "KrishiMitra AI", "docs": "/docs", "health": "/health"}


@app.get("/health", response_model=HealthResponse, tags=["health"])
async def health():
    return HealthResponse(
        status="ok",
        model=gemma_service.PRIMARY_MODEL,
        api_key_configured=gemma_service.is_api_key_configured(),
    )
