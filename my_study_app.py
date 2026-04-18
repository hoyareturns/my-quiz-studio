import streamlit as st
import re
import time
import random
from database import get_all_quizzes, get_all_results, get_settings, get_chats, save_quiz
from utils import robust_parse, generate_quiz_with_ai
from prompts import VIEW_OPTIONS
from admin import show_admin_sidebar
from pages_logic import show_season_leaderboard, show_chat_room, show_quiz_area
from my_study_app_utils import get_kst_time, generate_qr_code, apply_custom_style
from wrong_answer_logic import show_wrong_answer_conquest

def main():
    st.set_page_config(
        page_title="우정 파괴소",
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
            border-bottom: 1px solid #ddd !important;
            border-radius: 0 !important;
        }
        .title-text {
            font-size: 1.6rem !important;
            font-weight: 800;
            margin: 0 !important;
            white-space: nowrap;
        }
        </style>
    """, unsafe_allow_html=True)

    app_settings = get_settings()
    APP_URL = "https://hoya-quiz-studio.streamlit.app"
    
    with st.sidebar:
        show_admin_sidebar(app_settings, get_kst_time)
        st.divider()
        st.caption("친구 초대용 QR코드")
        st.image(generate_qr_code(APP_URL), width=100)

    # 중복 없는 랜덤 아이디 생성
    if 'player_name' not in st.session_state or not st.session_state.player_name:
        results = get_all_results()
        chats = get_chats()
        existing_users = set(str(r.get('User')) for r in results if r.get('User'))
        existing_users.update(set(str(c.get('User')) for c in chats if c.get('User')))
                
        while True:
            rand_num = random.randint(1000, 9999)
            new_id = f"우정파괴자{rand_num}"
            if new_id not in existing_users:
                st.session_state.player_name = new_id
                break

    c1, c2 = st.columns([0.45, 0.55])
    with c1:
        st.markdown('<p class="title-text">우정 파괴소</p>', unsafe_allow_html=True)
    with c2:
        st.session_state.player_name = st.text_input("아이디", value=st.session_state.player_name)

    st.write("")
    st.write("")
    st.write("")

    default_view = app_settings.get('default_view', "퀴즈 선택")
    def_idx = VIEW_OPTIONS.index(default_view) if default_view in VIEW_OPTIONS else 0

    view_mode = st.radio(
        "탭", 
        VIEW_OPTIONS, 
        horizontal=True, 
        label_visibility="collapsed", 
        index=def_idx,
        key="main_tab_selector"
    )
    
    st.write("") 

    season_start = app_settings.get('season_start', '2000-01-01 00:00:00')
    season_res = [r for r in get_all_results() if r.get('Time', '') >= season_start]

    # 세션 상태 초기화 리스트에 quiz_jump 추가
    for k in ['selected_quiz', 'user_answers', 'quiz_finished', 'start_time', 'review_data', 'answered_list', 'quiz_jump']:
        if k not in st.session_state: 
            st.session_state[k] = "" if k == 'selected_quiz' else [] if k in ['review_data', 'answered_list'] else {} if k == 'user_answers' else False if k in ['quiz_finished', 'quiz_jump'] else None

    if view_mode == "구역별 최강자":
        show_season_leaderboard(season_res, season_start)
    elif view_mode == "오답 정복":
        # 퀴즈 데이터와 parse 함수를 넘겨줌
        show_wrong_answer_conquest(st.session_state.player_name, get_all_quizzes(), robust_parse)
    elif view_mode == "우정파괴채팅": 
        show_chat_room(st.session_state.player_name)
    else:
        show_quiz_area(get_all_quizzes(), season_res, app_settings, st.session_state.player_name, robust_parse)

if __name__ == "__main__":
    main()
