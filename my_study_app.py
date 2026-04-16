import streamlit as st
import re
from database import get_all_quizzes, get_all_results, get_settings, get_chats
from utils import robust_parse
from prompts import VIEW_OPTIONS
from admin import show_admin_sidebar
# 📌 새로 분리한 탭 로직들 불러오기
from pages_logic import show_season_leaderboard, show_chat_room, show_quiz_area
# 📌 기존 유틸 함수들
from my_study_app_utils import get_kst_time, generate_qr_code, apply_custom_style

def main():
    apply_custom_style()
    app_settings = get_settings()
    APP_URL = "https://hoya-quiz-studio.streamlit.app"
    
    with st.sidebar:
        st.caption("📱 친구 초대용 QR코드")
        st.image(generate_qr_code(APP_URL), width=120)
        st.divider()
        show_admin_sidebar(app_settings, get_kst_time)

    st.title("우정 파괴소")
    
    # 수험번호 발급 및 세션 초기화
    if 'player_name' not in st.session_state or not st.session_state.player_name:
        results = get_all_results()
        nums = [int(re.match(r"우정파괴자(\d+)", str(r.get('User',''))).group(1)) for r in results if re.match(r"우정파괴자(\d+)", str(r.get('User','')))]
        st.session_state.player_name = f"우정파괴자{max(nums + [0]) + 1}"
    
    st.session_state.player_name = st.text_input("수험번호", value=st.session_state.player_name)
    
    for k in ['selected_quiz', 'user_answers', 'quiz_finished', 'start_time', 'review_data', 'answered_list']:
        if k not in st.session_state: st.session_state[k] = "" if k == 'selected_quiz' else [] if k in ['review_data', 'answered_list'] else {} if k == 'user_answers' else False if k == 'quiz_finished' else None

    # 화면 모드 선택
    saved_view = app_settings.get('default_view', "퀴즈 선택")
    def_view_idx = VIEW_OPTIONS.index(saved_view) if saved_view in VIEW_OPTIONS else 0
    view_mode = st.radio("탭", VIEW_OPTIONS, horizontal=True, label_visibility="collapsed", index=def_view_idx)
    
    # 시즌 데이터 준비
    season_start = app_settings.get('season_start', '2000-01-01 00:00:00')
    all_res = get_all_results()
    season_res = [r for r in all_res if r.get('Time', '') >= season_start]

    # 📌 외부 파일에서 불러온 함수들 실행
    if view_mode == "구역별 최강자":
        show_season_leaderboard(season_res, season_start)
    elif view_mode == "우정파괴창":
        show_chat_room(st.session_state.player_name)
    else:
        show_quiz_area(get_all_quizzes(), season_res, app_settings, st.session_state.player_name, robust_parse)

if __name__ == "__main__":
    main()