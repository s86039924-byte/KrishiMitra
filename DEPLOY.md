# 🚀 Deploying KrishiMitra AI

The app has **two services** that deploy to **two hosts**:

| Service | Folder | Host | Free? |
|---------|--------|------|-------|
| Backend (FastAPI + Gemma) | `backend/` | **Render** | ✅ free web service |
| Frontend (Streamlit) | `frontend/` | **Streamlit Community Cloud** | ✅ free |

> ⚠️ **Order matters.** Deploy the **backend first**, copy its public URL, then
> deploy the frontend pointing at that URL. The Streamlit "Deploy" button alone
> only hosts the frontend — without a hosted backend it will show "Backend offline".

---

## 0) One-time prep

1. **Rotate your API key** (it was shared in chat). Get a fresh one at
   https://aistudio.google.com/apikey.
2. **Push the repo to GitHub** (both hosts deploy from GitHub):
   ```bash
   cd ~/Desktop/hakathon
   git init && git add . && git commit -m "KrishiMitra AI"
   git branch -M main
   git remote add origin https://github.com/<you>/krishimitra-ai.git
   git push -u origin main
   ```
   `.gitignore` already excludes `.env` and `secrets.toml`, so no secrets are pushed.

---

## 1) Backend → Render (free)

**Option A — Blueprint (uses `render.yaml`, easiest):**
1. https://dashboard.render.com → **New +** → **Blueprint** → pick your repo.
2. Render reads `render.yaml` and creates the `krishimitra-backend` web service.
3. When prompted, set the secret **`GOOGLE_API_KEY`** = your new key.
4. Deploy. Wait for "Live".

**Option B — Manual:**
1. **New +** → **Web Service** → your repo.
2. Settings:
   - **Root Directory:** `backend`
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `uvicorn app:app --host 0.0.0.0 --port $PORT`
   - **Health Check Path:** `/health`
3. **Environment** → add:
   - `GOOGLE_API_KEY` = your key
   - `GEMMA_MODEL` = `models/gemma-4-31b-it`
   - `CORS_ORIGINS` = `*` (tighten later)
4. Create Web Service.

**Verify:** open `https://<your-service>.onrender.com/health` → you should see
`{"status":"ok","model":"models/gemma-4-31b-it","api_key_configured":true}`.

📋 **Copy this backend URL** — you need it for the frontend.

> Note: Render's free tier **sleeps after ~15 min idle**; the first request after
> sleeping takes ~30–50s to wake. Fine for a demo. The frontend timeout is 120s.

---

## 2) Frontend → Streamlit Community Cloud (free)

1. https://share.streamlit.io → **Create app** → **From GitHub**.
2. Settings:
   - **Repository:** your repo
   - **Branch:** `main`
   - **Main file path:** `frontend/main.py`
3. **Advanced settings → Secrets**, paste:
   ```toml
   BACKEND_URL = "https://<your-service>.onrender.com"
   BACKEND_TIMEOUT = "120"
   ```
   (No trailing slash on the URL.)
4. **Deploy**.

Streamlit installs from `frontend/requirements.txt` automatically.

---

## 3) Lock down CORS (recommended)

Once you know your Streamlit URL (e.g. `https://krishimitra.streamlit.app`),
go back to Render → the backend's **Environment** → set:
```
CORS_ORIGINS = https://krishimitra.streamlit.app
```
Redeploy. Now only your frontend can call the API.

---

## 4) Regional-language PDFs (optional but recommended)

On-screen text renders in all 13 languages already. For **Hindi/Bengali/Tamil/etc.
inside the downloaded PDF**, add a Unicode font:

1. Commit a Noto TTF into the repo, e.g. `backend/fonts/NotoSansDevanagari-Regular.ttf`.
2. On Render, set `KRISHIMITRA_PDF_FONT = fonts/NotoSansDevanagari-Regular.ttf`.

Without it, PDF body text for non-Latin scripts falls back to Latin glyphs
(English PDFs are unaffected).

---

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| Frontend: "Backend offline" | `BACKEND_URL` secret wrong/missing, or backend still waking (retry in ~40s). |
| `/health` shows `api_key_configured:false` | `GOOGLE_API_KEY` not set on Render. |
| CORS error in browser console | Set `CORS_ORIGINS` to your exact Streamlit URL (or `*` to test). |
| Analysis times out | Free Render cold start — first call is slow; subsequent calls are fast. |
| PDF shows boxes for Hindi text | Add the Noto font (section 4). |
