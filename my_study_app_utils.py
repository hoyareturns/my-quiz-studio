import streamlit as st
import qrcode
from io import BytesIO
from datetime import datetime, timedelta

def get_kst_time():
    """한국 표준시(KST)를 반환합니다."""
    return (datetime.utcnow() + timedelta(hours=9)).strftime('%Y-%m-%d %H:%M:%S')

@st.cache_data(ttl=3600)
def generate_qr_code(url):
    """주어진 URL로 QR코드 이미지를 생성하여 바이트 데이터를 반환합니다."""
    qr = qrcode.QRCode(version=1, box_size=4, border=2)
    qr.add_data(url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buf = BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()

def apply_custom_style():
    """앱 전체에 적용될 커스텀 CSS 스타일을 정의합니다."""
    st.markdown("""
    <style>
    /* 메인 컨테이너 및 인용구 스타일 */
    [data-testid="stMain"] blockquote { 
        background-color: var(--secondary-background-color) !important; 
        border-left: 4px solid var(--primary-color) !important; 
        padding: 16px !important; 
        border-radius: 6px !important; 
        color: var(--text-color) !important; 
        font-style: normal !important; 
    }
    
    /* 문제 번호 헤더 */
    .question-header { 
        font-size: 16px; 
        font-weight: 700; 
        color: #ff4b4b; 
        margin-top: 24px; 
        margin-bottom: 8px; 
    }
    
    /* 채팅 메시지 박스 */
    .chat-msg { 
        padding: 10px; 
        border-radius: 8px; 
        margin-bottom: 8px; 
        background-color: var(--secondary-background-color); 
        color: var(--text-color); 
        border: 1px solid var(--border-color);
    }
    
    /* 채팅 사용자명 및 시스템명 */
    .chat-user { font-weight: 600; color: var(--primary-color); font-size: 13px; margin-right: 5px; }
    .chat-sys { font-weight: 800; color: #ff4b4b; font-size: 13px; margin-right: 5px; }
    .chat-time { font-size: 11px; opacity: 0.5; float: right; margin-left: 10px; }
    
    /* 1등 도발 박스 */
    .taunt-box { 
        background-color: #2c3e50; 
        color: white; 
        padding: 15px; 
        border-radius: 8px; 
        text-align: center; 
        font-weight: bold; 
        margin-bottom: 15px; 
        border: 2px solid #f1c40f;
    }
    .taunt-author { font-size: 12px; opacity: 0.8; margin-top: 6px; }
    
    /* 버튼 스타일 조정 */
    .stButton > button { 
        padding: 0.3rem 0.5rem !important; 
        min-height: 2.2rem !important; 
        border-radius: 6px !important; 
        font-size: 14px !important; 
    }
    
    /* 정답 해설(Exp-box) 스타일 */
    .exp-box { 
        background-color: #f0f2f6; 
        border-left: 5px solid #007bff; 
        padding: 15px; 
        border-radius: 5px; 
        margin-top: 10px; 
        color: #1f2d3d; 
        font-size: 14px; 
        line-height: 1.6;
    }
    
    /* 모바일 환경 탭 레이아웃 최적화 */
    [data-testid="column"] { padding: 0 4px !important; }
    @media (max-width: 768px) { 
        [data-testid="stTabs"] [data-testid="column"] { 
            flex: 1 1 calc(50% - 8px) !important; 
        } 
    }
    </style>
    """, unsafe_allow_html=True)