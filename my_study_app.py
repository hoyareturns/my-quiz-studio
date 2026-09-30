import streamlit as st
from database import get_all_quizzes, get_all_results, get_settings, get_unique_players, get_gspread_client, clear_data_cache
from utils import robust_parse, natural_sort_key
from prompts import APP_TITLE, TAB_QUIZ, TAB_REVIEW, TAB_RECORDS, TAB_RANK, TAB_CHAT, TAB_PARTICIPATION, TAB_AUTHOR
from my_study_app_utils import get_kst_time, apply_custom_style
from admin import show_admin_page
from author_page import show_author_page
from quiz_page import show_quiz_area
from leaderboard_page import show_season_leaderboard
from chat_page import show_chat_room
from wrong_answer_logic import show_wrong_answer_conquest
from personal_record_logic import show_personal_records
from participation_page import show_participation_status


def main():
    st.set_page_config(page_title=APP_TITLE, page_icon="logo.png", layout="centered", initial_sidebar_state="collapsed")
    apply_custom_style()
    st.session_state.setdefault("player_name", "")
    st.session_state.setdefault("is_admin", False)
    st.session_state.setdefault("selected_quiz", "")
    st.session_state.setdefault("quiz_finished", False)
    st.session_state.setdefault("start_time", None)
    st.session_state.setdefault("user_answers", {})
    st.session_state.setdefault("results_saved", False)
    st.session_state.setdefault("review_data", [])
    active = st.session_state.start_time is not None and not st.session_state.quiz_finished
    settings = get_settings()
    options = [TAB_QUIZ, TAB_REVIEW, TAB_RECORDS, TAB_AUTHOR, TAB_RANK, TAB_PARTICIPATION, TAB_CHAT, "관리"]
    if "main_menu" not in st.session_state:
        preferred = settings.get("default_view", TAB_QUIZ)
        st.session_state.main_menu = preferred if preferred in options else TAB_QUIZ

    st.markdown('<div class="app-heading"><span class="eyebrow">매일 조금씩, 더 단단한 실력</span><h1>스마트 평가 센터</h1><p>풀어 보고, 돌아보고, 다음 단계로.</p></div>', unsafe_allow_html=True)
    with st.expander("학습자 이름 · 내 계정", expanded=not bool(st.session_state.player_name) and st.session_state.main_menu == TAB_QUIZ):
        st.text_input("학습자 이름", key="player_name", placeholder="기록에 사용할 이름을 입력하세요", disabled=active)
        st.caption("이름은 성적과 오답을 구분하는 용도입니다. 본인 인증용 로그인은 아닙니다.")
        if not active and st.checkbox("기존 학습자 목록에서 선택", key="show_existing_users"):
            users = sorted(get_unique_players(), key=natural_sort_key)
            def select_user():
                if st.session_state.existing_user:
                    st.session_state.player_name = st.session_state.existing_user
            st.selectbox("기존 학습자", [""] + users, key="existing_user", on_change=select_user)
    if st.session_state.player_name:
        st.caption(f"현재 학습자: {st.session_state.player_name}" + (" · 풀이 중에는 이름과 메뉴가 고정됩니다." if active else ""))

    st.radio("메뉴", options, key="main_menu", horizontal=True, label_visibility="collapsed", disabled=active)
    st.divider()
    with st.sidebar:
        st.subheader("도움말")
        st.write("문제 등록 메뉴에서 요청문을 복사한 뒤, GPT의 답변을 붙여넣어 퀴즈를 만들 수 있습니다.")
        st.caption("앱은 생성형 AI API를 호출하지 않습니다. 외부 GPT 서비스는 사용 중인 계정의 요금제를 따릅니다.")
        if st.button("최신 데이터 불러오기", use_container_width=True, disabled=active):
            clear_data_cache()
            st.rerun()
        st.caption("다른 사용자의 변경 사항은 잠시 후 반영됩니다. 바로 확인하려면 새로고침해 주세요.")
    if get_gspread_client() is None:
        st.info("Google Sheets 연결 설정이 필요합니다. 문제 등록 메뉴의 요청문 작성과 미리보기는 먼저 사용할 수 있습니다.")

    view = st.session_state.main_menu
    if view == TAB_AUTHOR:
        show_author_page(settings)
    elif view == "관리":
        show_admin_page(settings)
    elif view == TAB_QUIZ:
        quizzes = [st.session_state.quiz_snapshot] if active and st.session_state.get("quiz_snapshot") else get_all_quizzes()
        show_quiz_area(quizzes, None, settings, st.session_state.player_name, robust_parse, get_kst_time)
    elif view == TAB_REVIEW:
        if not st.session_state.player_name.strip():
            st.info("상단에서 학습자 이름을 입력해 주세요.")
        else:
            show_wrong_answer_conquest(st.session_state.player_name, get_all_quizzes(), robust_parse)
    elif view == TAB_RECORDS:
        show_personal_records(st.session_state.player_name, get_all_results())
    elif view == TAB_RANK:
        show_season_leaderboard(get_all_results(), settings.get("season_start") or "2000-01-01", settings)
    elif view == TAB_PARTICIPATION:
        show_participation_status(get_all_results(), get_all_quizzes())
    elif view == TAB_CHAT:
        show_chat_room(st.session_state.player_name)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        st.error("화면을 불러오지 못했습니다. 잠시 후 다시 시도하거나 Google Sheets 연결 설정을 확인해 주세요.")
        import logging
        logging.getLogger(__name__).exception("App request failed")
