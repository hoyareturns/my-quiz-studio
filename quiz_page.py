import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
import time
from database import get_all_quizzes, save_quiz, save_result, save_wrong_answers, save_wrong_answers_detailed
from utils import generate_quiz_with_ai, check_subjective_answer, natural_sort_key, robust_parse

def show_quiz_area(quizzes, season_res, app_settings, player_name, robust_parse_func, get_kst_time):

    if "results_saved" not in st.session_state:
            st.session_state.results_saved = False

    # 1. 실제 데이터에 존재하는 모든 카테고리 추출
    cats_in_data = set(q.get('Category', '미분류') for q in quizzes)
    
    # 2. 어드민 설정값 가져오기
    default_cat = app_settings.get("default_category") # '처음 열릴 카테고리'
    custom_cats = [c.strip() for c in app_settings.get("custom_categories", "").split(",") if c.strip()]
    
    # 3. [핵심 수정] 탭 목록 재구성: 데이터가 있는 경우만 포함 (우정퀴즈는 항상 포함)
    all_display_cats = []
    
    # [1순위] 어드민이 지정한 '처음 열릴 카테고리'
    # 우정퀴즈이거나 실제 퀴즈 데이터가 있는 경우에만 추가합니다.
    if default_cat:
        if default_cat == "우정퀴즈" or default_cat in cats_in_data:
            all_display_cats.append(default_cat)
        
    # [2순위] 우정퀴즈 (데이터 유무와 상관없이 항상 노출)
    if "우정퀴즈" not in all_display_cats:
        all_display_cats.append("우정퀴즈")
        
    # [3순위] 어드민 '카테고리 목록'에 적힌 항목들 중 퀴즈가 있는 것만 추가
    for c in custom_cats:
        if c not in all_display_cats and c in cats_in_data:
            all_display_cats.append(c)
            
    # [4순위] 그 외 데이터에만 있는 카테고리들 가나다순 정렬
    remaining_cats = sorted([c for c in cats_in_data if c not in all_display_cats])
    all_display_cats += remaining_cats

    # 탭 생성 (필터링된 목록 사용)
    if not all_display_cats:
        st.info("표시할 퀴즈 카테고리가 없습니다.")
        return

    tabs = st.tabs(all_display_cats)
    
    for i, cat in enumerate(all_display_cats):
        with tabs[i]:
            if cat == "우정퀴즈":
                render_ai_generation_ui()
            
            # 4. [핵심] 퀴즈 버튼 정렬: 1번부터 오름차순 정렬
            cat_qs = [q for q in quizzes if q.get('Category') == cat]
            cat_qs = sorted(cat_qs, key=lambda x: natural_sort_key(x['Title']))
            
            if not cat_qs:
                if cat != "우정퀴즈":
                    st.caption(f"'{cat}' 그룹에 등록된 퀴즈가 없습니다.")
            else:
                # [수정 포인트] 가로 줄(Row) 단위로 2개씩 묶어서 버튼 배치
                # 리스트를 2개씩 건너뛰며 반복문을 실행합니다.
                for j in range(0, len(cat_qs), 2):
                    cols = st.columns(2) # 매 줄마다 새로운 2개 컬럼 생성
                    
                    # 현재 줄의 첫 번째 칸 (홀수 번째 퀴즈)
                    with cols[0]:
                        q = cat_qs[j]
                        if st.button(q['Title'], use_container_width=True, key=f"btn_{cat}_{j}"):
                            st.session_state.selected_quiz = q['Title']
                            st.session_state.results_saved = False
                            st.session_state.quiz_finished = False
                            st.session_state.user_answers = {}
                            st.session_state.start_time = None
                            st.session_state.quiz_jump = True 
                            st.rerun()
                    
                    # 현재 줄의 두 번째 칸 (짝수 번째 퀴즈 - 존재할 경우에만 생성)
                    if j + 1 < len(cat_qs):
                        with cols[1]:
                            q = cat_qs[j+1]
                            if st.button(q['Title'], use_container_width=True, key=f"btn_{cat}_{j+1}"):
                                st.session_state.selected_quiz = q['Title']
                                st.session_state.results_saved = False
                                st.session_state.quiz_finished = False
                                st.session_state.user_answers = {}
                                st.session_state.start_time = None
                                st.session_state.quiz_jump = True 
                                st.rerun()

            if st.session_state.selected_quiz:
                selected_q_item = next((q for q in quizzes if q['Title'] == st.session_state.selected_quiz), None)
                if selected_q_item and selected_q_item.get('Category') == cat:
                    render_quiz_detail(selected_q_item, season_res, app_settings, player_name, robust_parse_func, get_kst_time)

