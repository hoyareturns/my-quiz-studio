import streamlit as st
import re
import time
import random
from database import get_all_quizzes, get_all_results, get_settings, get_chats, save_quiz
from utils import robust_parse, generate_quiz_with_ai

# prompts.py에서 모드별 이름표 함수를 불러옵니다.
from prompts import get_ui_labels 

from admin import show_admin_sidebar
from pages_logic import show_season_leaderboard, show_chat_room, show_quiz_area
from my_study_app_utils import get_kst_time, generate_qr_code, apply_custom_style
from wrong_answer_logic import show_wrong_answer_conquest
from personal_record_logic import show_personal_records

def main():
    # 1. URL 파라미터에서 현재 모드 읽기 (기본값은 personal)
    current_mode = st.query_params.get("mode", "personal")
    ui_labels = get_ui_labels(current_mode)
    
    # 2. 탭 메뉴 구성 (현재 접속한 모드에 맞게 이름이 바뀜)
    MODE_VIEW_OPTIONS = [
        ui_labels["TAB_QUIZ"], 
        ui_labels["TAB_REVIEW"], 
        ui_labels["TAB_RECORDS"], 
        ui_labels["TAB_RANK"], 
        ui_labels["TAB_CHAT"]
    ]

    st.set_page_config(
        page_title=ui_labels["APP_TITLE"],
        page_icon="logo.png",
        layout="centered"
    )

    apply_custom_style()
    st.markdown("""
        <style>
        header[data-testid="stHeader"] { 
            background-color: rgba(0,0,0,0) !important; 
            pointer-events: none !important; 
        }
        button[data-testid="stSidebarCollapseButton"] {
            pointer-events: auto !important;
            z-index: 9999 !important;
        }
        .main .block-container { padding-top: 5rem !important; }
        div[data-testid="stTextInput"] label { display: none !important; }
        div[data-testid="stTextInput"] input {
            height: 35px !important;
            padding: 2px 8px !important;
            font-size: 0.9rem !important;
            border: none !important;
            border-bottom: 1px solid #ccc !important;
            border-radius: 0 !important;
            background-color: transparent !important;
        }
        div[data-testid="stTextInput"] input:focus {
            border-bottom: 2px solid #ff4b4b !important;
            box-shadow: none !important;
        }
        .title-text {
            font-size: 2.2rem;
            font-weight: 800;
            color: #ff4b4b;
            margin-bottom: 0;
            padding-bottom: 0;
            line-height: 1.2;
        }
        div[data-testid="stRadio"] > div {
            display: flex;
            flex-direction: row;
            gap: 15px;
            justify-content: center;
        }
        /* QR 코드 캡션 스타일 */
        .qr-caption {
            font-size: 0.8rem;
            text-align: center;
            margin-top: 5px;
            color: #666;
        }
        </style>
    """, unsafe_allow_html=True)

    app_settings = get_settings()

    with st.sidebar:
        show_admin_sidebar(app_settings, get_kst_time)
        
        st.divider()
        st.caption(" 모드별 접속 QR코드")
        
        # 실제 앱 주소 (배포된 주소에 맞게 수정하세요)
        base_url = "https://my-quiz-studio.streamlit.app" 
        
        # --- [수정] QR 코드 2개를 나란히 배치 ---
        col1, col2 = st.columns(2)
        
        with col1:
            qr_p = generate_qr_code(f"{base_url}?mode=personal")
            st.image(qr_p, use_container_width=True)
            st.markdown('<p class="qr-caption"> 개인용</p>', unsafe_allow_html=True)
            
        with col2:
            qr_w = generate_qr_code(f"{base_url}?mode=work")
            st.image(qr_w, use_container_width=True)
            st.markdown('<p class="qr-caption"> 업무용</p>', unsafe_allow_html=True)
        
        st.write("")
        if current_mode == "work":
            st.success("현재 **업무 모드**로 접속 중입니다.")
        else:
            st.info("현재 **개인 모드**로 접속 중입니다.")

    c1, c2 = st.columns([1, 1])
    with c1:
        st.markdown(f'<p class="title-text">{ui_labels["APP_TITLE"]}</p>', unsafe_allow_html=True)
    with c2:
        st.session_state.player_name = st.text_input("아이디", value=st.session_state.player_name)

    st.write("")
    st.write("")

    # 기본 탭 설정 로직
    saved_default_view = app_settings.get('default_view', MODE_VIEW_OPTIONS[0])
    def_idx = MODE_VIEW_OPTIONS.index(saved_default_view) if saved_default_view in MODE_VIEW_OPTIONS else 0

    view_mode = st.radio(
        "탭", 
        MODE_VIEW_OPTIONS, 
        horizontal=True, 
        label_visibility="collapsed", 
        index=def_idx,
        key="main_tab_selector"
    )
    
    st.write("") 

    season_start = app_settings.get('season_start', '2000-01-01 00:00:00')
    season_res = [r for r in get_all_results() if r.get('Time', '') >= season_start]

    for k in ['selected_quiz', 'user_answers', 'quiz_finished', 'start_time', 'review_data', 'answered_list', 'quiz_jump']:
        if k not in st.session_state: 
            st.session_state[k] = "" if k == 'selected_quiz' else [] if k in ['review_data', 'answered_list'] else {} if k == 'user_answers' else False if k in ['quiz_finished', 'quiz_jump'] else None

    if view_mode == ui_labels["TAB_RANK"]:
        show_season_leaderboard(season_res, season_start)
    elif view_mode == ui_labels["TAB_REVIEW"]:
        show_wrong_answer_conquest(st.session_state.player_name, get_all_quizzes(), robust_parse)
    elif view_mode == ui_labels["TAB_RECORDS"]:
        show_personal_records(st.session_state.player_name, get_all_results())
    elif view_mode == ui_labels["TAB_CHAT"]:
        show_chat_room(st.session_state.player_name, ui_labels)
    else:
        show_quiz_area(get_all_quizzes(), season_res, app_settings, st.session_state.player_name, robust_parse, current_mode, ui_labels)

if __name__ == "__main__":
    if "player_name" not in st.session_state:
        st.session_state.player_name = f"Guest_{random.randint(1000,9999)}"
    main()