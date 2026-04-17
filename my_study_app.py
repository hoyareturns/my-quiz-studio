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

    # [2] 스타일 최적화 (버튼/입력창 크기 최소화)
    apply_custom_style()
    st.markdown("""
        <style>
        /* 상단 바 및 사이드바 버튼 확보 */
        header[data-testid="stHeader"] { visibility: hidden; height: 0px; }
        .main .block-container { padding-top: 3rem !important; }

        /* 입력창 및 버튼 높이와 너비 최소화 */
        div[data-testid="stTextInput"] input {
            height: 28px !important;
            padding: 2px 5px !important;
            font-size: 0.85rem !important;
            border-radius: 4px !important;
        }
        
        /* 탭 버튼(radio) 크기 축소 */
        div[data-testid="stWidgetLabel"] p { font-size: 0.8rem !important; }

        /* 한 줄 구성을 위한 컬럼 간격 조정 */
        [data-testid="column"] {
            display: flex;
            align-items: center;
            justify-content: flex-start;
        }

        /* 라벨 완전 제거 */
        label { display: none !important; }
        </style>
    """, unsafe_allow_html=True)

    # [3] 관리자 설정 로드
    app_settings = get_settings()
    
    # [4] 사이드바 (관리자 버튼 노출)
    with st.sidebar:
        show_admin_sidebar(app_settings, get_kst_time)
        st.divider()
        st.caption("친구 초대용 QR코드")
        st.image(generate_qr_code("https://hoya-quiz-studio.streamlit.app"), width=100)

    # [5] 아이디 자동 생성
    if 'player_name' not in st.session_state or not st.session_state.player_name:
        results = get_all_results()
        nums = [int(re.match(r"우정파괴자(\d+)", str(r.get('User',''))).group(1)) for r in results if re.match(r"우정파괴자(\d+)", str(r.get('User','')))]
        st.session_state.player_name = f"우정파괴자{max(nums + [0]) + 1}"

    # [6] 상단 레이아웃: 우정 파괴소 [입력창] (콜론 제거 및 너비 압축)
    c1, c2 = st.columns([0.4, 0.6])
    with c1:
        st.markdown("<h2 style='margin:0; font-size:1.5rem; white-space:nowrap;'>우정 파괴소</h2>", unsafe_allow_html=True)
    with c2:
        st.session_state.player_name = st.text_input("아이디", value=st.session_state.player_name)

    # [7] 기본 탭 및 퀴즈 카테고리 연동 (관리자 모드 설정 반영)
    default_view = app_settings.get('default_view', "퀴즈 선택")
    def_idx = VIEW_OPTIONS.index(default_view) if default_view in VIEW_OPTIONS else 0

    view_mode = st.radio(
        "메뉴탭", 
        VIEW_OPTIONS, 
        horizontal=True, 
        label_visibility="collapsed", 
        index=def_idx,
        key="main_tab_selector"
    )
    
    st.write("") # 미세 간격

    # 데이터 준비
    season_start = app_settings.get('season_start', '2000-01-01 00:00:00')
    season_res = [r for r in get_all_results() if r.get('Time', '') >= season_start]

    for k in ['selected_quiz', 'user_answers', 'quiz_finished', 'start_time', 'review_data', 'answered_list']:
        if k not in st.session_state: st.session_state[k] = "" if k == 'selected_quiz' else [] if k in ['review_data', 'answered_list'] else {} if k == 'user_answers' else False if k == 'quiz_finished' else None

    # [8] 화면 출력 (세션 상태에 따른 카테고리 전달)
    if view_mode == "구역별 최강자":
        show_season_leaderboard(season_res, season_start)
    elif view_mode == "우정파괴채팅": 
        show_chat_room(st.session_state.player_name)
    else:
        # 퀴즈 영역 호출 시 app_settings를 함께 전달하여 '처음 열릴 카테고리' 연동
        show_quiz_area(get_all_quizzes(), season_res, app_settings, st.session_state.player_name, robust_parse)

if __name__ == "__main__":
    main()