def render_ai_generation_ui():
    with st.expander("나만의 우정 파괴 퀴즈 만들기"):
        q_title = st.text_input("퀴즈 제목", placeholder="예: 길동이의 우정 테스트" , key="ai_title")
        q_topic = st.text_input("퀴즈 주제", placeholder="예: 설명하는 동물의 이름",  key="ai_topic")
        
        if st.button("AI 출제 시작"):            
            # [수정] api_key 체크를 제거하고 제목과 주제 입력 여부만 확인합니다.
            if q_title and q_topic:
                with st.spinner("생성 중..."):
                    # 실제 API 키 처리는 generate_quiz_with_ai 함수 내부에서 수행됩니다.
                    text = generate_quiz_with_ai(q_topic)
                    save_quiz(q_title, "우정퀴즈", text)
                    get_all_quizzes.clear()
                    st.rerun()
            else:
                st.warning("퀴즈 제목과 주제를 모두 입력해주세요.")

def render_quiz_detail(q_item, season_res, app_settings, player_name, robust_parse_func, get_kst_time):
    st.markdown("<div id='quiz_start_anchor'></div>", unsafe_allow_html=True)
    if st.session_state.get('quiz_jump'):
        components.html("<script>window.parent.document.getElementById('quiz_start_anchor').scrollIntoView({behavior: 'smooth'});</script>", height=0)
        st.session_state.quiz_jump = False

    with st.container(border=True):
        st.markdown(f"### {q_item['Title']}")
        
        # [복구] 상세 페이지 내 지배자들 랭킹 표시
        q_res = [r for r in season_res if r.get('QuizTitle') == q_item['Title']]
        with st.expander(" 성적 기록", expanded=True):
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
                score_logic(parsed, q_item, player_name, get_kst_time)

    if st.session_state.quiz_finished:
        render_results()


def score_logic(parsed, q_item, player_name, get_kst_time): # get_kst_time 인자 추가
    review_list, wrongs_results, wrongs_conquest = [], [], []
    wrongs_full_data = [] # 신규 시트용 데이터 보관함
    
    for k, it in enumerate(parsed):
        u = st.session_state.user_answers.get(f"ans_{k}", "")
        c = str(it['a']) if it['o'] == ["주관식"] else it['o'][it['a']]
        is_c = check_subjective_answer(u, it['a']) if it['o'] == ["주관식"] else (str(u) == str(c))
        
        if not is_c:
            wrongs_results.append(it['k']) # 기존 기능용 (ID)
            wrongs_conquest.append(it['q']) # 기존 기능용 (질문 텍스트)
            wrongs_full_data.append(it)    # 신규 시트용 (전체 객체)
            review_list.append({'idx': k+1, 'q': it['q'], 'u': u if u else "미입력", 'c': c, 'e': it['e']})
    
    score = round(((len(parsed)-len(review_list))/len(parsed))*100)

    # [수정] 중복 저장 방지 로직 (if문으로 감싸기)
    if not st.session_state.get('results_saved', False):
        with st.spinner("성적을 안전하게 저장 중입니다..."):
            # 1. 결과 저장
            save_result(
                q_item['Title'], 
                player_name, 
                score, 
                round(time.time() - st.session_state.start_time), 
                wrongs_results
            )
            
            # 2. 오답 정복 기능용 저장
            if wrongs_conquest: 
                save_wrong_answers(q_item['Title'], player_name, wrongs_conquest)
                
            # 3. 상세 로그 저장
            if wrongs_full_data:
                save_wrong_answers_detailed(
                    q_item['Title'], 
                    q_item.get('Category', '미분류'), 
                    player_name, 
                    wrongs_full_data, 
                    get_kst_time
                )
            
            # [핵심] 저장이 완료되었음을 세션에 기록 (도장 찍기)
            st.session_state.results_saved = True
            st.success(" 성적이 기록되었습니다.")
                
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