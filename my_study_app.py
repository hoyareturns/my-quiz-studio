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

    # [2] 스타일 최적화 (버튼 크기 축소 및 간격 제거)
    apply_custom_style()
    st.markdown("""
        <style>
        /* 상단 여백 제거 */
        header[data-testid="stHeader"] { visibility: hidden; height: 0px; }
        .main .block-container { padding-top: 2rem !important; }

        /* 입력창 및 버튼 높이 대폭 축소 */
        div[data-testid="stTextInput"] input {
            height: 30px !important;
            padding: 5px !important;
            font-size: 0.9rem !important;
        }
        div[data-testid="stButton"] button {
            height: 30px !important;
            padding-top: 0px !important;
            padding-bottom: 0px !important;
            line-height: 30px !important;
            font-size: 0.8rem !important;
        }

        /* 한 줄 배치용 컨테이너 */
        .header-row {
            display: flex;
            align-items: center;
            gap: 10px;
            margin-bottom: 10px;
        }
        .title-text {
            font-size: 1.5rem !important;
            font-weight: 800;
            margin: 0 !important;
        }

        /* 라벨 숨기기 */
        div[data-testid="stTextInput"] label { display: none !important; }
        </style>
    """, unsafe_allow_html=True)

    app_settings = get_settings()
    
    # [3] 사이드바
    with st.sidebar:
        show_admin_sidebar(app_settings, get_kst_time)
        st.divider()
        st.caption("친구 초대용 QR코드")
        st.image(generate_qr_code("https://hoya-quiz-studio.streamlit.app"), width=100)

    # [4] 아이디 자동 생성
    if 'player_name' not in st.session_state or not st.session_state.player_name:
        results = get_all_results()
        nums = [int(re.match(r"우정파괴자(\d+)", str(r.get('User',''))).group(1)) for r in results if re.match(r"우정파괴자(\d+)", str(r.get('User','')))]
        st.session_state.player_name = f"우정파괴자{max(nums + [0]) + 1}"

    # [5] 타이틀 및 아이디 한 줄 배치 (콜론 제거)
    c1, c2 = st.columns([0.5, 0.5])
    with c1:
        st.markdown('<p class="title-text">우정 파괴소</p>', unsafe_allow_html=True)
    with c2:
        st.session_state.player_name = st.text_input("아이디", value=st.session_state.player_name)

    # [6] 기본 탭 설정 (관리자 설정값 반영 로직 강화)
    updated_settings = get_settings()
    # 관리자 모드에서 설정한 기본 탭 이름을 가져옴
    default_tab_name = updated_settings.get('default_view', "우정퀴즈")
    
    # VIEW_OPTIONS에서 해당 탭의 인덱스를 찾음 (못 찾으면 0번)
    try:
        def_idx = VIEW_OPTIONS.index(default_tab_name)
    except ValueError:
        def_idx = 0

    view_mode = st.radio(
        "탭", 
        VIEW_OPTIONS, 
        horizontal=True, 
        label_visibility="collapsed", 
        index=def_idx,
        key="main_tab_selector"
    )
    
    st.write("") # 미세 간격

    # 데이터 로드
    season_start = updated_settings.get('season_start', '2000-01-01 00:00:00')
    season_res = [r for r in get_all_results() if r.get('Time', '') >= season_start]

    for k in ['selected_quiz', 'user_answers', 'quiz_finished', 'start_time', 'review_data', 'answered_list']:
        if k not in st.session_state: st.session_state[k] = "" if k == 'selected_quiz' else [] if k in ['review_data', 'answered_list'] else {} if k == 'user_answers' else False if k == 'quiz_finished' else None

    # [7] 화면 출력
    if view_mode == "구역별 최강자":
        show_season_leaderboard(season_res, season_start)
    elif view_mode == "우정파괴채팅": 
        show_chat_room(st.session_state.player_name)
    else:
        show_quiz_area(get_all_quizzes(), season_res, updated_settings, st.session_state.player_name, robust_parse)

if __name__ == "__main__":
    main()