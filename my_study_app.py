import streamlit as st
import re
import time
from database import get_all_quizzes, get_all_results, get_settings, get_chats, save_quiz
from utils import robust_parse, generate_quiz_with_ai
from prompts import VIEW_OPTIONS
from admin import show_admin_sidebar
from pages_logic import show_season_leaderboard, show_chat_room, show_quiz_area
from my_study_app_utils import get_kst_time, generate_qr_code, apply_custom_style

def main():
    st.set_page_config(
        page_title="우정 파괴소",
        page_icon="logo.png",
        layout="centered"
    )

    apply_custom_style()
    st.markdown("""
        <style>
        /* 1. 사이드바 아이콘(>)을 노출시키기 위해 상단 여백을 대폭 늘림 (3.5rem -> 4.5rem) */
        header[data-testid="stHeader"] { visibility: hidden; height: 0px; }
        .main .block-container { padding-top: 4.5rem !important; }

        /* 2. 아이디 입력창 디자인 */
        div[data-testid="stTextInput"] label { display: none !important; }
        div[data-testid="stTextInput"] input {
            height: 35px !important;
            padding: 2px 8px !important;
            font-size: 0.9rem !important;
            border: none !important;
            border-bottom: 1px solid #ddd !important;
            border-radius: 0 !important;
        }
        
        /* 3. 타이틀 한 줄 고정 및 밀림 방지 */
        .title-text {
            font-size: 1.6rem !important;
            font-weight: 800;
            margin: 0 !important;
            white-space: nowrap;
        }
        </style>
    """, unsafe_allow_html=True)

    app_settings = get_settings()
    
    with st.sidebar:
        # 관리자 비밀번호 입력창 등이 있는 사이드바 호출
        show_admin_sidebar(app_settings, get_kst_time)
        st.divider()
        st.caption("친구 초대용 QR코드")
        st.image(generate_qr_code("https://hoya-quiz-studio.streamlit.app"), width=100)

    if 'player_name' not in st.session_state or not st.session_state.player_name:
        results = get_all_results()
        nums = [int(re.match(r"우정파괴자(\d+)", str(r.get('User',''))).group(1)) for r in results if re.match(r"우정파괴자(\d+)", str(r.get('User','')))]
        st.session_state.player_name = f"우정파괴자{max(nums + [0]) + 1}"

    # 타이틀과 아이디 입력창 한 줄 배치
    c1, c2 = st.columns([0.45, 0.55])
    with c1:
        st.markdown('<p class="title-text">우정 파괴소</p>', unsafe_allow_html=True)
    with c2:
        st.session_state.player_name = st.text_input("아이디", value=st.session_state.player_name)

    # 기본 탭 설정 (관리자 설정값 연동)
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
    
    # 퀴즈 선택 위쪽에 공백 추가
    st.write("") 

    season_start = app_settings.get('season_start', '2000-01-01 00:00:00')
    season_res = [r for r in get_all_results() if r.get('Time', '') >= season_start]

    for k in ['selected_quiz', 'user_answers', 'quiz_finished', 'start_time', 'review_data', 'answered_list']:
        if k not in st.session_state: st.session_state[k] = "" if k == 'selected_quiz' else [] if k in ['review_data', 'answered_list'] else {} if k == 'user_answers' else False if k == 'quiz_finished' else None

    if view_mode == "구역별 최강자":
        show_season_leaderboard(season_res, season_start)
    elif view_mode == "우정파괴채팅": 
        show_chat_room(st.session_state.player_name)
    else:
        # 퀴즈 영역 호출
        show_quiz_area(get_all_quizzes(), season_res, app_settings, st.session_state.player_name, robust_parse)

if __name__ == "__main__":
    main()