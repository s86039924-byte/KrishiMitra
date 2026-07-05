"""KrishiMitra AI — Streamlit frontend.

Run:
    cd frontend
    streamlit run main.py

Requires the FastAPI backend running (set BACKEND_URL, default localhost:8000).

Language: the user picks a language once, up front, in the sidebar. That choice
is passed to every AI call, so the assessment, the follow-up questions, the
final report and the PDF all come back in that language.
"""
import sys
from pathlib import Path

import streamlit as st

# Make sibling packages importable when run via `streamlit run main.py`.
sys.path.insert(0, str(Path(__file__).parent))

from components import ui  # noqa: E402
from utils import api  # noqa: E402
from utils.api import APIError  # noqa: E402

st.set_page_config(
    page_title="KrishiMitra AI",
    page_icon="🌾",
    layout="wide",
    initial_sidebar_state="expanded",
)

ui.inject_css()

# Display label (native script) -> language name sent to the backend.
LANGUAGES = {
    "English": "English",
    "हिन्दी — Hindi": "Hindi",
    "বাংলা — Bengali": "Bengali",
    "मराठी — Marathi": "Marathi",
    "తెలుగు — Telugu": "Telugu",
    "தமிழ் — Tamil": "Tamil",
    "ગુજરાતી — Gujarati": "Gujarati",
    "ಕನ್ನಡ — Kannada": "Kannada",
    "മലയാളം — Malayalam": "Malayalam",
    "ਪੰਜਾਬੀ — Punjabi": "Punjabi",
    "ଓଡ଼ିଆ — Odia": "Odia",
    "اردو — Urdu": "Urdu",
    "অসমীয়া — Assamese": "Assamese",
}

# --------------------------------------------------------------------------- #
# Session state
# --------------------------------------------------------------------------- #
_DEFAULTS = {
    "page": "🏠 Home",
    "lang_choice": "English",  # widget-backed display label
    "language": "English",     # resolved backend language name
    "image_bytes": None,
    "image_name": None,
    "image_type": None,
    "analysis": None,       # dict from /analyze-image (in chosen language)
    "answers": None,        # list[{question, answer}]
    "report": None,         # dict from /final-diagnosis (in chosen language)
    "display_report": None, # report currently shown (may be re-translated)
    "report_lang": None,    # language the display_report is currently in
}
for key, value in _DEFAULTS.items():
    st.session_state.setdefault(key, value)

# Apply any navigation requested on the previous run. This MUST run before the
# sidebar radio (key="page") is instantiated — Streamlit forbids mutating a
# widget-backed key after the widget exists.
_pending_page = st.session_state.pop("_nav_to", None)
if _pending_page is not None:
    st.session_state.page = _pending_page


def goto(page: str):
    """Request navigation; applied at the top of the next run (see above)."""
    st.session_state._nav_to = page


# --------------------------------------------------------------------------- #
# Sidebar — brand, language (at the head), navigation, backend status
# --------------------------------------------------------------------------- #
with st.sidebar:
    st.markdown("## 🌾 KrishiMitra AI")
    st.caption("Crop disease assistant • Gemma 4")

    st.markdown("#### 🌐 Language / भाषा")
    st.selectbox(
        "Choose your language",
        list(LANGUAGES.keys()),
        key="lang_choice",
        label_visibility="collapsed",
    )
    # Resolve to the backend language name (plain key — safe to set anytime).
    st.session_state.language = LANGUAGES[st.session_state.lang_choice]
    st.caption("The assessment, questions & report will be in this language.")

    st.divider()
    page = st.radio(
        "Navigate",
        ["🏠 Home", "📷 Crop Analysis", "📋 Report", "ℹ️ About"],
        key="page",
    )
    st.divider()
    try:
        h = api.health()
        if h.get("api_key_configured"):
            st.success(f"Backend online · {h.get('model', '').split('/')[-1]}")
        else:
            st.warning("Backend online but GOOGLE_API_KEY missing.")
    except Exception:
        st.error("Backend offline. Start FastAPI on port 8000.")


