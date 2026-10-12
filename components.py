"""Reusable Streamlit UI helpers: theme, KPI cards, badges, filters, safe chart/table display."""
import html
from pathlib import Path

import pandas as pd
import streamlit as st

import risk_engine as risk

BASE_DIR = Path(__file__).resolve().parent

# Support Level Colors - chosen with high contrast against Dark Blue cards
RISK_COLORS = {
    "Low": "#00E5FF",           # Neon Cyan (Doing well / On track)
    "Medium": "#FBBF24",        # Amber Warning (Some support needed)
    "High": "#F97316",          # Vibrant Orange (Needs attention)
    "Critical": "#FB7185",      # Vivid Coral Red (Urgent support)
    "Insufficient data": "#64748B", # Slate Grey
}

# Plain-language supportive labels for teachers and coordinators
SUPPORT_LEVEL_LABELS = {
    "Low": "Doing well",
    "Medium": "Some support needed",
    "High": "Needs attention",
    "Critical": "Needs urgent support",
    "Insufficient data": "Insufficient data",
}

# Reverse mapping for filters if needed
LABEL_TO_CATEGORY = {v: k for k, v in SUPPORT_LEVEL_LABELS.items()}

# Exact Palette Tokens
COLOR_BG_MAIN = "#071426"       # Main page background
COLOR_SIDEBAR = "#081A30"       # Sidebar background
COLOR_CARD = "#0B2342"          # Card background
COLOR_PANEL = "#102B4D"         # Secondary panel background
COLOR_ELECTRIC_BLUE = "#00A6FF" # Primary electric blue
COLOR_NEON_CYAN = "#00E5FF"     # Neon cyan accent
COLOR_SECONDARY_BLUE = "#38BDF8"# Secondary blue
COLOR_TEXT_MAIN = "#F1F7FF"     # Main text
COLOR_TEXT_SECONDARY = "#A9BCD6"# Secondary text
COLOR_BORDER = "rgba(0, 229, 255, 0.20)" # Subtle cyan borders
COLOR_SUCCESS = "#34D399"       # Success
COLOR_WARNING = "#FBBF24"       # Warning
COLOR_ERROR = "#FB7185"         # Error

BRAND = COLOR_BG_MAIN           # Backward-compat alias
BRAND_NAVY = COLOR_BG_MAIN
BRAND_TEAL = COLOR_NEON_CYAN

