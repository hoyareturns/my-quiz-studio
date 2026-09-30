import hashlib
import streamlit as st
from database import get_all_quizzes, save_quiz
from prompts import EXTERNAL_PROMPT_TEMPLATE
from utils import validate_quiz_text, natural_sort_key


def remember_draft():
    st.session_state.author_draft = {key: st.session_state.get(key, "") for key in ("draft_title", "draft_category", "draft_content")}


def show_question_preview(questions):
    index = st.selectbox("미리 볼 문제", range(len(questions)), format_func=lambda i: f"{i+1}번 · {questions[i]['q'][:40]}", key="preview_question")
    question = questions[index]
    with st.container(border=True):
        st.markdown(f"**{index+1}. {question['q']}**")
        if question["p"]:
            st.info(question["p"])
        if question["o"] != ["주관식"]:
            for i, option in enumerate(question["o"]):
                st.write(f"{'①②③④⑤'[i]} {option}")
            answer = question["o"][question["a"]]
        else:
            st.caption("주관식")
            answer = question["a"]
        st.success(f"정답: {answer}")
        st.caption(question["e"])


def show_author_page(app_settings):
    from admin import show_admin_login
    st.subheader("문제를 준비하는 가장 쉬운 순서")
    st.caption("요청문 복사 → GPT에서 생성 → 붙여넣고 확인 → 등록")
    with st.expander("1. GPT에 보낼 요청문 만들기", expanded=False):
        st.markdown("주제와 문제 수를 정한 뒤, 아래 요청문 오른쪽 위 **복사 버튼**을 눌러 주세요.")
        with st.form("prompt_builder"):
            topic = st.text_input("출제 주제", placeholder="예: 엑셀 기본 함수, 산업안전 기초", key="prompt_topic")
            left, right = st.columns(2)
            count = left.number_input("문제 수", min_value=1, max_value=50, value=10)
            level = right.selectbox("난이도", ["기초", "보통", "심화"])
            kind = st.selectbox("문제 유형", ["객관식", "주관식", "객관식과 주관식 혼합"])
            material = st.text_area("참고 내용 (선택)", placeholder="교재 요약이나 출제 범위를 붙여넣으세요", height=120)
            make = st.form_submit_button("요청문 만들기", use_container_width=True)
        if make:
            base = EXTERNAL_PROMPT_TEMPLATE.replace("10문제", f"{int(count)}문제", 1)
            st.session_state.generated_prompt = f"주제: {topic.strip() or '아래 참고 내용'}\n난이도: {level}\n문제 유형: {kind}\n\n{base}" + (f"\n\n참고 내용:\n{material}" if material.strip() else "")
        prompt = st.session_state.get("generated_prompt", EXTERNAL_PROMPT_TEMPLATE)
        st.code(prompt, language=None)
        st.link_button("ChatGPT 열기 ↗", "https://chatgpt.com/", use_container_width=True)
        st.caption("직접 복사해서 사용하는 방식입니다. 앱은 AI API를 호출하지 않으며, 외부 서비스의 요금은 이용 중인 계정에 따릅니다.")

    st.markdown("### 2. 답변을 붙여넣고 확인")
    st.caption("GPT 답변을 통째로 붙여넣으세요. 여러 문제를 한 번에 등록할 수 있습니다.")
    if st.session_state.get("registration_success"):
        st.success(st.session_state.pop("registration_success"))
    saved = st.session_state.get("author_draft", {})
    for key, default in (("draft_title", ""), ("draft_category", app_settings.get("default_category") or "공통 역량"), ("draft_content", "")):
        if key not in st.session_state:
            st.session_state[key] = saved.get(key, default)
    st.text_input("퀴즈 제목", key="draft_title", placeholder="예: 엑셀 함수 기초 01", on_change=remember_draft)
    st.text_input("분류", key="draft_category", placeholder="예: 공통 역량", on_change=remember_draft)
    st.text_area("문제 붙여넣기", key="draft_content", height=280, placeholder="[Q1] 질문\n[O] ① 보기1 ② 보기2\n[A] ②\n[E] 해설", on_change=remember_draft)
    title = st.session_state.draft_title.strip()
    category = st.session_state.draft_category.strip()
    content = st.session_state.draft_content
    signature = hashlib.sha256((title + "\0" + category + "\0" + content).encode()).hexdigest()
    if st.button("문제 미리보기", type="primary", use_container_width=True):
        remember_draft()
        questions, errors = validate_quiz_text(content)
        if not title or not category:
            errors.append("퀴즈 제목과 분류를 입력해 주세요.")
        st.session_state.import_preview = (signature, questions, errors)
        st.session_state.pop("preview_question", None)
    preview = st.session_state.get("import_preview")
    ready = bool(preview and preview[0] == signature and preview[1] and not preview[2])
    if preview and preview[0] == signature:
        for error in preview[2]:
            st.error(error)
        if ready:
            st.success(f"총 {len(preview[1])}문제의 형식을 확인했습니다. 정답과 해설도 검토해 주세요.")
            show_question_preview(preview[1])
    elif preview:
        st.info("내용이 바뀌었습니다. 등록 전에 미리보기를 다시 확인해 주세요.")
    st.caption("주관식 허용 답안은 |로 나눕니다. 예: 서울 | Seoul. 분수와 수식은 그대로 입력하세요.")
    st.markdown("### 3. 퀴즈 등록")
    if not st.session_state.get("is_admin"):
        st.caption("요청문 작성과 미리보기는 누구나 가능합니다. 등록하려면 관리자 인증이 필요합니다.")
        show_admin_login("author")
    if st.button("퀴즈 등록", type="primary", use_container_width=True, disabled=not (ready and st.session_state.get("is_admin"))):
        try:
            save_quiz(title, category, content)
        except ValueError as exc:
            st.error(str(exc))
        except Exception:
            st.error("등록하지 못했습니다. 입력한 내용은 유지됩니다. 연결 상태를 확인한 뒤 다시 시도해 주세요.")
        else:
            st.session_state.registration_success = f"‘{title}’ 퀴즈를 등록했습니다. 역량 점검 메뉴에서 바로 풀 수 있습니다."
            st.session_state.author_draft = {}
            for key in ("draft_title", "draft_category", "draft_content", "import_preview"):
                st.session_state.pop(key, None)
            st.rerun()