# --------------------------------------------------------------------------- #
# Pages
# --------------------------------------------------------------------------- #
def page_home():
    ui.hero(
        "🌾 KrishiMitra AI",
        "AI-powered multilingual crop disease assistant powered by Gemma 4.",
    )
    st.write("")
    c1, c2, c3 = st.columns(3)
    ui.metric_card(c1, "Step 1", "Pick language & upload a photo")
    ui.metric_card(c2, "Step 2", "Answer 3 quick questions")
    ui.metric_card(c3, "Step 3", "Get treatment + PDF")

    st.write("")
    ui.section_title("Why KrishiMitra?")
    st.markdown(
        "- **Speaks your language** — pick from 13 Indian languages in the sidebar; "
        "every answer, question and report comes back in it.\n"
        "- **Context-aware reasoning** — the AI asks *disease-specific* follow-up "
        "questions instead of guessing from the image alone.\n"
        "- **Farmer-friendly report** — download a clean PDF to keep or share.\n"
        "- **Honest by design** — every result is an *AI-assisted assessment*, "
        "never a guaranteed diagnosis."
    )
    st.write("")
    st.info(f"🌐 Current language: **{st.session_state.lang_choice}** "
            "— change it anytime in the sidebar.")
    if st.button("🚀 Start Analysis", type="primary", use_container_width=True):
        goto("📷 Crop Analysis")
        st.rerun()


def page_analysis():
    ui.section_title("📷 Crop Analysis")
    st.caption(f"🌐 Responding in **{st.session_state.lang_choice}**")

    uploaded = st.file_uploader(
        "Upload a clear photo of the affected leaf, fruit, or plant",
        type=["jpg", "jpeg", "png", "webp", "bmp"],
    )

    if uploaded is not None:
        st.session_state.image_bytes = uploaded.getvalue()
        st.session_state.image_name = uploaded.name
        st.session_state.image_type = uploaded.type

    if st.session_state.image_bytes:
        col_img, col_btn = st.columns([1, 1])
        with col_img:
            st.image(st.session_state.image_bytes, caption=st.session_state.image_name,
                     use_container_width=True)
        with col_btn:
            st.write("")
            if st.button("🔍 Analyze Image", type="primary", use_container_width=True):
                with st.spinner("Gemma is analysing your crop image…"):
                    try:
                        analysis = api.analyze_image(
                            st.session_state.image_bytes,
                            st.session_state.image_name,
                            st.session_state.image_type or "image/png",
                            language=st.session_state.language,
                        )
                        st.session_state.analysis = analysis
                        st.session_state.answers = None
                        st.session_state.report = None
                        st.session_state.display_report = None
                    except APIError as e:
                        if e.code == "no_crop_detected":
                            st.session_state.analysis = None
                            st.warning("🌱 " + e.message)
                            st.info("Tip: upload a close-up of the leaf, fruit, or "
                                    "plant showing the problem — good lighting helps.")
                        else:
                            st.error(f"❌ {e.message}")
                    except Exception as e:  # noqa: BLE001
                        st.error(f"❌ Unexpected error: {e}")

    analysis = st.session_state.analysis
    if analysis:
        st.divider()
        ui.section_title("Assessment")
        c1, c2, c3 = st.columns(3)
        ui.metric_card(c1, "Crop", analysis["crop"])
        ui.metric_card(c2, "Possible Issue", analysis["possible_disease"])
        ui.metric_card(c3, "Confidence", analysis["confidence"])
        c4, c5 = st.columns(2)
        ui.metric_card(c4, "Severity", analysis["severity"], level=analysis["severity"])
        with c5:
            ui.bullet_card("Visible Symptoms", analysis.get("visible_symptoms", []), icon="👀")

        with st.expander("🧠 AI Reasoning", expanded=True):
            st.write(analysis.get("reasoning", ""))

        # --- Follow-up questions (in the chosen language) ---
        st.divider()
        ui.section_title("Follow-up Questions")
        st.caption("These questions are generated specifically for this issue.")
        with st.form("followup_form"):
            answers = []
            for i, q in enumerate(analysis.get("followup_questions", [])):
                ans = st.text_input(f"{i + 1}. {q}", key=f"ans_{i}")
                answers.append({"question": q, "answer": ans})
            submitted = st.form_submit_button(
                "✅ Get Final Diagnosis", type="primary", use_container_width=True
            )

        if submitted:
            with st.spinner("Gemma is combining the image with your answers…"):
                try:
                    report = api.final_diagnosis(
                        st.session_state.image_bytes,
                        st.session_state.image_name,
                        st.session_state.image_type or "image/png",
                        analysis,
                        answers,
                        language=st.session_state.language,
                    )
                    st.session_state.answers = answers
                    st.session_state.report = report
                    st.session_state.display_report = report
                    st.session_state.report_lang = st.session_state.language
                    goto("📋 Report")
                    st.rerun()
                except APIError as e:
                    st.error(f"❌ {e.message}")
                except Exception as e:  # noqa: BLE001
                    st.error(f"❌ Unexpected error: {e}")


