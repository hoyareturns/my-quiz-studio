import streamlit as st
import re
import streamlit.components.v1 as components
from database import get_all_quizzes, get_all_results, get_settings, get_chats
from utils import robust_parse
from prompts import VIEW_OPTIONS
from admin import show_admin_sidebar
from pages_logic import show_season_leaderboard, show_chat_room, show_quiz_area
from my_study_app_utils import get_kst_time, generate_qr_code, apply_custom_style

def main():
    # 📌 [1] 페이지 기본 설정 (반드시 가장 먼저 실행!)
    st.set_page_config(
        page_title="우정 파괴소",
        page_icon="logo.png",
        layout="centered"
    )

    # 📌 [2] 모바일 앱 아이콘 강제 주입 로직
    LOGO_URL = "https://raw.githubusercontent.com/hoyareturns/my-quiz-studio/main/logo.png"
    MANIFEST_URL = "https://raw.githubusercontent.com/hoyareturns/my-quiz-studio/main/manifest.json"

    components.html(
        f"""
        <script>
            // iOS 및 안드로이드 홈 화면 아이콘용 태그 주입
            var iconLink = window.parent.document.createElement('link');
            iconLink.rel = 'apple-touch-icon';
            iconLink.href = '{LOGO_URL}';
            window.parent.document.head.appendChild(iconLink);

            // PWA 앱 모드(주소창 숨김 등)를 위한 매니페스트 주입
            var manifestLink = window.parent.document.createElement('link');
            manifestLink.rel = 'manifest';
            manifestLink.href = '{MANIFEST_URL}';
            window.parent.document.head.appendChild(manifestLink);
        </script>
        """,
        height=0
    )

    # 📌 [3] 스타일 및 초기 설정 로드
    apply_custom_style()
    app_settings = get_settings()
    APP_URL = "https://hoya-quiz-studio.streamlit.app"
    
    # 📌 [4] 사이드바 구성
    with st.sidebar:
        st.caption("📱 친구 초대용 QR코드")
        st.image(generate_qr_code(APP_URL), width=120)
        st.divider()
        # 사이드바에서 설정 변경 시 리런(rerun)이 발생함
        show_admin_sidebar(app_settings, get_kst_time)

    # 📌 [5] 메인 화면 구성
    st.title("우정 파괴소")

    if 'player_name' not in st.session_state or not st.session_state.player_name:
        results = get_all_results()
        nums = [int(re.match(r"우정파괴자(\d+)", str(r.get('User',''))).group(1)) for r in results if re.match(r"우정파괴자(\d+)", str(r.get('User','')))]
        st.session_state.player_name = f"우정파괴자{max(nums + [0]) + 1}"
    
    st.session_state.player_name = st.text_input("수험번호", value=st.session_state.player_name)
    
    for k in ['selected_quiz', 'user_answers', 'quiz_finished', 'start_time', 'review_data', 'answered_list']:
        if k not in st.session_state: st.session_state[k] = "" if k == 'selected_quiz' else [] if k in ['review_data', 'answered_list'] else {} if k == 'user_answers' else False if k == 'quiz_finished' else None

    # 📌 [6] 화면 모드 선택 및 동기화
    updated_settings = get_settings() 
    
    saved_view = updated_settings.get('default_view', "퀴즈 선택")
    def_view_idx = VIEW_OPTIONS.index(saved_view) if saved_view in VIEW_OPTIONS else 0
    view_mode = st.radio("탭", VIEW_OPTIONS, horizontal=True, label_visibility="collapsed", index=def_view_idx)
    
    season_start = updated_settings.get('season_start', '2000-01-01 00:00:00')
    all_res = get_all_results()
    season_res = [r for r in all_res if r.get('Time', '') >= season_start]

    # 📌 [7] 탭별 화면 출력
    if view_mode == "구역별 최강자":
        show_season_leaderboard(season_res, season_start)
    elif view_mode == "우정파괴채팅": 
        show_chat_room(st.session_state.player_name)
    else:
        show_quiz_area(get_all_quizzes(), season_res, updated_settings, st.session_state.player_name, robust_parse)

if __name__ == "__main__":
    main()