CSS = """
<style>
/* Learnlytics AI — Centralized Futuristic Dark Blue + Neon Glow Design System */
@import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&family=Inter:wght@400;500;600;700&display=swap');

:root {
    --bg-main: #071426;
    --bg-sidebar: #081A30;
    --bg-card: #0B2342;
    --bg-panel: #102B4D;
    --electric-blue: #00A6FF;
    --neon-cyan: #00E5FF;
    --secondary-blue: #38BDF8;
    --text-main: #F1F7FF;
    --text-muted: #A9BCD6;
    --border-glow: rgba(0, 229, 255, 0.20);
    --border-glow-hover: rgba(0, 229, 255, 0.55);
}

html, body, [class*="css"] {
    font-family: 'Plus Jakarta Sans', 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
}

/* Main Canvas */
.stApp {
    background-color: #071426 !important;
    color: #F1F7FF !important;
}

header[data-testid="stHeader"] {
    background: transparent !important;
}

/* Futuristic Headings with subtle gradient */
h1 {
    font-family: 'Plus Jakarta Sans', sans-serif !important;
    background: linear-gradient(135deg, #FFFFFF 30%, #00E5FF 95%) !important;
    -webkit-background-clip: text !important;
    -webkit-text-fill-color: transparent !important;
    font-weight: 800 !important;
    letter-spacing: -0.03em !important;
    font-size: 2.1rem !important;
    margin-bottom: 0.2rem !important;
}

h2 {
    font-family: 'Plus Jakarta Sans', sans-serif !important;
    color: #F1F7FF !important;
    font-weight: 700 !important;
    letter-spacing: -0.02em !important;
    font-size: 1.55rem !important;
}

h3 {
    font-family: 'Plus Jakarta Sans', sans-serif !important;
    color: #F1F7FF !important;
    font-weight: 700 !important;
    font-size: 1.25rem !important;
}

h4, h5, h6 {
    color: #A9BCD6 !important;
    font-weight: 600 !important;
}

/* Sidebar Deep Navy Theme */
section[data-testid="stSidebar"] {
    background-color: #081A30 !important;
    border-right: 1px solid rgba(0, 229, 255, 0.16) !important;
    box-shadow: 4px 0 24px rgba(7, 20, 38, 0.7) !important;
}

section[data-testid="stSidebar"] p,
section[data-testid="stSidebar"] span {
    color: #A9BCD6 !important;
}

section[data-testid="stSidebar"] hr {
    border-color: rgba(0, 229, 255, 0.14) !important;
    margin: 1rem 0 !important;
}

/* Sidebar Navigation Items */
section[data-testid="stSidebar"] [role="radiogroup"] label {
    background: transparent !important;
    border-radius: 8px !important;
    padding: 6px 12px !important;
    margin-bottom: 3px !important;
    transition: all 0.15s ease-in-out !important;
    border: 1px solid transparent !important;
}

section[data-testid="stSidebar"] [role="radiogroup"] label:hover {
    background: rgba(0, 166, 255, 0.08) !important;
    border-color: rgba(0, 229, 255, 0.2) !important;
}

section[data-testid="stSidebar"] [role="radiogroup"] label[data-checked="true"],
section[data-testid="stSidebar"] [role="radiogroup"] label:has(input:checked) {
    background: rgba(0, 166, 255, 0.14) !important;
    border-left: 3px solid #00E5FF !important;
    box-shadow: 0 0 14px rgba(0, 229, 255, 0.16) !important;
}

section[data-testid="stSidebar"] [role="radiogroup"] label[data-checked="true"] p,
section[data-testid="stSidebar"] [role="radiogroup"] label:has(input:checked) p {
    color: #00E5FF !important;
    font-weight: 700 !important;
}

/* Futuristic Rounded Cards */
.ep-card {
    background: #0B2342;
    border: 1px solid rgba(0, 229, 255, 0.20);
    border-radius: 14px;
    padding: 18px 20px;
    box-shadow: 0 4px 18px rgba(7, 20, 38, 0.8), 0 0 10px rgba(0, 166, 255, 0.04);
    transition: transform 0.2s cubic-bezier(0.16, 1, 0.3, 1), border-color 0.2s ease, box-shadow 0.2s ease;
    height: 100%;
    position: relative;
    overflow: hidden;
}

.ep-card::before {
    content: "";
    position: absolute;
    top: 0; left: 0; right: 0; height: 2px;
    background: linear-gradient(90deg, transparent, #00E5FF, transparent);
    opacity: 0.6;
}

.ep-card:hover {
    transform: translateY(-2px);
    border-color: #00E5FF;
    box-shadow: 0 8px 26px rgba(7, 20, 38, 0.95), 0 0 20px rgba(0, 229, 255, 0.22);
}

.ep-kpi-label {
    font-size: 0.76rem;
    color: #A9BCD6;
    text-transform: uppercase;
    letter-spacing: 0.07em;
    font-weight: 700;
    margin-bottom: 6px;
}

.ep-kpi-value {
    font-size: 2.1rem;
    font-weight: 800;
    color: #F1F7FF;
    line-height: 1.15;
    letter-spacing: -0.02em;
    text-shadow: 0 0 14px rgba(0, 229, 255, 0.35);
    animation: epKpiEntrance 0.35s cubic-bezier(0.16, 1, 0.3, 1) forwards;
}

.ep-kpi-note {
    font-size: 0.80rem;
    color: #00E5FF;
    font-weight: 600;
    margin-top: 6px;
}

/* --------------------------------------------------------------------------
   Animations (Fade-in, Hover Glow, KPI Entrance, Logo Pulse)
   Respects prefers-reduced-motion
   -------------------------------------------------------------------------- */
@keyframes epFadeInUp {
    0% {
        opacity: 0;
        transform: translateY(8px);
    }
    100% {
        opacity: 1;
        transform: translateY(0);
    }
}

@keyframes epPulseGlow {
    0%, 100% {
        filter: drop-shadow(0 0 4px rgba(0, 229, 255, 0.25));
    }
    50% {
        filter: drop-shadow(0 0 12px rgba(0, 229, 255, 0.55));
    }
}

@keyframes epKpiEntrance {
    0% {
        opacity: 0;
        transform: translateY(6px);
    }
    100% {
        opacity: 1;
        transform: translateY(0);
    }
}

/* Page entrance: subtle fade-in with a small upward movement */
.main .block-container {
    animation: epFadeInUp 0.35s cubic-bezier(0.16, 1, 0.3, 1) forwards !important;
}

/* Streamlit Native Bordered Containers (e.g. login card) */
[data-testid="stVerticalBlockBorderWrapper"] > div {
    background-color: #0B2342 !important;
    border: 1px solid rgba(0, 229, 255, 0.20) !important;
    border-radius: 14px !important;
    box-shadow: 0 4px 18px rgba(7, 20, 38, 0.7), inset 0 0 12px rgba(0, 166, 255, 0.03) !important;
    padding: 1.5rem 1.6rem !important;
    transition: border-color 0.25s ease, box-shadow 0.25s ease, transform 0.25s ease !important;
    animation: epFadeInUp 0.35s cubic-bezier(0.16, 1, 0.3, 1) forwards !important;
}

[data-testid="stVerticalBlockBorderWrapper"] > div:hover {
    border-color: rgba(0, 229, 255, 0.45) !important;
    box-shadow: 0 6px 24px rgba(0, 229, 255, 0.14), inset 0 0 16px rgba(0, 229, 255, 0.05) !important;
}

/* Logo restrained cyan glow animation */
.ep-logo-container img {
    animation: epPulseGlow 4s ease-in-out infinite alternate !important;
    transition: filter 0.3s ease !important;
}

.ep-logo-container img:hover {
    filter: drop-shadow(0 0 14px rgba(0, 229, 255, 0.75)) !important;
}

/* Badges with Neon Border Glow */
.ep-badge {
    display: inline-block;
    padding: 3px 12px;
    border-radius: 999px;
    color: #FFFFFF;
    font-size: 0.82rem;
    font-weight: 700;
    letter-spacing: 0.02em;
    box-shadow: 0 0 10px rgba(0, 0, 0, 0.4);
    border: 1px solid rgba(255, 255, 255, 0.18);
    transition: box-shadow 0.2s ease, transform 0.2s ease;
}

.ep-subtitle {
    color: #A9BCD6;
    margin-top: -0.5rem;
    margin-bottom: 0.5rem;
    font-size: 1.05rem;
    font-weight: 400;
}

.ep-page-help {
    color: #F1F7FF;
    font-size: 0.90rem;
    background: #102B4D;
    border-left: 4px solid #00E5FF;
    border-top: 1px solid rgba(0, 229, 255, 0.16);
    border-right: 1px solid rgba(0, 229, 255, 0.16);
    border-bottom: 1px solid rgba(0, 229, 255, 0.16);
    padding: 10px 16px;
    border-radius: 0 8px 8px 0;
    margin-bottom: 1.4rem;
    box-shadow: 0 4px 14px rgba(0, 0, 0, 0.3), 0 0 12px rgba(0, 229, 255, 0.06);
}

.ep-why-box {
    background: #102B4D;
    border: 1px solid rgba(0, 229, 255, 0.28);
    border-left: 4px solid #00A6FF;
    border-radius: 8px;
    padding: 12px 18px;
    margin-bottom: 16px;
    color: #F1F7FF;
    font-size: 0.94rem;
    box-shadow: 0 0 16px rgba(0, 166, 255, 0.10);
    transition: border-color 0.2s ease, box-shadow 0.2s ease;
}

.ep-why-box:hover {
    border-color: rgba(0, 229, 255, 0.45);
    box-shadow: 0 0 20px rgba(0, 166, 255, 0.16);
}

/* Primary and Standard Buttons with Smooth Glow & Hover Transition */
button[kind="primary"], .stButton > button {
    background: linear-gradient(135deg, #0B2342 0%, #102B4D 100%) !important;
    color: #F1F7FF !important;
    border: 1px solid rgba(0, 229, 255, 0.35) !important;
    border-radius: 8px !important;
    padding: 8px 20px !important;
    font-weight: 600 !important;
    font-size: 0.92rem !important;
    transition: background 0.2s ease, border-color 0.2s ease, color 0.2s ease, box-shadow 0.2s ease, transform 0.2s cubic-bezier(0.16, 1, 0.3, 1) !important;
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.3) !important;
}

button[kind="primary"]:hover, .stButton > button:hover {
    background: linear-gradient(135deg, #102B4D 0%, #005B94 100%) !important;
    border-color: #00E5FF !important;
    color: #FFFFFF !important;
    box-shadow: 0 0 16px rgba(0, 229, 255, 0.40), 0 0 4px #00E5FF !important;
    transform: translateY(-1.5px) !important;
}

button[kind="primary"]:active, .stButton > button:active {
    transform: translateY(0px) !important;
    box-shadow: 0 0 8px rgba(0, 229, 255, 0.25) !important;
}

/* Form Inputs & Controls */
.stTextInput input,
.stNumberInput input,
.stTextArea textarea {
    background-color: #102B4D !important;
    color: #F1F7FF !important;
    border: 1px solid rgba(0, 229, 255, 0.22) !important;
    border-radius: 8px !important;
    font-size: 0.92rem !important;
    transition: border-color 0.2s ease, box-shadow 0.2s ease !important;
}

.stTextInput input:focus,
.stNumberInput input:focus,
.stTextArea textarea:focus {
    border-color: #00E5FF !important;
    box-shadow: 0 0 14px rgba(0, 229, 255, 0.35) !important;
}

[data-baseweb="select"] > div {
    background-color: #102B4D !important;
    border: 1px solid rgba(0, 229, 255, 0.22) !important;
    border-radius: 8px !important;
    color: #F1F7FF !important;
    transition: border-color 0.2s ease, box-shadow 0.2s ease !important;
}

[data-baseweb="select"] > div:focus-within {
    border-color: #00E5FF !important;
    box-shadow: 0 0 14px rgba(0, 229, 255, 0.35) !important;
}

/* Radio selectors (e.g. login mode selector) */
div[data-testid="stRadio"] label p {
    color: #F1F7FF !important;
}

/* Tabs: Underline, Smooth Color & Glow */
button[data-baseweb="tab"] {
    background: transparent !important;
    color: #A9BCD6 !important;
    font-weight: 600 !important;
    font-size: 0.94rem !important;
    padding-top: 0.6rem !important;
    padding-bottom: 0.6rem !important;
    border-bottom: 2px solid transparent !important;
    transition: color 0.2s ease, border-color 0.2s ease, box-shadow 0.2s ease !important;
}

button[data-baseweb="tab"]:hover {
    color: #00E5FF !important;
}

button[data-baseweb="tab"][aria-selected="true"] {
    color: #00E5FF !important;
    border-bottom: 2px solid #00E5FF !important;
    box-shadow: 0 4px 12px rgba(0, 229, 255, 0.22) !important;
}

/* Expanders */
[data-testid="stExpander"] {
    background-color: #0B2342 !important;
    border: 1px solid rgba(0, 229, 255, 0.20) !important;
    border-radius: 12px !important;
    box-shadow: 0 4px 14px rgba(7, 20, 38, 0.6) !important;
    transition: border-color 0.2s ease, box-shadow 0.2s ease !important;
}

[data-testid="stExpander"]:hover {
    border-color: rgba(0, 229, 255, 0.40) !important;
    box-shadow: 0 6px 18px rgba(7, 20, 38, 0.8), 0 0 12px rgba(0, 229, 255, 0.10) !important;
}

/* Dataframe & Tables */
[data-testid="stDataFrame"] {
    border: 1px solid rgba(0, 229, 255, 0.20) !important;
    border-radius: 10px !important;
    overflow: hidden !important;
    box-shadow: 0 4px 14px rgba(7, 20, 38, 0.6) !important;
}

/* Alerts / Banners */
[data-testid="stAlert"] {
    background-color: #102B4D !important;
    border-radius: 10px !important;
    border: 1px solid rgba(0, 229, 255, 0.28) !important;
    color: #F1F7FF !important;
    box-shadow: 0 4px 14px rgba(7, 20, 38, 0.6) !important;
    transition: border-color 0.2s ease !important;
}

/* Code & Pre */
code, pre {
    background-color: #102B4D !important;
    color: #00E5FF !important;
    border: 1px solid rgba(0, 229, 255, 0.16) !important;
    border-radius: 6px !important;
}

/* Accessibility: Support prefers-reduced-motion */
@media (prefers-reduced-motion: reduce) {
    *,
    *::before,
    *::after {
        animation-duration: 0.01ms !important;
        animation-iteration-count: 1 !important;
        transition-duration: 0.01ms !important;
        scroll-behavior: auto !important;
    }
}
</style>
"""


