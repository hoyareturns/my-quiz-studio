import streamlit as st
import re
import time
import random

# 1. 공통 데이터 및 유틸리티 관련
from database import get_all_quizzes, get_all_results, get_settings, get_chats, save_quiz, get_unique_players
from utils import robust_parse, generate_quiz_with_ai, trigger_google_sheet_backup, natural_sort_key 
from prompts import VIEW_OPTIONS, APP_TITLE, TAB_QUIZ, TAB_REVIEW, TAB_RECORDS, TAB_RANK, TAB_CHAT, DEFAULT_CATEGORY, TAB_PARTICIPATION
from my_study_app_utils import get_kst_time, generate_qr_code, apply_custom_style

# 2. 관리자 화면 관련
from admin import show_admin_sidebar

# 3. [개별 분리된] 페이지 로직 관련
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
            raw_users = get_unique_players() 
            st.session_state.cached_user_list = sorted(raw_users, key=natural_sort_key)

        # 2. 드롭박스 선택 시 실행될 콜백 함수
        def on_user_dropdown_change():
            selected = st.session_state.user_dropdown_selection
            if selected != "--- 기존 유저 선택 ---":
                st.session_state.player_name = selected

        # 3. 아이디 직접 입력창
        st.text_input("아이디", key="player_name", placeholder="이름을 입력하세요")

        # 4. 기존 유저 선택 드롭박스 (입력창 바로 아래 배치)
        st.selectbox(
            "기존 유저 목록",
            ["--- 기존 유저 선택 ---"] + st.session_state.cached_user_list,
            key="user_dropdown_selection",
            on_change=on_user_dropdown_change,
            label_visibility="collapsed"
        )

    st.write(""); st.write(""); st.write("")

    if 'main_menu' not in st.session_state:
        st.session_state.main_menu = TAB_QUIZ

    # --- 1. 데이터 로드 및 유효 카테고리 추출 ---
    all_quizzes = get_all_quizzes()

    # 실제로 퀴즈가 1개 이상 존재하는 카테고리만 추출
    available_cats = sorted(list(set(
        q.get('Category', DEFAULT_CATEGORY) for q in all_quizzes if q.get('Category')
    )))

    # 세션 스테이트 초기화 (초기 접속 시 모든 카테고리 활성화)
    if 'active_categories' not in st.session_state:
        st.session_state.active_categories = available_cats.copy()

    # --- 2. 카테고리 선택 영역 (토글 UI) ---
    st.subheader("📁 카테고리 필터 (스위치)")
    if not available_cats:
        st.info("현재 등록된 퀴즈 카테고리가 없습니다.")
    else:
        # 가로로 토글 배치
        cat_cols = st.columns(min(len(available_cats), 4)) 
        for i, cat in enumerate(available_cats):
            with cat_cols[i % 4]:
                is_on = st.toggle(cat, value=(cat in st.session_state.active_categories), key=f"tog_{cat}")
                
                if is_on and cat not in st.session_state.active_categories:
                    st.session_state.active_categories.append(cat)
                elif not is_on and cat in st.session_state.active_categories:
                    st.session_state.active_categories.remove(cat)

    st.write("---")

    # --- [핵심 수정 부분] 토글 스위치가 켜진 카테고리의 퀴즈만 필터링 ---
    filtered_quizzes = [
        q for q in all_quizzes 
        if q.get('Category', DEFAULT_CATEGORY) in st.session_state.active_categories
    ]

    # --- 3. 메뉴 버튼 배치 ---
    m_col1, m_col2 = st.columns(2)
    def menu_btn(label, col):
        with col:
            is_selected = st.session_state.get('main_menu') == label
            if st.button(label, use_container_width=True, type="primary" if is_selected else "secondary"):
                st.session_state.main_menu = label
                st.rerun()

    menu_btn(TAB_QUIZ, m_col1);          menu_btn(TAB_REVIEW, m_col2)      # 1행
    menu_btn(TAB_RECORDS, m_col1);       menu_btn(TAB_RANK, m_col2)        # 2행
    menu_btn(TAB_CHAT, m_col1);          menu_btn(TAB_PARTICIPATION, m_col2) # 3행

    view_mode = st.session_state.main_menu
    st.write("---")
    
    season_start = app_settings.get('season_start', '2000-01-01 00:00:00')
    season_res = [r for r in get_all_results() if r.get('Time', '') >= season_start]

    for k in ['selected_quiz', 'user_answers', 'quiz_finished', 'start_time', 'review_data', 'answered_list', 'quiz_jump', 'results_saved']:
        if k not in st.session_state: 
            st.session_state[k] = "" if k == 'selected_quiz' else [] if k in ['review_data', 'answered_list'] else {} if k == 'user_answers' else False if k in ['quiz_finished', 'quiz_jump', 'results_saved'] else None

    # --- 4. 탭 이동 및 필터링된 데이터 전달 ---
    # [핵심 수정 부분] get_all_quizzes() 대신 필터링이 완료된 filtered_quizzes를 전달합니다.
    if view_mode == TAB_RANK:
        show_season_leaderboard(season_res, season_start, app_settings)
    elif view_mode == TAB_REVIEW:
        show_wrong_answer_conquest(st.session_state.player_name, filtered_quizzes, robust_parse) # 변경됨
    elif view_mode == TAB_CHAT:
        show_chat_room(st.session_state.player_name)
    elif view_mode == TAB_RECORDS:
        show_personal_records(st.session_state.player_name, season_res)
    elif view_mode == TAB_QUIZ:
        show_quiz_area(filtered_quizzes, season_res, app_settings, st.session_state.player_name, robust_parse, get_kst_time) # 변경됨
    elif view_mode == TAB_PARTICIPATION:
        show_participation_status(season_res)

if __name__ == "__main__":
    if "player_name" not in st.session_state:
        st.session_state.player_name = f"Guest_{random.randint(1000,9999)}"
    main()