"""PDF report generation using ReportLab.

Produces a clean, farmer-friendly one/two-page report from a FinalDiagnosis.
Supports Unicode content (Hindi/Bengali) when a matching TTF font is available;
otherwise falls back to Helvetica for English reports.
"""
import io
import os
from datetime import datetime

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

# Optional Unicode font for Hindi/Bengali. Point KRISHIMITRA_PDF_FONT at a TTF
# (e.g. NotoSansDevanagari-Regular.ttf) to enable proper regional rendering.
_UNICODE_FONT_ENV = "KRISHIMITRA_PDF_FONT"
_BASE_FONT = "Helvetica"
_BOLD_FONT = "Helvetica-Bold"

# Brand logo — used as a centered header and a faint full-page watermark.
# Override with KRISHIMITRA_LOGO; defaults to <project_root>/img/logo.png.
_DEFAULT_LOGO = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "img", "logo.png")
)
_WATERMARK_OPACITY = 0.06  # fraction of original alpha kept for the watermark
_watermark_cache: ImageReader | None = None


def _logo_path() -> str | None:
    path = os.getenv("KRISHIMITRA_LOGO", _DEFAULT_LOGO)
    return path if path and os.path.exists(path) else None


def _watermark_image() -> ImageReader | None:
    """Build (once) a very faint version of the logo for the page background."""
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
    """Page callback: draw the faint logo centered behind the content."""
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
    """Centered header logo flowable, aspect-ratio preserved."""
    path = _logo_path()
    if not path:
        return None
    with PILImage.open(path) as im:
        iw, ih = im.size
    width = width_mm * mm
    img = RLImage(path, width=width, height=width * (ih / iw))
    img.hAlign = "CENTER"
    return img


def _register_unicode_font() -> str:
    """Register a Unicode TTF if configured; return the font name to use."""
    global _BASE_FONT, _BOLD_FONT
    font_path = os.getenv(_UNICODE_FONT_ENV)
    if font_path and os.path.exists(font_path):
        try:
            pdfmetrics.registerFont(TTFont("KM-Unicode", font_path))
            _BASE_FONT = "KM-Unicode"
            _BOLD_FONT = "KM-Unicode"  # single-weight fallback
        except Exception:
            pass
    return _BASE_FONT


def _styles():
    _register_unicode_font()
    styles = getSampleStyleSheet()
    styles.add(
        ParagraphStyle(
            "KMTitle", parent=styles["Title"], textColor=GREEN,
            fontName=_BOLD_FONT, fontSize=22, spaceAfter=2,
        )
    )
    styles.add(
        ParagraphStyle(
            "KMSubtitle", parent=styles["Normal"], textColor=GREY,
            fontName=_BASE_FONT, fontSize=10, spaceAfter=10,
        )
    )
    styles.add(
        ParagraphStyle(
            "KMSection", parent=styles["Heading2"], textColor=GREEN,
            fontName=_BOLD_FONT, fontSize=13, spaceBefore=12, spaceAfter=4,
        )
    )
    styles.add(
        ParagraphStyle(
            "KMBody", parent=styles["Normal"], textColor=DARK,
            fontName=_BASE_FONT, fontSize=10.5, leading=15, alignment=TA_LEFT,
        )
    )
    styles.add(
        ParagraphStyle(
            "KMBullet", parent=styles["Normal"], textColor=DARK,
            fontName=_BASE_FONT, fontSize=10.5, leading=15, leftIndent=4,
        )
    )
    styles.add(
        ParagraphStyle(
            "KMDisclaimer", parent=styles["Normal"], textColor=GREY,
            fontName=_BASE_FONT, fontSize=8.5, leading=12, spaceBefore=6,
        )
    )
    return styles


def _summary_table(report: FinalDiagnosis, styles) -> Table:
    def cell(text):
        return Paragraph(str(text), styles["KMBody"])

    data = [
        [cell("<b>Crop</b>"), cell(report.crop),
         cell("<b>Confidence</b>"), cell(report.confidence)],
        [cell("<b>Possible Issue</b>"), cell(report.possible_disease),
         cell("<b>Severity</b>"), cell(report.severity)],
        [cell("<b>Urgency</b>"), cell(report.urgency),
         cell("<b>Date</b>"), cell(datetime.now().strftime("%d %b %Y"))],
    ]
    table = Table(data, colWidths=[32 * mm, 58 * mm, 32 * mm, 48 * mm])
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), LIGHT_GREEN),
                ("BOX", (0, 0), (-1, -1), 0.5, GREEN),
                ("INNERGRID", (0, 0), (-1, -1), 0.4, colors.white),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    return table


def _bullets(items, styles) -> ListFlowable:
    if not items:
        items = ["No specific items provided."]
    return ListFlowable(
        [ListItem(Paragraph(str(i), styles["KMBullet"]), leftIndent=10) for i in items],
        bulletType="bullet",
        bulletColor=GREEN,
        start="•",
    )


def generate_pdf(report: FinalDiagnosis, language: str = "English") -> bytes:
    """Render a FinalDiagnosis into PDF bytes."""
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
    story.append(Paragraph("KrishiMitra AI", styles["KMTitle"]))
    story.append(
        Paragraph(
            f"AI-Assisted Crop Health Report &nbsp;•&nbsp; Language: {language}",
            styles["KMSubtitle"],
        )
    )
    story.append(HRFlowable(width="100%", thickness=1, color=GREEN))
    story.append(Spacer(1, 8))

    story.append(_summary_table(report, styles))
    story.append(Spacer(1, 6))

    story.append(Paragraph("AI Reasoning", styles["KMSection"]))
    story.append(Paragraph(report.reasoning or "—", styles["KMBody"]))

    story.append(Paragraph("Recommended Treatment", styles["KMSection"]))
    story.append(_bullets(report.treatment, styles))

    story.append(Paragraph("Prevention", styles["KMSection"]))
    story.append(_bullets(report.prevention, styles))

    story.append(Paragraph("What to Monitor", styles["KMSection"]))
    story.append(_bullets(report.monitoring, styles))

    story.append(Spacer(1, 8))
    story.append(HRFlowable(width="100%", thickness=0.5, color=GREY))
    story.append(
        Paragraph("<b>Disclaimer:</b> " + (report.disclaimer or ""), styles["KMDisclaimer"])
    )
    story.append(
        Paragraph(
            "Generated by KrishiMitra AI • Powered by Gemma 4 • "
            "Build with Gemma Hackathon",
            styles["KMDisclaimer"],
        )
    )

    doc.build(story, onFirstPage=_draw_watermark, onLaterPages=_draw_watermark)
    buffer.seek(0)
    return buffer.read()
