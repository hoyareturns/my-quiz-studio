import streamlit as st
import re
from database import get_all_quizzes, get_all_results, get_settings, get_chats
from utils import robust_parse
from prompts import VIEW_OPTIONS
from admin import show_admin_sidebar
from pages_logic import show_season_leaderboard, show_chat_room, show_quiz_area
from my_study_app_utils import get_kst_time, generate_qr_code, apply_custom_style

def main():
    apply_custom_style()
    # 1. 초기 설정 로드
    app_settings = get_settings()
    APP_URL = "https://hoya-quiz-studio.streamlit.app"
    
    with st.sidebar:
        st.caption("📱 친구 초대용 QR코드")
        st.image(generate_qr_code(APP_URL), width=120)
        st.divider()
        # 사이드바에서 설정 변경 시 리런(rerun)이 발생함
        show_admin_sidebar(app_settings, get_kst_time)

    st.title("우정 파괴소")
    
    if 'player_name' not in st.session_state or not st.session_state.player_name:
        results = get_all_results()
        nums = [int(re.match(r"우정파괴자(\d+)", str(r.get('User',''))).group(1)) for r in results if re.match(r"우정파괴자(\d+)", str(r.get('User','')))]
        st.session_state.player_name = f"우정파괴자{max(nums + [0]) + 1}"
    
    st.session_state.player_name = st.text_input("수험번호", value=st.session_state.player_name)
    
    for k in ['selected_quiz', 'user_answers', 'quiz_finished', 'start_time', 'review_data', 'answered_list']:
        if k not in st.session_state: st.session_state[k] = "" if k == 'selected_quiz' else [] if k in ['review_data', 'answered_list'] else {} if k == 'user_answers' else False if k == 'quiz_finished' else None

    # 📌 [핵심 수정] 화면 모드 선택 직전에 설정값을 다시 한 번 확인 (동기화)
    # 사이드바에서 저장한 최신값이 메인 화면 탭 생성에 즉시 반영되도록 함
    updated_settings = get_settings() 
    
    saved_view = updated_settings.get('default_view', "퀴즈 선택")
    def_view_idx = VIEW_OPTIONS.index(saved_view) if saved_view in VIEW_OPTIONS else 0
    view_mode = st.radio("탭", VIEW_OPTIONS, horizontal=True, label_visibility="collapsed", index=def_view_idx)
    
    season_start = updated_settings.get('season_start', '2000-01-01 00:00:00')
    all_res = get_all_results()
    season_res = [r for r in all_res if r.get('Time', '') >= season_start]

    if view_mode == "구역별 최강자":
        show_season_leaderboard(season_res, season_start)
    elif view_mode == "우정파괴채팅": # 여기 이름을 prompts.py와 맞춤
        show_chat_room(st.session_state.player_name)
    else:
        show_quiz_area(get_all_quizzes(), season_res, updated_settings, st.session_state.player_name, robust_parse)

if __name__ == "__main__":
    main()