# --------------------------------------------------------------------------
# Layout and theme
# --------------------------------------------------------------------------
def inject_css():
    st.markdown(CSS, unsafe_allow_html=True)


def render_logo(width=220, target=st):
    """Safely render the Learnlytics AI SVG logo without raw SVG text leaking into markdown."""
    logo = BASE_DIR / "assets" / "logo.svg"
    if logo.exists():
        import base64
        svg_b64 = base64.b64encode(logo.read_bytes()).decode("ascii")
        target.markdown(
            f"<div class='ep-logo-container' style='margin-bottom:8px; line-height:0;'>"
            f"<img src='data:image/svg+xml;base64,{svg_b64}' alt='Learnlytics AI Logo' style='max-width:{width}px; width:100%; height:auto; display:block;' />"
            f"</div>",
            unsafe_allow_html=True,
        )
    else:
        target.markdown("### Learnlytics AI")


def sidebar_logo():
    """Render sidebar branding with logo, tagline, and short product description."""
    render_logo(width=210, target=st.sidebar)
    st.sidebar.caption("Understand Performance. Unlock Potential.")
    st.sidebar.caption("AI-powered student analytics and explainable early-warning platform to support learner success.")



def page_header(title, subtitle="", page_help=""):
    """Render page title with optional subtitle and explicit 'What is this page for?' caption."""
    st.title(title)
    if subtitle:
        st.markdown(f"<div class='ep-subtitle'>{html.escape(subtitle)}</div>", unsafe_allow_html=True)
    if page_help:
        st.caption(f"**What is this page for?** {page_help}")


