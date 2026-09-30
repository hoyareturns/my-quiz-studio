import time
import uuid
import streamlit as st
from database import save_result, save_wrong_answers, save_wrong_answers_detailed, get_all_results
from utils import check_subjective_answer, natural_sort_key, validate_quiz_text


def reset_attempt():
    st.session_state.update(selected_quiz="", quiz_snapshot=None, start_time=None,
                            quiz_finished=False, user_answers={}, results_saved=False,
                            review_data=[], save_steps={}, pending_result=None)


def select_quiz(quiz):
    reset_attempt()
    st.session_state.selected_quiz = quiz["Title"]
    st.session_state.quiz_snapshot = dict(quiz)


def show_quiz_area(quizzes, season_res, app_settings, player_name, robust_parse_func, get_kst_time):
    if st.session_state.selected_quiz:
        item = st.session_state.get("quiz_snapshot") or next((q for q in quizzes if q["Title"] == st.session_state.selected_quiz), None)
        if item:
            render_quiz_detail(item, season_res, app_settings, player_name, robust_parse_func, get_kst_time)
            return
        reset_attempt()
    st.subheader("오늘은 무엇을 배워 볼까요?")
    st.caption("분류를 고르거나 제목을 검색해 퀴즈를 찾아보세요.")
    if not quizzes:
        st.info("아직 등록된 퀴즈가 없습니다. 문제 등록 메뉴에서 첫 퀴즈를 준비해 보세요.")
        return
    categories = sorted({str(q.get("Category") or "미분류") for q in quizzes}, key=natural_sort_key)
    c1, c2 = st.columns([1, 2])
    with c1:
        preferred = app_settings.get("default_category")
        options = ["전체"] + categories
        category = st.selectbox("분류", options, index=options.index(preferred) if preferred in options else 0, key="quiz_filter")
    with c2:
        search = st.text_input("퀴즈 검색", placeholder="제목이나 키워드를 입력하세요", key="quiz_search")
    visible = sorted([q for q in quizzes if (category == "전체" or str(q.get("Category") or "미분류") == category) and search.casefold().strip() in str(q["Title"]).casefold()], key=lambda q: natural_sort_key(q["Title"]))
    st.caption(f"{len(visible)}개의 퀴즈")
    if not visible:
        st.info("검색 결과가 없습니다. 검색어나 분류를 바꿔 보세요.")
    for index, quiz in enumerate(visible):
        with st.container(border=True):
            st.caption(str(quiz.get("Category") or "미분류"))
            st.button(quiz["Title"], key=f"quiz_pick_{index}", use_container_width=True, on_click=select_quiz, args=(quiz,))
            st.caption("선택하면 문제 수와 안내를 확인할 수 있습니다.")


def render_quiz_detail(q_item, season_res, app_settings, player_name, robust_parse_func, get_kst_time):
    parsed, errors = validate_quiz_text(q_item["Content"])
    if st.session_state.quiz_finished:
        render_results()
        return
    st.caption(str(q_item.get("Category") or "미분류"))
    st.subheader(q_item["Title"])
    if errors or not parsed:
        st.error("문제 형식을 확인해야 합니다. 관리자에게 수정을 요청해 주세요.")
        for error in errors:
            st.caption(error)
        st.button("목록으로 돌아가기", on_click=reset_attempt)
        return
    if st.session_state.start_time is None:
        short_count = sum(q["o"] == ["주관식"] for q in parsed)
        st.info(f"총 {len(parsed)}문제 · 객관식 {len(parsed)-short_count} · 주관식 {short_count}")
        st.write("모든 답을 입력한 뒤 제출하면 점수와 해설을 볼 수 있습니다.")
        if short_count:
            st.caption("주관식은 등록된 정답과 비교합니다. 공백·대소문자는 구분하지 않으며, 별도의 AI 채점은 없습니다.")
        if not player_name.strip():
            st.warning("상단에서 학습자 이름을 입력한 뒤 시작해 주세요.")
        def start():
            st.session_state.start_time = time.time()
            st.session_state.attempt_id = uuid.uuid4().hex
            st.session_state.attempt_player = player_name.strip()
            st.session_state.save_steps = {}
        st.button("풀이 시작", type="primary", use_container_width=True, disabled=not player_name.strip(), on_click=start)
        st.button("다른 퀴즈 선택", use_container_width=True, on_click=reset_attempt)
        if st.checkbox("이 퀴즈의 성적 기록 보기"):
            rows = [r for r in get_all_results() if r.get("QuizTitle") == q_item["Title"]]
            if rows:
                import pandas as pd
                st.dataframe(pd.DataFrame(rows)[["User", "Score", "Duration"]].rename(columns={"User":"학습자", "Score":"점수", "Duration":"시간(초)"}), hide_index=True, use_container_width=True)
            else:
                st.caption("아직 기록이 없습니다.")
        return

    st.caption(f"{st.session_state.attempt_player}님 · {len(parsed)}문제 · 답안은 제출할 때 한 번에 전송됩니다.")
    with st.form(f"answers_{st.session_state.attempt_id}"):
        answers = {}
        for index, item in enumerate(parsed):
            st.markdown(f"#### {index+1}. {item['q']}")
            if item.get("p"):
                st.info(item["p"])
            key = f"answer_{st.session_state.attempt_id}_{index}"
            if item["o"] == ["주관식"]:
                answers[index] = st.text_input(f"{index+1}번 답", key=key, placeholder="정답을 입력하세요")
            else:
                answers[index] = st.radio(f"{index+1}번 보기", item["o"], index=None, key=key, label_visibility="collapsed")
            if index < len(parsed)-1:
                st.divider()
        submitted = st.form_submit_button("답안 제출", type="primary", use_container_width=True)
    if submitted:
        missing = [str(i+1) for i, value in answers.items() if value is None or not str(value).strip()]
        if missing:
            st.warning("아직 답하지 않은 문제: " + ", ".join(missing) + "번. 답을 입력한 뒤 다시 제출해 주세요.")
        else:
            score_logic(parsed, q_item, st.session_state.attempt_player, get_kst_time, answers)
    with st.expander("풀이 그만두기"):
        st.caption("목록으로 돌아가면 작성 중인 답안이 사라집니다.")
        st.button("풀이 취소하고 목록으로", on_click=reset_attempt, use_container_width=True)


