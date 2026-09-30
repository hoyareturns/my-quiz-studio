import streamlit as st
import qrcode
from io import BytesIO
from datetime import datetime, timedelta, timezone

def get_kst_time():
    return datetime.now(timezone(timedelta(hours=9))).strftime('%Y-%m-%d %H:%M:%S')

@st.cache_data(ttl=3600)
def generate_qr_code(url):
    qr = qrcode.QRCode(version=1, box_size=4, border=2)
    qr.add_data(url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buf = BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()

def apply_custom_style():
    st.markdown("""
    <style>
    :root { --accent: #176c62; --ink: #163c3c; }
    .block-container { max-width: 1060px; padding-top: 4.5rem; padding-bottom: 3rem; }
    .app-heading { padding: 1.4rem 1.6rem; border-radius: 20px; background: linear-gradient(115deg, #e4f3ed, #f1f7fc); margin-bottom: 1.2rem; border: 1px solid #d7e9e1; }
    .eyebrow { font-size: .82rem; font-weight: 700; letter-spacing: .06em; color: #3a7364; }
    .app-heading h1 { color: #173f3b; font-size: 2rem; letter-spacing: -.06em; padding: .4rem 0; }
    .app-heading p { margin: 0; color: #48645f; font-size: .95rem; }
    [data-testid="stMain"] div[role="radiogroup"] { gap: .45rem; }
    div[role="radiogroup"] label { padding: .5rem .65rem; border-radius: 9px; min-height: 44px; }
    div[role="radiogroup"] label:has(input:checked) { background: rgba(23,108,98,.10); }
    div[role="radiogroup"][aria-label="메뉴"] { display: grid; grid-template-columns: repeat(8, minmax(0, 1fr)); gap: .35rem; }
    div[role="radiogroup"][aria-label="메뉴"] label { margin: 0; justify-content: center; padding: .6rem .25rem; border: 1px solid #dce6e1; }
    div[role="radiogroup"][aria-label="메뉴"] label > div:first-child { display: none; }
    div[role="radiogroup"][aria-label="메뉴"] label > div:last-child { padding: 0; }
    div[role="radiogroup"][aria-label="메뉴"] label:has(input:checked) { border-color: #176c62; background: #e0f0e9; font-weight: 700; }
    div[role="radiogroup"][aria-label="메뉴"] label:has(input:focus-visible) { outline: 2px solid #176c62; outline-offset: 2px; }
    button, [data-testid="stLinkButton"] a { min-height: 46px !important; border-radius: 10px !important; }
    button[kind="primary"] { font-weight: 700; }
    [data-testid="stCodeBlock"] button { opacity: 1 !important; }
    input, textarea { font-size: 16px !important; }
    [data-testid="stForm"] { border-radius: 14px; }
    [data-testid="stMetricValue"] { color: #176c62; }
    blockquote { border-left: 4px solid #64a993; border-radius: 6px; padding: .8rem 1rem; background: rgba(100,169,147,.08); }
    .stButton > button { white-space: normal; text-align: left; }
    @media (max-width: 900px) {
      div[role="radiogroup"][aria-label="메뉴"] { grid-template-columns: repeat(4, minmax(0, 1fr)); }
    }
    @media (max-width: 640px) {
      .block-container { padding: 4.3rem 1rem 3rem; }
      .app-heading { padding: 1.1rem; border-radius: 14px; }
      .app-heading h1 { font-size: 1.55rem; }
      div[role="radiogroup"] { gap: .2rem; flex-wrap: wrap; }
      div[role="radiogroup"] label { font-size: .9rem; padding: .4rem .5rem; }
      div[role="radiogroup"][aria-label="메뉴"] p { font-size: .82rem; text-align: center; }
      [data-testid="stHorizontalBlock"] { flex-wrap: wrap; gap: .7rem; }
      [data-testid="stHorizontalBlock"] > [data-testid="stColumn"] { min-width: min(100%, 240px); flex: 1 1 240px; }
      [data-testid="stCodeBlock"] pre { max-height: 280px; }
    }
    </style>
    """, unsafe_allow_html=True)
