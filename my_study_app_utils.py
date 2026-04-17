import streamlit as st
import qrcode
from io import BytesIO
from datetime import datetime, timedelta

def get_kst_time():
    return (datetime.utcnow() + timedelta(hours=9)).strftime('%Y-%m-%d %H:%M:%S')

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
    [data-testid="stMain"] blockquote { 
        background-color: #f8f9fa !important; 
        border-left: 4px solid #ff4b4b !important; 
        padding: 16px !important; 
        border-radius: 6px !important; 
    }
    
    .chat-msg {
        background-color: #ffffff;
        border: 1px solid #e9ecef;
        padding: 10px;
        border-radius: 10px;
        margin-bottom: 8px;
    }
    .chat-user, .chat-sys { font-weight: 600; color: #ff4b4b; font-size: 13px; margin-right: 5px; }
    .chat-time { font-size: 11px; opacity: 0.5; float: right; }
    
    .stButton > button { 
        padding: 0.3rem 0.5rem !important; 
        min-height: 2.2rem !important; 
        border-radius: 6px !important; 
    }
    
    .stTabs [data-baseweb="tab"] {
        height: 40px;
        background-color: #f8f9fa;
        border-radius: 5px;
        padding: 5px 15px;
    }
    
    .exp-box {
        background-color: #f8f9fa;
        padding: 12px;
        border-left: 5px solid #ff4b4b;
        margin-top: 10px;
        font-size: 0.9rem;
    }
    </style>
    """, unsafe_allow_html=True)