def page_report():
    ui.section_title("📋 Final Report")
    report = st.session_state.display_report
    if not report:
        st.info("No report yet. Run an analysis first.")
        if st.button("Go to Crop Analysis"):
            goto("📷 Crop Analysis")
            st.rerun()
        return

    report_lang = st.session_state.report_lang or "English"
    st.caption(f"🌐 Report language: **{report_lang}**")

    # If the user changed the global language after generating the report,
    # offer to re-render this report in the new language (one Gemma call).
    if st.session_state.language != report_lang:
        if st.button(
            f"🌐 Show this report in {st.session_state.lang_choice}",
            use_container_width=True,
        ):
            with st.spinner(f"Translating to {st.session_state.language}…"):
                try:
                    translated = api.translate(report, st.session_state.language)
                    st.session_state.display_report = translated
                    st.session_state.report_lang = st.session_state.language
                    st.rerun()
                except APIError as e:
                    st.error(f"❌ {e.message}")

    # --- Summary cards (severity/urgency stay colour-coded English enums) ---
    c1, c2, c3, c4 = st.columns(4)
    ui.metric_card(c1, "Crop", report["crop"])
    ui.metric_card(c2, "Confidence", report["confidence"])
    ui.metric_card(c3, "Severity", report["severity"], level=report["severity"])
    ui.metric_card(c4, "Urgency", report["urgency"], level=report["urgency"])

    with st.expander("🧠 AI Reasoning", expanded=True):
        st.write(report.get("reasoning", ""))

    ui.bullet_card("💊 Treatment", report.get("treatment", []))
    ui.bullet_card("🛡️ Prevention", report.get("prevention", []))
    ui.bullet_card("🔭 What to Monitor", report.get("monitoring", []))

    st.warning("⚠️ " + report.get("disclaimer", ""))

    # --- Download PDF (in the report's current language) ---
    st.divider()
    try:
        pdf_bytes = api.generate_pdf(report, language=report_lang)
        st.download_button(
            "⬇️ Download PDF Report",
            data=pdf_bytes,
            file_name=f"KrishiMitra_{report['crop'].replace(' ', '_')}.pdf",
            mime="application/pdf",
            type="primary",
            use_container_width=True,
        )
    except APIError as e:
        st.error(f"Could not generate PDF: {e.message}")

    if st.button("🔄 Analyze another crop", use_container_width=True):
        for k in ("analysis", "answers", "report", "display_report",
                  "report_lang", "image_bytes", "image_name", "image_type"):
            st.session_state[k] = None
        goto("📷 Crop Analysis")
        st.rerun()


def page_about():
    ui.section_title("ℹ️ About KrishiMitra AI")
    st.markdown(
        "**KrishiMitra AI** helps farmers identify possible crop problems from a "
        "single photo, using **Gemma 4's multimodal vision + reasoning** — in the "
        "farmer's own language.\n\n"
        "**Workflow**\n"
        "1. Pick your language, then upload a crop image → Gemma detects crop + "
        "possible issue.\n"
        "2. Gemma asks 3 issue-specific follow-up questions (in your language).\n"
        "3. Your answers + the image → a final report with treatment, prevention, "
        "monitoring, urgency and a disclaimer.\n"
        "4. Download a PDF report with the KisanMitraa branding.\n\n"
        "**Languages:** English, Hindi, Bengali, Marathi, Telugu, Tamil, Gujarati, "
        "Kannada, Malayalam, Punjabi, Odia, Urdu, Assamese.\n\n"
        "**Track:** GenAI for Good • **Event:** Build with Gemma\n\n"
        "> This tool provides AI-assisted assessments, not guaranteed diagnoses. "
        "Always confirm with a local agricultural expert before chemical treatment."
    )


PAGES = {
    "🏠 Home": page_home,
    "📷 Crop Analysis": page_analysis,
    "📋 Report": page_report,
    "ℹ️ About": page_about,
}
PAGES[st.session_state.page]()
