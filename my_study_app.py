import streamlit as st
import re
import time
import random

# 1. 공통 데이터 및 유틸리티 관련
from database import get_all_quizzes, get_all_results, get_settings, get_chats, save_quiz, get_unique_players
from utils import robust_parse, generate_quiz_with_ai,trigger_google_sheet_backup, natural_sort_key # natural_sort_key 추가
from prompts import VIEW_OPTIONS, APP_TITLE, TAB_QUIZ, TAB_REVIEW, TAB_RECORDS, TAB_RANK, TAB_CHAT, DEFAULT_CATEGORY
from my_study_app_utils import get_kst_time, generate_qr_code, apply_custom_style

# 2. 관리자 화면 관련
from admin import show_admin_sidebar

# 3. [개별 분리된] 페이지 로직 관련
from quiz_page import show_quiz_area
from leaderboard_page import show_season_leaderboard
from chat_page import show_chat_room
from wrong_answer_logic import show_wrong_answer_conquest
from personal_record_logic import show_personal_records


def main():
    st.set_page_config(
        page_title=APP_TITLE, 
        page_icon="logo.png",
        layout="centered"
    )

    apply_custom_style()
    st.markdown("""
        <style>
        header[data-testid="stHeader"] { background-color: rgba(0,0,0,0) !important; pointer-events: none !important; }
        button[data-testid="stSidebarCollapseButton"] { pointer-events: auto !important; z-index: 9999 !important; }
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
        div[data-testid="stTextInput"] input:focus { border-bottom: 2px solid #ff4b4b !important; box-shadow: none !important; }
        .title-text { font-size: 2.2rem; font-weight: 800; color: #ff4b4b; line-height: 1.2; }
        div[data-testid="stRadio"] > div { display: flex; flex-direction: column; gap: 10px; justify-content: flex-start; align-items: flex-start; } 
        </style>
    """, unsafe_allow_html=True)

    app_settings = get_settings()

    with st.sidebar:
        show_admin_sidebar(app_settings, get_kst_time)
        st.divider()
        app_url = "https://hoya-quiz-studio.streamlit.app/" 
        qr_img = generate_qr_code(app_url)
        st.image(qr_img, width=150)

    c1, c2 = st.columns([1, 1])
    with c1:
        st.markdown(f'<p class="title-text">{APP_TITLE}</p>', unsafe_allow_html=True)
    with c2:
        # 1. 기존 유저 목록 불러오기 및 정렬 (캐싱 활용)
        if "cached_user_list" not in st.session_state:
            # database.py에 추가하신 함수 호출
            raw_users = get_unique_players() 
            # utils.py의 natural_sort_key로 '유저2 < 유저11' 정렬 적용
            st.session_state.cached_user_list = sorted(raw_users, key=natural_sort_key)

        # 2. 드롭박스 선택 시 실행될 콜백 함수
        def on_user_dropdown_change():
            selected = st.session_state.user_dropdown_selection
            if selected != "--- 기존 유저 선택 ---":
                # 선택한 이름을 텍스트 입력창(session_state.player_name)에 즉시 반영
                st.session_state.player_name = selected

        # 3. 아이디 직접 입력창
        # key="player_name"을 지정하면 st.session_state.player_name과 자동으로 동기화됩니다.
        st.text_input("아이디", key="player_name", placeholder="이름을 입력하세요")

        # 4. 기존 유저 선택 드롭박스 (입력창 바로 아래 배치)
        st.selectbox(
            "기존 유저 목록",
            ["--- 기존 유저 선택 ---"] + st.session_state.cached_user_list,
            key="user_dropdown_selection",
            on_change=on_user_dropdown_change,
            label_visibility="collapsed" # 불필요한 라벨을 숨겨 입력창에 밀착시킴
        )

    st.write(""); st.write(""); st.write("")

    # 기본 탭 설정
    default_view = app_settings.get('default_view', TAB_QUIZ)
    def_idx = VIEW_OPTIONS.index(default_view) if default_view in VIEW_OPTIONS else 0

    view_mode = st.radio(
        "탭", VIEW_OPTIONS, horizontal=True, label_visibility="collapsed", index=def_idx, key="main_tab_selector"
    )
    
    st.write("") 

    season_start = app_settings.get('season_start', '2000-01-01 00:00:00')
    season_res = [r for r in get_all_results() if r.get('Time', '') >= season_start]

    # 세션 상태 초기화
    for k in ['selected_quiz', 'user_answers', 'quiz_finished', 'start_time', 'review_data', 'answered_list', 'quiz_jump']:
        if k not in st.session_state: 
            st.session_state[k] = "" if k == 'selected_quiz' else [] if k in ['review_data', 'answered_list'] else {} if k == 'user_answers' else False if k in ['quiz_finished', 'quiz_jump'] else None

    # --- [수정 완료] 조건 분기문 (ui_labels 대신 prompts 변수 직접 사용) ---
    if view_mode == TAB_RANK:
        show_season_leaderboard(season_res, season_start)
    elif view_mode == TAB_REVIEW:
        show_wrong_answer_conquest(st.session_state.player_name, get_all_quizzes(), robust_parse)
    elif view_mode == TAB_CHAT:
        show_chat_room(st.session_state.player_name)
    elif view_mode == TAB_RECORDS:
        show_personal_records(st.session_state.player_name, get_all_results())
    else:
        # TAB_QUIZ (퀴즈 선택)
        show_quiz_area(get_all_quizzes(), season_res, app_settings, st.session_state.player_name, robust_parse, get_kst_time)


if __name__ == "__main__":
    if "player_name" not in st.session_state:
        st.session_state.player_name = f"Guest_{random.randint(1000,9999)}"
    main()