"""Reusable UI components and styling for the Streamlit frontend."""
import streamlit as st

# Global CSS — green agricultural theme, rounded cards, badges.
# Cards are intentionally LIGHT with explicit high-contrast text so they stay
# readable regardless of the viewer's OS light/dark preference (we do NOT use
# prefers-color-scheme, which previously fought the forced-light Streamlit theme
# and made card text unreadable).
CSS = """
<style>
:root {
  --km-green: #2e7d32;
  --km-green-dark: #14401b;
  --km-green-light: #eaf5ec;
  --km-amber: #e65100;
  --km-red: #c62828;
  --km-ink: #14201a;
  --km-muted: #55655a;
  --km-border: #d5e3d8;
}

/* Keep the app background consistently light so light cards read well. */
.stApp { background: #f6faf6; }

.km-hero {
  background: linear-gradient(135deg, #2e7d32 0%, #66bb6a 100%);
  border-radius: 20px;
  padding: 40px 38px;
  color: #ffffff;
  margin-bottom: 10px;
  box-shadow: 0 8px 24px rgba(46,125,50,0.18);
}
.km-hero h1 { font-size: 2.4rem; margin: 0 0 6px 0; font-weight: 800; color:#fff; }
.km-hero p  { font-size: 1.08rem; margin: 0; color:#f2fff2; opacity: 0.96; }

.km-card {
  background: #ffffff;
  border: 1px solid var(--km-border);
  border-radius: 16px;
  padding: 18px 20px;
  box-shadow: 0 2px 12px rgba(20,64,27,0.06);
  margin-bottom: 14px;
  height: 100%;
  transition: box-shadow .18s ease, transform .18s ease;
}
.km-card:hover { box-shadow: 0 6px 18px rgba(20,64,27,0.12); transform: translateY(-1px); }

/* Force readable text on every element inside a card. */
.km-card, .km-card * { color: var(--km-ink); }
.km-card h4 {
  margin: 0 0 8px 0; color: var(--km-muted) !important;
  font-size: 0.72rem; font-weight: 700;
  text-transform: uppercase; letter-spacing: 0.07em;
}
.km-card .km-value {
  font-size: 1.28rem; font-weight: 800; color: var(--km-green-dark) !important;
  line-height: 1.3; word-break: break-word;
}

.km-pill-list { margin: 4px 0 0 2px; padding-left: 18px; }
.km-pill-list li {
  margin-bottom: 7px; color: var(--km-ink) !important;
  font-size: 0.98rem; line-height: 1.45;
}
.km-pill-list li::marker { color: var(--km-green); }

.km-badge {
  display: inline-block; padding: 5px 16px; border-radius: 999px;
  font-weight: 800; font-size: 0.9rem; color: #ffffff !important;
  letter-spacing: 0.02em; box-shadow: 0 2px 6px rgba(0,0,0,0.12);
}
.km-badge.low    { background: var(--km-green); }
.km-badge.medium { background: var(--km-amber); }
.km-badge.high   { background: var(--km-red); }
.km-badge.info   { background: #1565c0; }

.km-section-title {
  color: var(--km-green-dark); font-weight: 800; font-size: 1.3rem;
  margin: 20px 0 10px 0; border-left: 4px solid var(--km-green);
  padding-left: 10px;
}
</style>
"""


def inject_css():
    st.markdown(CSS, unsafe_allow_html=True)


def hero(title: str, subtitle: str):
    st.markdown(
        f"""<div class="km-hero"><h1>{title}</h1><p>{subtitle}</p></div>""",
        unsafe_allow_html=True,
    )


def _badge_class(level: str) -> str:
    l = (level or "").strip().lower()
    if l in {"low", "routine"}:
        return "low"
    if l in {"medium", "soon"}:
        return "medium"
    if l in {"high", "immediate"}:
        return "high"
    return "info"


def badge(text: str, level: str):
    st.markdown(
        f'<span class="km-badge {_badge_class(level)}">{text}</span>',
        unsafe_allow_html=True,
    )


def metric_card(col, label: str, value: str, level: str | None = None):
    with col:
        if level:
            value_html = (
                f'<span class="km-badge {_badge_class(level)}">{value}</span>'
            )
        else:
            value_html = f'<span class="km-value">{value}</span>'
        st.markdown(
            f'<div class="km-card"><h4>{label}</h4>{value_html}</div>',
            unsafe_allow_html=True,
        )


def section_title(text: str):
    st.markdown(f'<div class="km-section-title">{text}</div>', unsafe_allow_html=True)


def bullet_card(title: str, items: list[str], icon: str = "•"):
    lis = "".join(f"<li>{i}</li>" for i in (items or ["—"]))
    st.markdown(
        f"""<div class="km-card"><h4>{icon} {title}</h4>
        <ul class="km-pill-list">{lis}</ul></div>""",
        unsafe_allow_html=True,
    )
