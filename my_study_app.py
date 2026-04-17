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
    # 📌 [1] 페이지 기본 설정
    st.set_page_config(
        page_title="우정 파괴소",
        page_icon="logo.png",
        layout="centered"
    )

    # 📌 [2] 스타일 및 초기 설정 로드
    apply_custom_style()
    
    # 🪄 [핵심 추가] 모바일 강제 한 줄 배치 CSS
    st.markdown("""
        <style>
        /* 화면 폭이 좁은 모바일 기기에서 작동 */
        @media (max-width: 768px) {
            /* 타이틀(h1)이 포함된 컬럼 묶음만 강제로 가로(row) 유지 */
            div[data-testid="stHorizontalBlock"]:has(h1) {
                flex-direction: row !important;
                align-items: center !important;
            }
            /* 타이틀 쪽(왼쪽) 영역 넓게 유지 (비율 3) */
            div[data-testid="stHorizontalBlock"]:has(h1) > div[data-testid="column"]:nth-child(1) {
                width: 75% !important;
                flex: 3 1 0% !important;
            }
            /* 버튼 쪽(오른쪽) 영역 좁게 유지 (비율 1) */
            div[data-testid="stHorizontalBlock"]:has(h1) > div[data-testid="column"]:nth-child(2) {
                width: 25% !important;
                flex: 1 1 0% !important;
            }
        }
        </style>
    """, unsafe_allow_html=True)

    app_settings = get_settings()
    APP_URL = "https://hoya-quiz-studio.streamlit.app"
    
    # 📌 [3] 사이드바 구성
    with st.sidebar:
        st.caption("📱 친구 초대용 QR코드")
        st.image(generate_qr_code(APP_URL), width=120)
        st.divider()
        show_admin_sidebar(app_settings, get_kst_time)

    # 📌 [4] 메인 화면 구성 (타이틀 & 퀴즈 생성 버튼 나란히 배치)
    c1, c2 = st.columns([3, 1])
    with c1:
        st.title("우정 파괴소")
    with c2:
        st.write("") # 타이틀과 높이를 맞추기 위한 빈 줄
        st.write("")
        with st.popover("함정 파기", use_container_width=True):
            st.markdown("### 나만의 우정 파괴 퀴즈 생성")
            q_title = st.text_input("퀴즈 제목", placeholder="예: 진주여고 맛집 상식")
            q_topic = st.text_input("퀴즈 주제", placeholder="예: AI가 제안하는 진주시 제일여고 근처 맛집상식")
            
            if st.button("AI 출제 시작", use_container_width=True):
                try:
                    api_key = st.secrets["GEMINI_API_KEY"]
                except KeyError:
                    st.error("서버에 API 키가 설정되지 않았습니다.")
                    api_key = None
                    
                if api_key:
                    if not q_title or not q_topic:
                        st.warning("제목과 주제를 모두 입력하세요.")
                    else:
                        with st.spinner("AI가 지옥의 문제를 생성 중입니다..."):
                            try:
                                generated_text = generate_quiz_with_ai(api_key, q_topic)
                                save_quiz(q_title, "우정퀴즈", generated_text)
                                st.success("함정이 성공적으로 파졌습니다! '우정퀴즈' 탭을 확인하세요.")
                                time.sleep(2)
                                get_all_quizzes.clear() 
                                st.rerun()
                            except Exception as e:
                                st.error(f"생성 실패: {e}")

    # 📌 [5] 수험번호(세션) 초기화
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