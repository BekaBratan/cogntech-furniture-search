"""Shared light visual theme for the Streamlit pages."""
import streamlit as st

CSS = """
<style>
:root { --ink:#1d1d1f; --muted:#6e6e73; --surface:#f5f5f7; --line:#e8e8ed; }
html, body, [data-testid="stAppViewContainer"], [data-testid="stApp"] {
  background:#fff; color:var(--ink);
  font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;
}
[data-testid="stMainBlockContainer"] { max-width:1500px; padding:3rem 2.2rem 5rem; }
[data-testid="stHeader"] { background:rgba(255,255,255,.94); border-bottom:1px solid #f0f0f2; }
[data-testid="stSidebar"] { background:var(--surface); border-right:1px solid var(--line); }
h1,h2,h3 { color:var(--ink); letter-spacing:-.035em; font-weight:650; }
h1 { font-size:clamp(2.2rem,5vw,3.8rem); }
h3 { font-size:1.45rem; line-height:1.25; }
p, label { line-height:1.55; }
[data-testid="stCaptionContainer"] { color:var(--muted); }
.sf-hero { padding:1.4rem 0 2.4rem; max-width:850px; }
.sf-hero .sf-eyebrow { color:#86868b; font-size:.73rem; font-weight:650; letter-spacing:.18em; margin-bottom:1rem; }
.sf-hero h1 { margin:0; font-size:clamp(2.4rem,5.5vw,4.2rem); font-weight:650; line-height:1.08; letter-spacing:-.055em; }
.sf-hero p { color:var(--muted); font-size:1.12rem; margin:1.2rem 0 0; max-width:660px; }
[data-testid="stForm"] { background:var(--surface); border:1px solid transparent; border-radius:24px; padding:1.8rem; margin-bottom:1.6rem; }
[data-testid="stVerticalBlockBorderWrapper"] { border:1px solid var(--line) !important; border-radius:24px !important; padding:1.35rem !important; background:#fff; box-shadow:0 4px 20px rgba(0,0,0,.025); }
[data-testid="stTextInputRootElement"], [data-baseweb="input"], [data-baseweb="select"] > div,
[data-testid="stNumberInputContainer"] { border-radius:12px !important; }
[data-testid="stTextInputRootElement"] input { min-height:44px; }
.stButton > button, .stDownloadButton > button, .stLinkButton > a, [data-testid="stFormSubmitButton"] > button {
  border-radius:999px !important; min-height:42px; padding:.55rem 1.25rem; font-weight:500;
  transition:background .18s ease,box-shadow .18s ease;
}
button[kind="primary"], [data-testid="stFormSubmitButton"] button {
  background:#1d1d1f !important; border-color:#1d1d1f !important; color:#fff !important;
}
button[kind="primary"]:hover, [data-testid="stFormSubmitButton"] button:hover { background:#363638 !important; }
button:focus-visible, a:focus-visible { outline:3px solid #0071e3 !important; outline-offset:3px; }
[data-testid="stExpander"] { border-radius:16px !important; border-color:var(--line); }
[data-testid="stAlert"] { border-radius:16px; }
[data-testid="stMetric"] { background:var(--surface); border-radius:20px; padding:1.3rem 1.5rem; }
[data-testid="stMetricValue"] { font-weight:600; letter-spacing:-.04em; }
[data-testid="stImage"] img { border-radius:18px; object-fit:contain; }
.sf-image-empty { min-height:220px; border-radius:20px; background:var(--surface); display:flex;
  flex-direction:column; justify-content:center; align-items:center; gap:14px; color:#86868b; font-size:.84rem; text-align:center; padding:20px; }
.sf-image-empty svg { width:46px; height:46px; stroke:#aeaeb2; }
@media (max-width:640px) {
  [data-testid="stMainBlockContainer"] { padding:1.8rem 1rem 3rem; }
  .sf-hero { padding:.8rem 0 1.6rem; }
  .sf-hero p { font-size:1rem; }
  [data-testid="stForm"] { padding:1.2rem; border-radius:20px; }
  .sf-image-empty { min-height:150px; }
}
@media (prefers-reduced-motion:reduce) { button,a { transition:none !important; } }
</style>
"""

def apply_theme():
    st.markdown(CSS,unsafe_allow_html=True)

def hero(title, subtitle):
    # These arguments are fixed page copy, never catalog or user input.
    st.markdown(f'<div class="sf-hero"><div class="sf-eyebrow">SMART FURNITURE</div><h1>{title}</h1><p>{subtitle}</p></div>',unsafe_allow_html=True)

def missing_image():
    st.markdown("""<div class="sf-image-empty">
    <svg viewBox="0 0 48 48" fill="none" aria-hidden="true"><rect x="6" y="8" width="36" height="32" rx="6" stroke-width="1.5"/>
    <circle cx="17" cy="19" r="3" stroke-width="1.5"/><path d="M8 34l10-10 8 8 6-6 8 8" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg>
    <span>Сурет әлі қосылмаған</span></div>""",unsafe_allow_html=True)

