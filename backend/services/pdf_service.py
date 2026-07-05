"""PDF report generation using ReportLab.

Produces a clean, farmer-friendly one/two-page report from a FinalDiagnosis in
any supported language.

Mixed-script rendering: bundled Noto fonts (backend/fonts/) do NOT contain Latin
letters, and reports mix scripts (e.g. "मक्का (Corn)", English enums like
"High", the "KrishiMitra AI" brand). So every text run is split by codepoint —
Latin/ASCII/digits render in Helvetica, the regional script renders in its Noto
font — via ReportLab inline <font> markup. This makes any mixed string render
correctly without maintaining per-language label translations.
"""
import io
import os
from datetime import datetime
from xml.sax.saxutils import escape as _xml_escape

from PIL import Image as PILImage
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    HRFlowable,
    Image as RLImage,
    ListFlowable,
    ListItem,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from models.schemas import FinalDiagnosis

GREEN = colors.HexColor("#2e7d32")
LIGHT_GREEN = colors.HexColor("#e8f5e9")
DARK = colors.HexColor("#1b1b1b")
GREY = colors.HexColor("#555555")

LATIN_FONT = "Helvetica"
LATIN_BOLD = "Helvetica-Bold"

# --- Fonts -----------------------------------------------------------------
# Each language maps to a bundled Noto TTF that covers its script.
_FONTS_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "fonts"))
_UNICODE_FONT_ENV = "KRISHIMITRA_PDF_FONT"  # optional hard override (one TTF)

_LANG_FONT = {
    "Hindi": "NotoSansDevanagari-Regular.ttf",
    "Marathi": "NotoSansDevanagari-Regular.ttf",
    "Bengali": "NotoSansBengali-Regular.ttf",
    "Assamese": "NotoSansBengali-Regular.ttf",
    "Tamil": "NotoSansTamil-Regular.ttf",
    "Telugu": "NotoSansTelugu-Regular.ttf",
    "Gujarati": "NotoSansGujarati-Regular.ttf",
    "Kannada": "NotoSansKannada-Regular.ttf",
    "Malayalam": "NotoSansMalayalam-Regular.ttf",
    "Punjabi": "NotoSansGurmukhi-Regular.ttf",
    "Odia": "NotoSansOriya-Regular.ttf",
    "Urdu": "NotoSansArabic-Regular.ttf",
}

_registered_fonts: set[str] = set()

# Codepoints below this are treated as Latin/common (ASCII, Latin-1/Ext, IPA).
# All supported Indic scripts + Arabic are well above it.
_LATIN_MAX = 0x0500


def _script_font_for(language: str) -> str:
    """Register (once) and return the Noto font name for `language`'s script.

    Returns LATIN_FONT for English or when the TTF is unavailable, so the PDF
    never crashes on a font problem.
    """
    lang = (language or "English").strip().title()
    if lang == "English":
        return LATIN_FONT

    override = os.getenv(_UNICODE_FONT_ENV)
    path = override if override and os.path.exists(override) else None
    if path is None:
        fname = _LANG_FONT.get(lang)
        if fname:
            candidate = os.path.join(_FONTS_DIR, fname)
            if os.path.exists(candidate):
                path = candidate
    if not path:
        return LATIN_FONT

    name = "KM-" + os.path.splitext(os.path.basename(path))[0]
    if name not in _registered_fonts:
        try:
            pdfmetrics.registerFont(TTFont(name, path))
            _registered_fonts.add(name)
        except Exception:
            return LATIN_FONT
    return name


def _mixed(text, script_font: str) -> str:
    """Return ReportLab markup that renders Latin runs in Helvetica and script
    runs in `script_font`. Escapes XML-special characters."""
    text = "" if text is None else str(text)
    if script_font == LATIN_FONT:
        return _xml_escape(text)

    parts, buf, buf_latin = [], "", None

    def flush():
        nonlocal buf
        if buf:
            font = LATIN_FONT if buf_latin else script_font
            parts.append(f'<font name="{font}">{_xml_escape(buf)}</font>')
            buf = ""

    for ch in text:
        is_latin = ord(ch) < _LATIN_MAX
        if buf_latin is None or is_latin == buf_latin:
            buf += ch
        else:
            flush()
            buf = ch
        buf_latin = is_latin
    flush()
    return "".join(parts)


# --- Logo / watermark ------------------------------------------------------
_DEFAULT_LOGO = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "img", "logo.png")
)
_WATERMARK_OPACITY = 0.06
_watermark_cache: ImageReader | None = None


def _logo_path() -> str | None:
    path = os.getenv("KRISHIMITRA_LOGO", _DEFAULT_LOGO)
    return path if path and os.path.exists(path) else None


def _watermark_image() -> ImageReader | None:
    global _watermark_cache
    if _watermark_cache is not None:
        return _watermark_cache
    path = _logo_path()
    if not path:
        return None
    try:
        logo = PILImage.open(path).convert("RGBA")
        r, g, b, a = logo.split()
        a = a.point(lambda v: int(v * _WATERMARK_OPACITY))
        faded = PILImage.merge("RGBA", (r, g, b, a))
        buf = io.BytesIO()
        faded.save(buf, format="PNG")
        buf.seek(0)
        _watermark_cache = ImageReader(buf)
    except Exception:
        _watermark_cache = None
    return _watermark_cache


def _draw_watermark(canvas, doc):
    wm = _watermark_image()
    if wm is None:
        return
    page_w, page_h = A4
    target_w = page_w * 0.6
    iw, ih = wm.getSize()
    target_h = target_w * (ih / iw)
    x = (page_w - target_w) / 2
    y = (page_h - target_h) / 2
    canvas.saveState()
    canvas.drawImage(wm, x, y, width=target_w, height=target_h, mask="auto")
    canvas.restoreState()


