# 🌾 KrishiMitra AI

**AI-Powered Multilingual Crop Disease Assistant — powered by Gemma 4**
_Build with Gemma Hackathon · Track: GenAI for Good_

KrishiMitra AI helps farmers identify possible crop problems from a single
photo. Unlike a traditional image classifier, it uses **Gemma 4's multimodal
vision + step-by-step reasoning**: it looks at the image, asks 3 *issue-specific*
follow-up questions, then combines the image and the answers into a final,
actionable report — with treatment, prevention, monitoring, urgency, a
disclaimer, regional-language translation (English / Hindi / Bengali), and a
downloadable PDF.

---

## Architecture

```
┌────────────┐        HTTP         ┌──────────────────────────┐
│  Streamlit │ ─────────────────▶  │  FastAPI backend         │
│  frontend  │ ◀─────────────────  │  ├─ gemma_service (Gemma)│
└────────────┘   JSON / PDF        │  ├─ prompt_service       │
                                    │  ├─ translation_service  │
                                    │  └─ pdf_service          │
                                    └──────────────┬───────────┘
                                                   │ google-genai
                                                   ▼
                                         models/gemma-4-31b-it
```

**Workflow:** Upload image → Gemma vision → disease/abiotic detection →
3 dynamic follow-up questions → user answers → Gemma contextual reasoning →
final diagnosis → treatment / prevention / monitoring / urgency →
regional translation → download PDF.

### Project structure
```
hakathon/
├── backend/
│   ├── app.py                 # FastAPI entrypoint + /health
│   ├── routers/crop.py        # /analyze-image /final-diagnosis /translate /generate-pdf
│   ├── services/
│   │   ├── gemma_service.py    # Gemma 4 wrapper (grounded in the notebook)
│   │   ├── prompt_service.py   # all prompt templates
│   │   ├── translation_service.py
│   │   └── pdf_service.py      # ReportLab PDF
│   ├── utils/{image_utils,json_utils}.py
│   ├── models/schemas.py      # Pydantic JSON contracts
│   ├── requirements.txt
│   └── .env.example
├── frontend/
│   ├── main.py                # Streamlit app (Home / Analysis / Report / About)
│   ├── components/ui.py       # cards, badges, hero, CSS
│   ├── utils/api.py           # backend HTTP client
│   ├── .streamlit/config.toml # green theme
│   ├── requirements.txt
│   └── .env.example
└── README.md
```

---

## Quick start (local)

You need **Python 3.10+** and a **Google AI Studio API key**
(https://aistudio.google.com/apikey).

### 1) Backend
```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# edit .env and set GOOGLE_API_KEY=...
uvicorn app:app --reload --port 8000
```
Open http://localhost:8000/docs to try the API. Check http://localhost:8000/health.

### 2) Frontend (new terminal)
```bash
cd frontend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # BACKEND_URL defaults to http://localhost:8000
streamlit run main.py
```
Open http://localhost:8501.

---

## API reference

| Method | Path                   | Body                                   | Returns |
|--------|------------------------|----------------------------------------|---------|
| GET    | `/health`              | —                                      | status + model + key configured |
| POST   | `/api/analyze-image`   | multipart `file`                       | `AnalysisResult` (+ 3 questions) |
| POST   | `/api/final-diagnosis` | multipart `file`, `analysis`, `answers`| `FinalDiagnosis` |
| POST   | `/api/translate`       | `{report, language}`                   | translated `FinalDiagnosis` |
| POST   | `/api/generate-pdf`    | `FinalDiagnosis` (+ `?language=`)      | `application/pdf` |

All JSON shapes are defined in [`backend/models/schemas.py`](backend/models/schemas.py).

---

## Gemma integration notes (important)

Grounded in the reference Kaggle notebook:

- SDK: `google-genai` — `client = genai.Client(api_key=...)`.
- Vision call: `client.models.generate_content(model="models/gemma-4-31b-it", contents=[pil_image, prompt])`.
- **Gemma does not support Gemini-only structured output** (`system_instruction`,
  `response_mime_type`, `response_schema`). So we **prompt for JSON** and parse
  defensively (strip ```` ```json ```` fences, slice `{`…`}`, retry on failure).
  See [`utils/json_utils.py`](backend/utils/json_utils.py) and
  [`services/gemma_service.py`](backend/services/gemma_service.py).

### Regional PDF fonts
Hindi/Bengali render on-screen out of the box. For **PDF** in those scripts,
set `KRISHIMITRA_PDF_FONT` to a Unicode TTF (e.g. `NotoSansDevanagari-Regular.ttf`)
in `backend/.env`. Without it, the PDF falls back to Latin fonts.

---

## Deployment

- **Backend** → Render / Railway / Fly.io: run
  `uvicorn app:app --host 0.0.0.0 --port $PORT`, set `GOOGLE_API_KEY` and
  `CORS_ORIGINS` to your frontend URL.
- **Frontend** → Streamlit Community Cloud: point it at `frontend/main.py`, add a
  secret `BACKEND_URL` = your deployed backend URL.

---

## Disclaimer
KrishiMitra AI provides **AI-assisted assessments, not guaranteed diagnoses**.
Always confirm with a local agricultural expert before applying any chemical
treatment.
