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
    # [1] 페이지 기본 설정
    st.set_page_config(
        page_title="우정 파괴소",
        page_icon="logo.png",
        layout="centered"
    )

    # [2] 스타일 최적화 (버튼 크기 축소 및 사이드바 버튼 확보)
    apply_custom_style()
    st.markdown("""
        <style>
        /* 상단 여백 제거 및 사이드바 아이콘 노출 */
        header[data-testid="stHeader"] { visibility: hidden; height: 0px; }
        .main .block-container { padding-top: 3.5rem !important; }

        /* 입력창 및 버튼 높이 축소 */
        div[data-testid="stTextInput"] input {
            height: 35px !important;
            padding: 5px !important;
            font-size: 0.9rem !important;
        }
        
        /* 한 줄 배치를 위한 타이틀 스타일 */
        .title-text {
            font-size: 1.6rem !important;
            font-weight: 800;
            margin: 0 !important;
            white-space: nowrap;
        }

        /* 라벨 숨기기 */
        div[data-testid="stTextInput"] label { display: none !important; }
        </style>
    """, unsafe_allow_html=True)

    # [3] 관리자 설정 로드
    app_settings = get_settings()
    
    # [4] 사이드바 (관리자 버튼 << 복구)
    with st.sidebar:
        show_admin_sidebar(app_settings, get_kst_time)
        st.divider()
        st.caption("친구 초대용 QR코드")
        st.image(generate_qr_code("https://hoya-quiz-studio.streamlit.app"), width=100)

    # [5] 아이디 자동 생성 및 세션 초기화
    if 'player_name' not in st.session_state or not st.session_state.player_name:
        results = get_all_results()
        nums = [int(re.match(r"우정파괴자(\d+)", str(r.get('User',''))).group(1)) for r in results if re.match(r"우정파괴자(\d+)", str(r.get('User','')))]
        st.session_state.player_name = f"우정파괴자{max(nums + [0]) + 1}"

    # [6] 상단 레이아웃: 우정 파괴소 아이디입력창 (한 줄 배치)
    t_c1, t_c2 = st.columns([0.4, 0.6])
    with t_c1:
        st.markdown('<p class="title-text">우정 파괴소</p>', unsafe_allow_html=True)
    with t_c2:
        st.session_state.player_name = st.text_input("아이디", value=st.session_state.player_name)

    # [7] 기본 탭 설정 연동 (관리자 모드 설정값 우선 적용)
    # 세션에 모드가 없으면 관리자 설정값을 기본으로 세팅
    default_view_setting = app_settings.get('default_view', "우정퀴즈")
    
    if "main_tab_selector" not in st.session_state:
        try:
            st.session_state.main_tab_selector = default_view_setting
        except:
            st.session_state.main_tab_selector = VIEW_OPTIONS[0]

    view_mode = st.radio(
        "탭", 
        VIEW_OPTIONS, 
        horizontal=True, 
        label_visibility="collapsed", 
        key="main_tab_selector"
    )
    
    st.write("") # 간격용

    # 데이터 로드
    season_start = app_settings.get('season_start', '2000-01-01 00:00:00')
    season_res = [r for r in get_all_results() if r.get('Time', '') >= season_start]

    for k in ['selected_quiz', 'user_answers', 'quiz_finished', 'start_time', 'review_data', 'answered_list']:
        if k not in st.session_state: st.session_state[k] = "" if k == 'selected_quiz' else [] if k in ['review_data', 'answered_list'] else {} if k == 'user_answers' else False if k == 'quiz_finished' else None

    # [8] 화면 출력
    if view_mode == "구역별 최강자":
        show_season_leaderboard(season_res, season_start)
    elif view_mode == "우정파괴채팅": 
        show_chat_room(st.session_state.player_name)
    else:
        show_quiz_area(get_all_quizzes(), season_res, app_settings, st.session_state.player_name, robust_parse)

if __name__ == "__main__":
    main()