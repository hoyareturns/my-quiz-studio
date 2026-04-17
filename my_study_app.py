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

    # [2] 스타일 및 여백 최적화 CSS
    apply_custom_style()
    st.markdown("""
        <style>
        /* 1. 사이드바 아이콘 보존 및 상단 여백 제거 */
        .main .block-container { 
            padding-top: 3.5rem !important; 
            padding-bottom: 1rem !important; 
        }
        
        /* 2. 기존 입력창 라벨 숨기기 */
        div[data-testid="stTextInput"] label { display: none !important; }
        
        /* 3. 타이틀과 아이디 한 줄 배치를 위한 커스텀 스타일 */
        .header-box {
            display: flex;
            align-items: center;
            justify-content: flex-start;
            gap: 10px;
            margin-bottom: 15px;
        }
        .main-title {
            font-size: 1.8rem !important;
            font-weight: 800;
            margin: 0 !important;
            white-space: nowrap;
        }
        .id-colon {
            font-size: 1.5rem;
            font-weight: bold;
            color: #333;
        }
        
        /* 4. 입력창 슬림화 및 위치 조정 */
        div[data-testid="stHorizontalBlock"] {
            align-items: center !important;
        }
        
        /* 모바일 대응: 화면 폭에 따른 크기 조정 */
        @media (max-width: 768px) {
            .main-title { font-size: 1.4rem !important; }
            .id-colon { font-size: 1.2rem; }
        }
        </style>
    """, unsafe_allow_html=True)

    app_settings = get_settings()
    APP_URL = "https://hoya-quiz-studio.streamlit.app"
    
    # [3] 사이드바 (관리자 모드 및 QR코드)
    # 상단 패딩을 3.5rem으로 늘려 사이드바 버튼(>>)이 가려지지 않게 했습니다.
    with st.sidebar:
        show_admin_sidebar(app_settings, get_kst_time)
        st.divider()
        st.caption("친구 초대용 QR코드")
        st.image(generate_qr_code(APP_URL), width=120)

    # [4] 아이디 자동 생성 로직
    if 'player_name' not in st.session_state or not st.session_state.player_name:
        results = get_all_results()
        nums = [int(re.match(r"우정파괴자(\d+)", str(r.get('User',''))).group(1)) for r in results if re.match(r"우정파괴자(\d+)", str(r.get('User','')))]
        st.session_state.player_name = f"우정파괴자{max(nums + [0]) + 1}"

    # [5] 우정 파괴소 : 아이디 한 줄 배치 구현
    # columns의 비율을 조절하여 타이틀 뒤에 바로 콜론과 입력창이 붙게 함
    c1, c2, c3 = st.columns([0.35, 0.05, 0.6])
    with c1:
        st.markdown('<p class="main-title">우정 파괴소</p>', unsafe_allow_html=True)
    with c2:
        st.markdown('<p class="id-colon">:</p>', unsafe_allow_html=True)
    with c3:
        st.session_state.player_name = st.text_input("아이디입력", value=st.session_state.player_name)

    # [6] 화면 모드 선택 (탭 메뉴)
    updated_settings = get_settings() 
    saved_view = updated_settings.get('default_view', "퀴즈 선택")
    def_view_idx = VIEW_OPTIONS.index(saved_view) if saved_view in VIEW_OPTIONS else 0
    view_mode = st.radio("탭", VIEW_OPTIONS, horizontal=True, label_visibility="collapsed", index=def_view_idx)
    
    # 탭 하단 여백 추가
    st.write("") 
    st.write("")

    season_start = updated_settings.get('season_start', '2000-01-01 00:00:00')
    season_res = [r for r in get_all_results() if r.get('Time', '') >= season_start]

    # 세션 변수 초기화
    for k in ['selected_quiz', 'user_answers', 'quiz_finished', 'start_time', 'review_data', 'answered_list']:
        if k not in st.session_state: st.session_state[k] = "" if k == 'selected_quiz' else [] if k in ['review_data', 'answered_list'] else {} if k == 'user_answers' else False if k == 'quiz_finished' else None

    # [7] 탭별 화면 출력
    if view_mode == "구역별 최강자":
        show_season_leaderboard(season_res, season_start)
    elif view_mode == "우정파괴채팅": 
        show_chat_room(st.session_state.player_name)
    else:
        show_quiz_area(get_all_quizzes(), season_res, updated_settings, st.session_state.player_name, robust_parse)

if __name__ == "__main__":
    main()