def kpi_card(label, value, note=""):
    st.markdown(
        f"<div class='ep-card'><div class='ep-kpi-label'>{html.escape(str(label))}</div>"
        f"<div class='ep-kpi-value'>{html.escape(str(value))}</div>"
        f"<div class='ep-kpi-note'>{html.escape(str(note))}</div></div>", unsafe_allow_html=True)


def kpi_row(items):
    """items: list of (label, value, note)."""
    cols = st.columns(len(items))
    for col, (label, value, note) in zip(cols, items):
        with col:
            kpi_card(label, value, note)


def risk_badge(category, label=None):
    """Coloured pill for a support category; defaults to friendly support level text."""
    color = RISK_COLORS.get(category, "#5B6475")
    display_text = label or SUPPORT_LEVEL_LABELS.get(category, category)
    return f"<span class='ep-badge' style='background:{color}'>{html.escape(str(display_text))}</span>"


def student_summary_sentence(student, screening, is_self=False):
    """A single factual sentence explaining status, avoiding jargon."""
    if not student or not screening:
        return "Your progress details are being updated." if is_self else "Student record details are being reviewed."
    cat = screening.get("category", "Low")
    reasons = screening.get("reasons", [])
    
    if cat == "Insufficient data":
        unavail = screening.get("unavailable", [])
        if unavail:
            missing_str = ", ".join(unavail)
            return (
                f"Some of your records are still being entered ({missing_str} are missing). Your status will update once grades are recorded."
                if is_self else
                f"This student has insufficient data recorded ({missing_str} are missing) so no support level can be calculated yet."
            )
        return (
            "Not enough attendance or marks data has been recorded yet to calculate your standing."
            if is_self else
            "This student does not have enough attendance or score data recorded to calculate a support level."
        )

    att = student.get("attendance_rate")
    score = student.get("academic_score")
    asg = student.get("assignment_rate")
    att_str = f"{att:.1f}%" if att is not None and not pd.isna(att) else "not recorded"
    score_str = f"{score:.1f}%" if score is not None and not pd.isna(score) else "not recorded"
    asg_str = f"{asg:.1f}%" if asg is not None and not pd.isna(asg) else "not recorded"

    if not reasons or cat == "Low":
        if is_self:
            return (
                f"Your attendance is {att_str} and your academic score is {score_str}. "
                f"All your tracked metrics meet the school's benchmarks (attendance >= 75%, score >= 50%, assignments >= 60%). Keep building on your progress."
            )
        return f"This student is doing well on all tracked indicators (attendance: {att_str}, academic score: {score_str}) and meets institutional targets."

    # Highlight specific metric numbers
    points = []
    for ind in screening.get("indicators", []):
        if ind.get("triggered"):
            k = ind.get("key")
            thr = ind.get("threshold")
            val = ind.get("value")
            if k == "attendance" and val is not None:
                points.append(f"attendance is {val:.1f}% (target: {thr:.0f}%)" if is_self else f"attendance is {val:.1f}% (target: {thr:.0f}%)")
            elif k == "score" and val is not None:
                points.append(f"academic score is {val:.1f}% (target: {thr:.0f}%)" if is_self else f"academic score is {val:.1f}% (target: {thr:.0f}%)")
            elif k == "assignment" and val is not None:
                points.append(f"assignment completion is {val:.1f}% (target: {thr:.0f}%)" if is_self else f"assignment completion is {val:.1f}% (target: {thr:.0f}%)")
            elif k == "decline" and val is not None:
                points.append(f"academic score dropped by {val:.1f} points across recent weeks" if is_self else f"academic score dropped by {val:.1f} points across recent history")

    level_name = SUPPORT_LEVEL_LABELS.get(cat, cat)
    if points:
        details = ", and ".join(points)
        if is_self:
            return f"Your current standing is '{level_name}' because your {details}. Focus on these areas with your teachers to boost your grade."
        return f"This student is flagged for '{level_name}' because their {details}."
    if is_self:
        return f"Your current standing is '{level_name}' based on the recorded course benchmarks."
    return f"This student is flagged for '{level_name}' based on the recorded academic guidelines."


