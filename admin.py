import hmac
import streamlit as st
import pandas as pd
from database import (get_all_quizzes, get_all_results, save_setting, update_quiz, delete_quiz,
                      reset_all_data, restore_database_from_backup, get_backup_file_list)
from prompts import VIEW_OPTIONS
from utils import trigger_google_sheet_backup, generate_default_backup_name, validate_quiz_text, get_secret
from my_study_app_utils import get_kst_time


def configured_admin_password():
    return str(get_secret("ADMIN_PASSWORD", ""))


def show_admin_login(location="admin"):
    if st.session_state.get("is_admin"):
        st.caption("관리자 인증됨")
        return True
    expected = configured_admin_password()
    if not expected:
        st.info("관리자 비밀번호 설정이 필요합니다. 배포 설정의 ADMIN_PASSWORD를 등록해 주세요.")
        return False
    with st.form(f"admin_login_{location}"):
        password = st.text_input("관리자 비밀번호", type="password", key=f"admin_password_{location}")
        login = st.form_submit_button("관리자 인증", use_container_width=True)
    if login:
        if hmac.compare_digest(password.encode(), expected.encode()):
            st.session_state.is_admin = True
            st.rerun()
        else:
            st.error("비밀번호가 일치하지 않습니다.")
    return False


def show_admin_page(settings):
    st.subheader("운영 관리")
    if not show_admin_login():
        return
    if st.button("관리자 로그아웃"):
        st.session_state.is_admin = False
        for key in ("admin_password_admin", "admin_password_author"):
            st.session_state.pop(key, None)
        st.rerun()
    section = st.selectbox("관리할 항목", ["퀴즈 수정·삭제", "참여 기록", "화면 설정", "백업·복구", "시즌 초기화"])
    if section == "퀴즈 수정·삭제":
        show_quiz_editor()
    elif section == "참여 기록":
        rows = get_all_results()
        if rows:
            frame = pd.DataFrame(rows).sort_values("Time", ascending=False)
            st.dataframe(frame.rename(columns={"User":"학습자", "QuizTitle":"퀴즈", "Score":"점수", "Duration":"시간(초)", "Time":"완료 시각"}), hide_index=True, use_container_width=True)
        else:
            st.info("아직 참여 기록이 없습니다.")
    elif section == "화면 설정":
        with st.form("app_settings"):
            current = settings.get("default_view", VIEW_OPTIONS[0])
            view = st.selectbox("처음 열릴 메뉴", VIEW_OPTIONS, index=VIEW_OPTIONS.index(current) if current in VIEW_OPTIONS else 0)
            category = st.text_input("기본 분류", value=str(settings.get("default_category", "공통 역량")))
            categories = st.text_input("분류 목록 (쉼표 구분)", value=str(settings.get("custom_categories", "")))
            try:
                initial_count = max(1, min(1000, int(settings.get("top_achievers_count", 3))))
            except (ValueError, TypeError):
                initial_count = 3
            count = st.number_input("순위표에 표시할 인원", min_value=1, max_value=1000, value=initial_count)
            submit = st.form_submit_button("설정 저장", type="primary", use_container_width=True)
        if submit:
            results = [save_setting(k, v) for k, v in {"default_view":view, "default_category":category.strip(), "custom_categories":categories.strip(), "top_achievers_count":str(count)}.items()]
            if all(ok for ok, _ in results):
                st.success("설정을 저장했습니다.")
            else:
                st.error("일부 설정을 저장하지 못했습니다. 연결 상태를 확인해 주세요.")
    elif section == "백업·복구":
        name = st.text_input("백업 이름", value=generate_default_backup_name())
        if st.button("백업 만들기", use_container_width=True):
            ok, message = trigger_google_sheet_backup(name.strip())
            (st.success if ok else st.error)(message)
            if ok:
                get_backup_file_list.clear()
        st.divider()
        st.caption("백업 목록은 이 버튼을 누를 때만 불러옵니다.")
        if st.button("복구할 백업 목록 불러오기"):
            try:
                st.session_state.backup_choices = get_backup_file_list()
            except Exception:
                st.error("백업 목록을 불러오지 못했습니다.")
        if st.session_state.get("backup_choices"):
            selected = st.selectbox("백업 파일", st.session_state.backup_choices)
            confirmed = st.checkbox("선택한 백업으로 현재 데이터를 덮어쓰는 것을 확인했습니다.")
            if st.button("선택한 백업 복구", disabled=not confirmed):
                if restore_database_from_backup(selected):
                    st.success("데이터를 복구했습니다.")
    else:
        st.warning("퀴즈·성적·오답 기록이 삭제됩니다. 먼저 백업해 주세요.")
        with st.form("reset_season"):
            password = st.text_input("관리자 비밀번호 재입력", type="password")
            confirmed = st.checkbox("데이터 삭제와 새 시즌 시작을 확인했습니다.")
            submitted = st.form_submit_button("데이터 삭제 및 새 시즌 시작")
        if submitted:
            if not confirmed or not hmac.compare_digest(password.encode(), configured_admin_password().encode()):
                st.error("비밀번호와 확인 항목을 확인해 주세요.")
            else:
                ok, msg = reset_all_data()
                if ok:
                    saved, _ = save_setting("season_start", get_kst_time())
                    (st.success if saved else st.warning)(msg if saved else "데이터는 초기화했지만 시즌 시작 시각은 저장하지 못했습니다.")
                else:
                    st.error(msg)


def show_quiz_editor():
    quizzes = get_all_quizzes()
    if not quizzes:
        st.info("등록된 퀴즈가 없습니다. 문제 등록 메뉴에서 첫 퀴즈를 만들어 보세요.")
        return
    index = st.selectbox("수정할 퀴즈", range(len(quizzes)), format_func=lambda i: quizzes[i]["Title"])
    quiz = quizzes[index]
    st.caption("기록과 연결된 제목은 유지됩니다. 분류·문제·정답·해설을 수정할 수 있습니다.")
    with st.form(f"edit_quiz_{index}_{quiz['Title']}"):
        category = st.text_input("분류", value=quiz["Category"])
        content = st.text_area("문제 전체 내용", value=quiz["Content"], height=350)
        submitted = st.form_submit_button("검사 후 수정 저장", type="primary", use_container_width=True)
    if submitted:
        questions, errors = validate_quiz_text(content)
        if not category.strip():
            errors.append("분류를 입력해 주세요.")
        if errors:
            for error in errors:
                st.error(error)
        else:
            try:
                if update_quiz(quiz["Title"], category.strip(), quiz["Title"], content):
                    st.success(f"{len(questions)}문제를 수정했습니다.")
                else:
                    st.error("수정할 퀴즈를 찾지 못했습니다. 새로고침 후 다시 시도해 주세요.")
            except Exception:
                st.error("저장하지 못했습니다. 연결 상태를 확인해 주세요.")
    with st.expander("퀴즈 삭제"):
        confirmed = st.checkbox("이 퀴즈를 삭제하겠습니다.", key=f"delete_confirm_{quiz['Title']}")
        if st.button("퀴즈 삭제", disabled=not confirmed):
            if delete_quiz(quiz["Title"]):
                st.rerun()
