import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
import time
from database import get_all_quizzes, save_quiz, save_result, save_wrong_answers
from utils import generate_quiz_with_ai, check_subjective_answer, natural_sort_key, robust_parse

def show_quiz_area(quizzes, season_res, app_settings, player_name, robust_parse_func):
    # cats_with_quizzes = set(q.get('Category', '미분류') for q in quizzes)
    # custom_cats = [c.strip() for c in app_settings.get("custom_categories", "").split(",") if c.strip()]
    # all_display_cats = list(dict.fromkeys(["우정퀴즈"] + custom_cats + list(cats_with_quizzes)))

    # 1. 데이터에 존재하는 실제 카테고리들 추출
    cats_in_data = set(q.get('Category', '미분류') for q in quizzes)
    
    # 2. 어드민(Admin) 설정값 가져오기 (가장 앞의 한 개 값만 사용)
    raw_custom = app_settings.get("custom_categories", "").split(",")
    admin_main = raw_custom[0].strip() if raw_custom and raw_custom[0].strip() else None
    
    # 3. 우선순위 리스트(탭 순서) 조립
    priority_list = []
    
    if admin_main:
        # [A순위] 어드민 설정값이 있으면 무조건 1번
        priority_list.append(admin_main)
    
    if "우정퀴즈" not in priority_list:
        # [B순위] 우정퀴즈가 어드민 설정이 아니라면 그 다음에 배치
        priority_list.append("우정퀴즈")
        
    # 4. [C순위] 나머지 카테고리들 가나다순 정렬
    remaining_cats = sorted([c for c in cats_in_data if c not in priority_list])
    
    # 5. 최종 탭 리스트 결합
    all_display_cats = priority_list + remaining_cats

    # 탭 생성
    tabs = st.tabs(all_display_cats)


    tabs = st.tabs(all_display_cats)
    for i, cat in enumerate(all_display_cats):
        with tabs[i]:
            if cat == "우정퀴즈":
                render_ai_generation_ui()
            
            cat_qs = [q for q in quizzes if q.get('Category') == cat]
            cat_qs = sorted(cat_qs, key=lambda x: natural_sort_key(x['Title'])) 
            if not cat_qs:
                st.caption("등록된 퀴즈가 없습니다.")
            else:
                cols = st.columns(2)
                for j, q in enumerate(cat_qs):
                    if cols[j%2].button(q['Title'], use_container_width=True, key=f"q_{cat}_{j}"):
                        st.session_state.selected_quiz = q['Title']
                        st.session_state.quiz_finished = False
                        st.session_state.user_answers = {}
                        st.session_state.answered_list = []
                        st.session_state.start_time = None
                        st.session_state.quiz_jump = True 
                        st.rerun()

            if st.session_state.selected_quiz:
                selected_q_item = next((q for q in quizzes if q['Title'] == st.session_state.selected_quiz), None)
                if selected_q_item and selected_q_item.get('Category') == cat:
                    render_quiz_detail(selected_q_item, season_res, app_settings, player_name, robust_parse_func)

def render_ai_generation_ui():
    with st.expander("나만의 우정 파괴 퀴즈 만들기"):
        q_title = st.text_input("퀴즈 제목", key="ai_title")
        q_topic = st.text_input("퀴즈 주제", key="ai_topic")
        if st.button("AI 출제 시작"):
            api_key = st.secrets.get("GEMINI_API_KEY")
            if api_key and q_title and q_topic:
                with st.spinner("생성 중..."):
                    text = generate_quiz_with_ai(api_key, q_topic)
                    save_quiz(q_title, "우정퀴즈", text)
                    get_all_quizzes.clear()
                    st.rerun()

def render_quiz_detail(q_item, season_res, app_settings, player_name, robust_parse_func):
    st.markdown("<div id='quiz_start_anchor'></div>", unsafe_allow_html=True)
    if st.session_state.get('quiz_jump'):
        components.html("<script>window.parent.document.getElementById('quiz_start_anchor').scrollIntoView({behavior: 'smooth'});</script>", height=0)
        st.session_state.quiz_jump = False

    with st.container(border=True):
        st.markdown(f"### {q_item['Title']}")
        
        # [복구] 상세 페이지 내 지배자들 랭킹 표시
        q_res = [r for r in season_res if r.get('QuizTitle') == q_item['Title']]
        with st.expander(" 이 구역의 지배자들", expanded=True):
            if q_res:
                s_df = pd.DataFrame(q_res).sort_values(by=['Score', 'Duration'], ascending=[False, True]).reset_index(drop=True)
                s_df.index = range(1, len(s_df) + 1)
                st.table(s_df[['User', 'Score', 'Duration']].rename(columns={'User':'수험번호', 'Score':'점수', 'Duration':'시간'}))
            else: 
                st.info(" ")

        if st.session_state.start_time is None and not st.session_state.quiz_finished:
            if st.button("시험 시작하기", use_container_width=True, type="primary"):
                st.session_state.start_time = time.time()
                st.rerun()
        
        elif not st.session_state.quiz_finished:
            parsed = robust_parse_func(q_item['Content'])
            for idx, it in enumerate(parsed):
                st.divider()
                
                # [복구] 지문이 있으면 지문 박스 표시
                if it.get('p'):
                    with st.container(border=True):
                        st.markdown(f"📄 **[지문]**\n\n{it['p']}")
                
                st.markdown(f"**Q{idx+1}.** {it['q']}")
                
                if it['o'] == ["주관식"]:
                    st.session_state.user_answers[f"ans_{idx}"] = st.text_input("정답 입력", key=f"in_{idx}")
                else:
                    st.session_state.user_answers[f"ans_{idx}"] = st.radio("보기", it['o'], index=None, key=f"in_{idx}", label_visibility="collapsed")

            if st.button("최종 제출", use_container_width=True):
                score_logic(parsed, q_item, player_name)

    if st.session_state.quiz_finished:
        render_results()

def score_logic(parsed, q_item, player_name):
    review_list, wrongs_results, wrongs_conquest = [], [], []
    for k, it in enumerate(parsed):
        u = st.session_state.user_answers.get(f"ans_{k}", "")
        c = str(it['a']) if it['o'] == ["주관식"] else it['o'][it['a']]
        
        is_c = check_subjective_answer(u, it['a']) if it['o'] == ["주관식"] else (str(u) == str(c))
        
        if not is_c:
            wrongs_results.append(it['k'])
            wrongs_conquest.append(it['q'])
            review_list.append({'idx': k+1, 'q': it['q'], 'u': u if u else "미입력", 'c': c, 'e': it['e']})
    
    score = ((len(parsed)-len(review_list))/len(parsed))*100
    save_result(q_item['Title'], player_name, score, time.time()-st.session_state.start_time, wrongs_results)
    if wrongs_conquest: save_wrong_answers(q_item['Title'], player_name, wrongs_conquest)
    st.session_state.quiz_finished, st.session_state.last_score, st.session_state.review_data = True, score, review_list
    st.rerun()

def render_results():
    st.success(f"최종 점수: {int(st.session_state.last_score)}점")
    for rev in st.session_state.review_data:
        with st.expander(f"Q{rev['idx']}. 오답 확인", expanded=True):
            st.markdown(f"**문제:** {rev['q']}\n\n**제출:** {rev['u']}\n\n**정답:** {rev['c']}\n\n💡 {rev['e']}")
    if st.button("목록으로 돌아가기", use_container_width=True):
        st.session_state.selected_quiz = ""
        st.rerun()