def render_why_box(student, screening, is_self=False):
    """Render the summary box in the UI."""
    sentence = student_summary_sentence(student, screening, is_self=is_self)
    header_title = "Your Progress at a Glance" if is_self else "Why is this student shown here?"
    st.markdown(f"<div class='ep-why-box'><strong>{header_title}:</strong> {html.escape(sentence)}</div>", unsafe_allow_html=True)


def screening_disclaimer():
    st.info(risk.DISCLAIMER)


# --------------------------------------------------------------------------
# Messages
# --------------------------------------------------------------------------
def flash(message, kind="success"):
    """Queue a message that survives st.rerun()."""
    st.session_state.setdefault("_flash", []).append((kind, message))


def render_flash():
    for kind, message in st.session_state.pop("_flash", []):
        getattr(st, kind, st.info)(message)


def show_errors(errors):
    for err in errors:
        st.error(err)


# --------------------------------------------------------------------------
# Formatting
# --------------------------------------------------------------------------
def fmt_pct(value):
    return "Not recorded" if value is None or pd.isna(value) else f"{value:.1f}%"


def metric_text(value):
    """Value for a text input: blank when missing."""
    return "" if value is None or pd.isna(value) else f"{value:g}"


def evidence_dataframe(screening):
    rows = []
    for ind in screening["indicators"]:
        if ind["key"] == "decline":
            value = "Not recorded" if ind["value"] is None else f"{-ind['value']:+.1f} pts"
            guide = f"drop of {ind['threshold']:.0f}+ pts"
        else:
            value = "Not recorded" if ind["value"] is None else f"{ind['value']:.1f}%"
            guide = f">= {ind['threshold']:.0f}%"
        rows.append({"Indicator": ind["label"], "Recorded Value": value, "Target Guideline": guide,
                     "Status": ind["status"], "Points Added": ind["weight"] if ind["triggered"] else 0})
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------
# Display wrappers that work across Streamlit versions
# --------------------------------------------------------------------------
def _stretch(fn, *args, **kwargs):
    try:
        return fn(*args, width="stretch", **kwargs)
    except TypeError:  # older Streamlit or API change: use_container_width
        return fn(*args, use_container_width=True, **kwargs)


