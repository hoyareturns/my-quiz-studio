import streamlit as st
import re
import time
import random

# 1. 공통 데이터 및 유틸리티 관련
from database import get_all_quizzes, get_all_results, get_settings, get_chats, save_quiz, get_unique_players
from utils import robust_parse, generate_quiz_with_ai, trigger_google_sheet_backup, natural_sort_key 
from prompts import APP_TITLE, TAB_QUIZ, TAB_REVIEW, TAB_RECORDS, TAB_RANK, TAB_CHAT, TAB_PARTICIPATION
from my_study_app_utils import get_kst_time, generate_qr_code, apply_custom_style

# 2. 관리자 화면 관련
from admin import show_admin_sidebar

# 3. 페이지 로직 관련
from quiz_page import show_quiz_area
from leaderboard_page import show_season_leaderboard
from chat_page import show_chat_room
from wrong_answer_logic import show_wrong_answer_conquest
from personal_record_logic import show_personal_records
from participation_page import show_participation_status

def main():
    st.set_page_config(
        page_title=APP_TITLE, 
        page_icon="logo.png",
        layout="centered"
    )

    apply_custom_style()
    
    # CSS 설정 (꼬이게 만들던 레이아웃 꼼수 제거, 깔끔한 기본 스타일 유지)
    st.markdown("""
        <style>
        header[data-testid="stHeader"] { background-color: rgba(0,0,0,0) !important; pointer-events: none !important; }
        .main .block-container { padding-top: 5rem !important; }
        .title-text { font-size: 2.2rem; font-weight: 800; color: #ff4b4b; line-height: 1.2; }
        /* 라디오 버튼 간격 살짝 넓히기 (가독성 향상) */
        div.row-widget.stRadio > div { gap: 10px; }
        </style>
    """, unsafe_allow_html=True)

    app_settings = get_settings()

    # 사이드바 (관리자 설정)
    with st.sidebar:
        show_admin_sidebar(app_settings, get_kst_time)
        st.divider()
        app_url = "https://hoya-quiz-studio.streamlit.app/" 
        qr_img = generate_qr_code(app_url)
        st.image(qr_img, width=150)

    # 상단 타이틀 및 유저 선택
    c1, c2 = st.columns([1, 1])
    with c1:
        st.markdown(f'<p class="title-text">{APP_TITLE}</p>', unsafe_allow_html=True)
    with c2:
        if "cached_user_list" not in st.session_state:
            raw_users = get_unique_players() 
            st.session_state.cached_user_list = sorted(raw_users, key=natural_sort_key)

        def on_user_dropdown_change():
            selected = st.session_state.user_dropdown_selection
            if selected != "--- 기존 유저 선택 ---":
                st.session_state.player_name = selected

        st.text_input("아이디", key="player_name", placeholder="이름을 입력하세요")
        st.selectbox(
            "기존 유저 목록",
            ["--- 기존 유저 선택 ---"] + st.session_state.cached_user_list,
            key="user_dropdown_selection",
            on_change=on_user_dropdown_change,
            label_visibility="collapsed"
        )

    st.write("---")

    # [핵심 수정 1] 초기값 설정
    if 'main_menu' not in st.session_state:
        st.session_state.main_menu = TAB_QUIZ

    menu_options = [TAB_QUIZ, TAB_REVIEW, TAB_RECORDS, TAB_RANK, TAB_CHAT, TAB_PARTICIPATION]

    # [핵심 수정 2] 라디오 버튼 렌더링 (더블클릭 버그 해결 & 세로 배치)
    # key="main_menu"를 사용하면 라디오 버튼을 누르는 즉시 session_state.main_menu 값이 변경됨
    st.radio(
        "메뉴를 선택하세요",
        options=menu_options,
        key="main_menu",             # 이 속성이 더블 클릭 버그를 완벽히 해결합니다.
        label_visibility="collapsed" # 라벨 숨김
        # horizontal=True 를 삭제하여 자연스러운 세로 1줄 배치로 복구
    )
    
    # 렌더링 이후 선택된 값을 가져옴
    view_mode = st.session_state.main_menu

    st.write("---")
    
    # 데이터 로드
    all_quizzes = get_all_quizzes()
    season_start = app_settings.get('season_start', '2000-01-01 00:00:00')
    season_res = [r for r in get_all_results() if r.get('Time', '') >= season_start]

    # 세션 상태 초기화
    for k in ['selected_quiz', 'user_answers', 'quiz_finished', 'start_time', 'review_data', 'answered_list', 'quiz_jump', 'results_saved']:
        if k not in st.session_state: 
            st.session_state[k] = "" if k == 'selected_quiz' else [] if k in ['review_data', 'answered_list'] else {} if k == 'user_answers' else False if k in ['quiz_finished', 'quiz_jump', 'results_saved'] else None

    # 선택된 메뉴(라디오 버튼 상태)에 따른 화면 출력
    if view_mode == TAB_RANK:
        show_season_leaderboard(season_res, season_start, app_settings)
    elif view_mode == TAB_REVIEW:
        show_wrong_answer_conquest(st.session_state.player_name, all_quizzes, robust_parse)
    elif view_mode == TAB_CHAT:
        show_chat_room(st.session_state.player_name)
    elif view_mode == TAB_RECORDS:
        show_personal_records(st.session_state.player_name, season_res)
    elif view_mode == TAB_QUIZ:
        show_quiz_area(all_quizzes, season_res, app_settings, st.session_state.player_name, robust_parse, get_kst_time)
    elif view_mode == TAB_PARTICIPATION:
        show_participation_status(season_res)

if __name__ == "__main__":
    if "player_name" not in st.session_state:
        st.session_state.player_name = f"Guest_{random.randint(1000,9999)}"
    main()