def score_logic(parsed, q_item, player_name, get_kst_time, answers=None):
    if not parsed or st.session_state.quiz_finished:
        return
    answers = answers or {}
    review, wrong_items = [], []
    for index, item in enumerate(parsed):
        user_answer = answers.get(index, "")
        correct = item["a"] if item["o"] == ["주관식"] else item["o"][item["a"]]
        matched = check_subjective_answer(user_answer, correct) if item["o"] == ["주관식"] else user_answer == correct
        review.append({"idx": index+1, "q": item["q"], "u": user_answer, "c": correct, "e": item["e"], "correct": matched})
        if not matched:
            wrong_items.append(item)
    score = round(100 * (len(parsed) - len(wrong_items)) / len(parsed))
    st.session_state.pending_result = {"title": q_item["Title"], "category": q_item.get("Category", "미분류"),
                                       "player": player_name, "score": score,
                                       "duration": max(0, round(time.time()-st.session_state.start_time)), "wrongs": wrong_items}
    st.session_state.review_data = review
    st.session_state.last_score = score
    st.session_state.quiz_finished = True
    persist_attempt(get_kst_time)
    st.rerun()


def persist_attempt(get_kst_time):
    result = st.session_state.pending_result
    steps = st.session_state.setdefault("save_steps", {})
    try:
        if not steps.get("result"):
            save_result(result["title"], result["player"], result["score"], result["duration"], [], attempt_id=st.session_state.attempt_id)
            steps["result"] = True
        if result["wrongs"] and not steps.get("wrongs"):
            save_wrong_answers(result["title"], result["player"], [q["q"] for q in result["wrongs"]], attempt_id=st.session_state.attempt_id)
            steps["wrongs"] = True
        if result["wrongs"] and not steps.get("details"):
            save_wrong_answers_detailed(result["title"], result["category"], result["player"], result["wrongs"], get_kst_time, attempt_id=st.session_state.attempt_id)
            steps["details"] = True
        st.session_state.results_saved = True
        st.session_state.save_error = ""
    except Exception:
        st.session_state.results_saved = False
        st.session_state.save_error = "기록 저장이 완료되지 않았습니다. 이 화면을 유지하고 연결 상태를 확인한 뒤 다시 시도해 주세요."


def render_results():
    from my_study_app_utils import get_kst_time
    result = st.session_state.pending_result
    st.subheader("풀이를 마쳤어요")
    st.caption(result["title"])
    c1, c2 = st.columns(2)
    c1.metric("나의 점수", f"{result['score']}점")
    c2.metric("정답", f"{len(st.session_state.review_data)-len(result['wrongs'])} / {len(st.session_state.review_data)}")
    if st.session_state.results_saved:
        st.success("성적이 저장되었습니다. 아래에서 답과 해설을 확인해 보세요.")
    else:
        st.warning(st.session_state.get("save_error", "기록 저장이 필요합니다."))
        if st.button("저장 다시 시도", type="primary"):
            persist_attempt(get_kst_time)
            st.rerun()
    for row in st.session_state.review_data:
        with st.expander(f"{row['idx']}번 · {'정답' if row['correct'] else '오답'} · {row['q']}", expanded=not row["correct"]):
            st.write(f"내 답: {row['u']}")
            st.write(f"정답: {row['c']}")
            st.info(row["e"])
    if not st.session_state.results_saved:
        st.caption("목록으로 이동하면 저장되지 않은 기록을 잃을 수 있습니다.")
    st.button("다른 퀴즈 풀기", use_container_width=True, on_click=reset_attempt)