def show_df(df, **kwargs):
    if df is None or len(df) == 0:
        st.caption("No records to display.")
        return
    _stretch(st.dataframe, df, hide_index=True, **kwargs)


def show_chart(fig, key, empty_note="No data available for this chart."):
    if fig is None:
        st.caption(empty_note)
        return
    # Apply futuristic Dark Blue & Neon styling to plotly layout
    fig.update_layout(
        paper_bgcolor="rgba(11, 35, 66, 0.4)",
        plot_bgcolor="rgba(16, 43, 77, 0.3)",
        font=dict(color="#F1F7FF", family="'Plus Jakarta Sans', 'Inter', sans-serif"),
        hoverlabel=dict(
            bgcolor="#0B2342",
            bordercolor="#00E5FF",
            font=dict(color="#F1F7FF", size=12, family="'Plus Jakarta Sans', sans-serif")
        ),
        legend=dict(
            font=dict(color="#A9BCD6"),
            bgcolor="rgba(11, 35, 66, 0.5)",
            bordercolor="rgba(0, 229, 255, 0.20)",
            borderwidth=1
        )
    )
    fig.update_xaxes(
        gridcolor="rgba(0, 229, 255, 0.12)",
        zerolinecolor="rgba(0, 166, 255, 0.25)",
        linecolor="rgba(0, 229, 255, 0.20)",
        tickfont=dict(color="#A9BCD6"),
        title_font=dict(color="#F1F7FF")
    )
    fig.update_yaxes(
        gridcolor="rgba(0, 229, 255, 0.12)",
        zerolinecolor="rgba(0, 166, 255, 0.25)",
        linecolor="rgba(0, 229, 255, 0.20)",
        tickfont=dict(color="#A9BCD6"),
        title_font=dict(color="#F1F7FF")
    )
    _stretch(st.plotly_chart, fig, key=key)


