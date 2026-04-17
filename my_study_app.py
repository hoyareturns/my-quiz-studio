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
        /* 1. 최상단 불필요한 공백 제거 */
        header[data-testid="stHeader"] { display: none !important; }
        .main .block-container { 
            padding-top: 0rem !important; 
            padding-bottom: 1rem !important; 
        }
        
        /* 2. 아이디 입력창 라벨 숨기기 및 간격 미세 조정 */
        div[data-testid="stTextInput"] label { display: none !important; }
        div[data-testid="stTextInput"] { margin-top: 10px !important; }
        
        /* 3. 타이틀 폰트 및 하단 간격 */
        h1 { 
            margin-top: 0px !important; 
            margin-bottom: 5px !important; 
            font-size: 2.2rem !important; 
        }
        
        /* 4. 탭 메뉴 하단에 의도적인 공백 추가 */
        div[data-testid="stTable"] { margin-top: 20px !important; }
        
        /* 5. 아이디 입력창 폰트 스타일 */
        .stTextInput input { font-size: 0.85rem !important; color: #999 !important; }
        </style>
    """, unsafe_allow_html=True)

    app_settings = get_settings()
    APP_URL = "https://hoya-quiz-studio.streamlit.app"
    
    with st.sidebar:
        st.caption("친구 초대용 QR코드")
        st.image(generate_qr_code(APP_URL), width=120)
        st.divider()
        show_admin_sidebar(app_settings, get_kst_time)

    # [3] 최상단 배치: 아이디(수험번호)
    if 'player_name' not in st.session_state or not st.session_state.player_name:
        results = get_all_results()
        nums = [int(re.match(r"우정파괴자(\d+)", str(r.get('User',''))).group(1)) for r in results if re.match(r"우정파괴자(\d+)", str(r.get('User','')))]
        st.session_state.player_name = f"우정파괴자{max(nums + [0]) + 1}"

    st.session_state.player_name = st.text_input("아이디", value=st.session_state.player_name, placeholder="아이디 입력")

    # [4] 메인 타이틀
    st.title("우정 파괴소")

    # [5] 화면 모드 선택 (탭 메뉴)
    updated_settings = get_settings() 
    saved_view = updated_settings.get('default_view', "퀴즈 선택")
    def_view_idx = VIEW_OPTIONS.index(saved_view) if saved_view in VIEW_OPTIONS else 0
    view_mode = st.radio("탭", VIEW_OPTIONS, horizontal=True, label_visibility="collapsed", index=def_view_idx)
    
    # [6] 퀴즈 선택 메뉴 아래에 의도적인 여백 추가
    st.write("") 
    st.write("")

    season_start = updated_settings.get('season_start', '2000-01-01 00:00:00')
    season_res = [r for r in get_all_results() if r.get('Time', '') >= season_start]

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