def _header_logo(width_mm: float = 40) -> RLImage | None:
    path = _logo_path()
    if not path:
        return None
    with PILImage.open(path) as im:
        iw, ih = im.size
    width = width_mm * mm
    img = RLImage(path, width=width, height=width * (ih / iw))
    img.hAlign = "CENTER"
    return img


# --- Styles ----------------------------------------------------------------
def _styles():
    """All styles use a Latin base font; per-run script switching is done via
    the _mixed() markup, so styles are language-independent."""
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle("KMTitle", parent=styles["Title"], textColor=GREEN,
                              fontName=LATIN_BOLD, fontSize=22, spaceAfter=2))
    styles.add(ParagraphStyle("KMSubtitle", parent=styles["Normal"], textColor=GREY,
                              fontName=LATIN_FONT, fontSize=10, spaceAfter=10))
    styles.add(ParagraphStyle("KMSection", parent=styles["Heading2"], textColor=GREEN,
                              fontName=LATIN_BOLD, fontSize=13, spaceBefore=12, spaceAfter=4))
    styles.add(ParagraphStyle("KMLabel", parent=styles["Normal"], textColor=DARK,
                              fontName=LATIN_BOLD, fontSize=10.5, leading=15))
    styles.add(ParagraphStyle("KMBody", parent=styles["Normal"], textColor=DARK,
                              fontName=LATIN_FONT, fontSize=10.5, leading=15, alignment=TA_LEFT))
    styles.add(ParagraphStyle("KMBullet", parent=styles["Normal"], textColor=DARK,
                              fontName=LATIN_FONT, fontSize=10.5, leading=15, leftIndent=4))
    styles.add(ParagraphStyle("KMDisclaimer", parent=styles["Normal"], textColor=GREY,
                              fontName=LATIN_FONT, fontSize=8.5, leading=12, spaceBefore=6))
    return styles


def _summary_table(report: FinalDiagnosis, styles, sf: str) -> Table:
    def label(text):
        return Paragraph(_mixed(text, sf), styles["KMLabel"])

    def value(text):
        return Paragraph(_mixed(text, sf), styles["KMBody"])

    data = [
        [label("Crop"), value(report.crop),
         label("Confidence"), value(report.confidence)],
        [label("Possible Issue"), value(report.possible_disease),
         label("Severity"), value(report.severity)],
        [label("Urgency"), value(report.urgency),
         label("Date"), value(datetime.now().strftime("%d %b %Y"))],
    ]
    table = Table(data, colWidths=[32 * mm, 58 * mm, 32 * mm, 48 * mm])
    table.setStyle(
        TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), LIGHT_GREEN),
            ("BOX", (0, 0), (-1, -1), 0.5, GREEN),
            ("INNERGRID", (0, 0), (-1, -1), 0.4, colors.white),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("LEFTPADDING", (0, 0), (-1, -1), 8),
            ("RIGHTPADDING", (0, 0), (-1, -1), 8),
            ("TOPPADDING", (0, 0), (-1, -1), 6),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ])
    )
    return table


def _bullets(items, styles, sf: str) -> ListFlowable:
    if not items:
        items = ["—"]
    return ListFlowable(
        [ListItem(Paragraph(_mixed(i, sf), styles["KMBullet"]), leftIndent=10)
         for i in items],
        bulletType="bullet", bulletColor=GREEN, start="•",
    )


def generate_pdf(report: FinalDiagnosis, language: str = "English") -> bytes:
    """Render a FinalDiagnosis into PDF bytes in the given language."""
    sf = _script_font_for(language)
    styles = _styles()
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4,
        leftMargin=18 * mm, rightMargin=18 * mm,
        topMargin=16 * mm, bottomMargin=16 * mm,
        title="KrishiMitra AI Crop Report",
    )

    story = []
    header = _header_logo()
    if header is not None:
        story.append(header)
        story.append(Spacer(1, 4))

    # Brand + subtitle are English chrome (Latin).
    story.append(Paragraph("KrishiMitra AI", styles["KMTitle"]))
    story.append(Paragraph(
        f"AI-Assisted Crop Health Report &nbsp;•&nbsp; Language: {language}",
        styles["KMSubtitle"]))
    story.append(HRFlowable(width="100%", thickness=1, color=GREEN))
    story.append(Spacer(1, 8))

    story.append(_summary_table(report, styles, sf))
    story.append(Spacer(1, 6))

    story.append(Paragraph("AI Reasoning", styles["KMSection"]))
    story.append(Paragraph(_mixed(report.reasoning or "—", sf), styles["KMBody"]))

    story.append(Paragraph("Recommended Treatment", styles["KMSection"]))
    story.append(_bullets(report.treatment, styles, sf))

    story.append(Paragraph("Prevention", styles["KMSection"]))
    story.append(_bullets(report.prevention, styles, sf))

    story.append(Paragraph("What to Monitor", styles["KMSection"]))
    story.append(_bullets(report.monitoring, styles, sf))

    story.append(Spacer(1, 8))
    story.append(HRFlowable(width="100%", thickness=0.5, color=GREY))
    story.append(Paragraph(
        "<b>Disclaimer:</b> " + _mixed(report.disclaimer or "", sf),
        styles["KMDisclaimer"]))
    story.append(Paragraph(
        "Generated by KrishiMitra AI • Powered by Gemma 4 • Build with Gemma Hackathon",
        styles["KMDisclaimer"]))

    doc.build(story, onFirstPage=_draw_watermark, onLaterPages=_draw_watermark)
    buffer.seek(0)
    return buffer.read()
