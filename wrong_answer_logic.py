import hashlib
import streamlit as st
from database import get_wrong_answers_by_user, update_wrong_answer_status, get_all_users_with_wrongs
from utils import check_subjective_answer


def show_wrong_answer_conquest(current_player, all_quizzes, robust_parse):
    st.subheader("틀린 문제, 한 번 더")
    st.caption("한 문제씩 복습해 보세요. 정답을 맞히면 오답 목록에서 빠집니다.")
    target = current_player
    if st.session_state.get("is_admin"):
        users = get_all_users_with_wrongs()
        if users:
            target = st.selectbox("복습할 학습자", users, index=users.index(current_player) if current_player in users else 0)
    records = get_wrong_answers_by_user(target)
    if st.session_state.get("review_flash"):
        st.success(st.session_state.pop("review_flash"))
    if not records:
        st.info("남아 있는 오답이 없습니다. 새로운 퀴즈에 도전해 보세요.")
        return
    st.caption(f"{target}님 · 남은 오답 {len(records)}개")
    selected = st.selectbox("복습할 문제", range(len(records)), format_func=lambda i: f"{i+1}. {records[i].get('QuestionText', '')[:60]}")
    record = records[selected]
    title, text = record.get("QuizTitle"), str(record.get("QuestionText", "")).strip()
    quiz = next((q for q in all_quizzes if q["Title"] == title), None)
    question = next((q for q in robust_parse(quiz["Content"]) if q["q"].strip() == text), None) if quiz else None
    key = hashlib.sha256(f"{target}|{title}|{text}|{record.get('CreatedAt')}|{selected}".encode()).hexdigest()[:16]
    st.caption(f"출처: {title}")
    if not question:
        st.write(text)
        st.warning("원본 문제가 수정되었거나 삭제되어 이 항목은 다시 채점할 수 없습니다. 최신 퀴즈를 풀거나 이 항목을 정리해 주세요.")
        if st.button("변경된 오답 항목 정리", key=f"archive_{key}"):
            if update_wrong_answer_status(target, title, text, "문제 변경"):
                st.session_state.review_flash = "변경된 항목을 오답 목록에서 정리했습니다."
                st.rerun()
            else:
                st.error("정리하지 못했습니다. 다시 시도해 주세요.")
        return
    with st.form(f"review_{key}"):
        if question["p"]:
            st.info(question["p"])
        st.markdown(f"### {question['q']}")
        if question["o"] == ["주관식"]:
            answer = st.text_input("정답 입력")
        else:
            answer = st.radio("보기 선택", question["o"], index=None)
        submit = st.form_submit_button("정답 확인", type="primary", use_container_width=True)
    if submit:
        if answer is None or not str(answer).strip():
            st.warning("답을 입력하거나 선택해 주세요.")
            return
        correct = check_subjective_answer(answer, question["a"]) if question["o"] == ["주관식"] else answer == question["o"][question["a"]]
        if correct:
            if update_wrong_answer_status(target, title, text, "정복"):
                st.session_state.review_flash = "정답입니다! 오답 하나를 해결했어요."
                st.rerun()
            else:
                st.error("정답이지만 기록을 저장하지 못했습니다. 다시 시도해 주세요.")
        else:
            st.warning("정답이 아닙니다. 해설을 확인하고 다시 도전해 보세요.")
            st.info(question["e"])