# --------------------------------------------------------------------------
# Shared widgets
# --------------------------------------------------------------------------
def filter_bar(df, prefix, with_category=True, default_categories=None):
    """Department / semester (/ support level) filters. Returns the filtered DataFrame."""
    n_cols = 3 if with_category else 2
    cols = st.columns(n_cols)
    departments = sorted(df["department"].dropna().unique()) if not df.empty else []
    semesters = sorted(df["semester"].dropna().unique()) if not df.empty else []
    sel_dept = cols[0].multiselect(
        "Department", departments, key=f"{prefix}_dept",
        help="Filter student list by department or program"
    )
    sel_sem = cols[1].multiselect(
        "Semester", semesters, key=f"{prefix}_sem",
        help="Filter student list by current enrolled semester"
    )
    sel_cat = None
    if with_category:
        # Provide friendly support level names in UI
        cat_options = [SUPPORT_LEVEL_LABELS.get(c, c) for c in risk.ALL_CATEGORIES]
        default_labels = [SUPPORT_LEVEL_LABELS.get(c, c) for c in (default_categories or [])]
        sel_labels = cols[2].multiselect(
            "Support level", cat_options,
            default=default_labels, key=f"{prefix}_cat",
            help="Filter by support need (Doing well, Some support needed, Needs attention, Needs urgent support)"
        )
        if sel_labels:
            sel_cat = [LABEL_TO_CATEGORY.get(l, l) for l in sel_labels]

    out = df
    if sel_dept:
        out = out[out["department"].isin(sel_dept)]
    if sel_sem:
        out = out[out["semester"].isin(sel_sem)]
    if sel_cat:
        out = out[out["risk_category"].isin(sel_cat)]
    return out


def student_picker(df, key, label="Select a student"):
    """Selectbox of students; returns the chosen student_id or None."""
    if df.empty:
        st.info("No students match the current filters. Try resetting the filters above or add new students.")
        return None
    ids = list(df["student_id"])
    names = dict(zip(df["student_id"], df["name"]))
    if key in st.session_state and st.session_state[key] not in ids:
        del st.session_state[key]
    return st.selectbox(
        label, ids,
        format_func=lambda i: f"{i} - {names[i]}",
        key=key,
        help="Choose a student from the list to view their detailed metrics and history"
    )

