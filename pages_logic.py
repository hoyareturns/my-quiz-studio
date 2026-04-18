import streamlit as st
import pandas as pd
import time
from database import (get_chats, save_chat, save_setting, get_all_quizzes, save_result, save_quiz,
                      get_wrong_answers_by_user, update_wrong_answer_status, get_all_users_with_wrongs)
from utils import generate_quiz_with_ai, robust_parse

def show_season_leaderboard(season_res, season_start):
    """구역별 최강자 리뉴얼: 퀴즈별 1, 2, 3위만 이모지 없이 표시"""
    st.subheader("구역별 최강자")
    st.caption(f"이번 시즌 시작일: {season_start[:10]}")
    
    if not season_res:
        st.info("이번 시즌 기록이 없습니다.")
        return

    df = pd.DataFrame(season_res)
    # 기록이 존재하는 모든 퀴즈 목록 (중복 제거)
    quiz_titles = df['QuizTitle'].unique()

    for title in quiz_titles:
        st.markdown(f"### {title}")
        
        # 해당 퀴즈의 기록만 필터링 후 점수(내림차순), 시간(오름차순)으로 정렬
        quiz_df = df[df['QuizTitle'] == title].sort_values(
            by=['Score', 'Duration'], ascending=[False, True]
        ).reset_index(drop=True)

        # 상위 3위까지 텍스트로만 표시
        for i in range(min(3, len(quiz_df))):
            row = quiz_df.iloc[i]
            st.write(f"{i+1}위: {row['User']} ({int(row['Score'])}점 / {row['Duration']}초)")
        
        st.write("") # 퀴즈별 간격

def show_chat_room(player_name):
    st.markdown("<div id='chat_top_anchor'></div>", unsafe_allow_html=True)
    c1, c2 = st.columns([3, 1])
    c1.subheader("우정파괴채팅")
    if c2.button("새로고침", key="chat_refresh"): 
        get_chats.clear()
        st.rerun()
    
    chat_box = st.container(height=400)
    for c in get_chats():
        t_str = str(c.get('Time', ''))[:16]
        cls = "chat-sys" if c["User"] == "시스템" else "chat-user"
        chat_box.markdown(f'<div class="chat-msg"><span class="{cls}">{c["User"]}:</span>{c["Message"]}<span class="chat-time">{t_str}</span></div>', unsafe_allow_html=True)
    
    with st.form("chat_input", clear_on_submit=True):
        m = st.text_input("메시지 입력", label_visibility="collapsed")
        if st.form_submit_button("전송", use_container_width=True) and m:
            save_chat(player_name, m)
            st.rerun()

def show_quiz_area(quizzes, season_res, app_settings, player_name, robust_parse):
    cats_with_quizzes = set(q.get('Category', '미분류') for q in quizzes)
    custom_cats = [c.strip() for c in app_settings.get("custom_categories", "").split(",") if c.strip()]
    candidates = list(dict.fromkeys(custom_cats + list(cats_with_quizzes) + ["우정퀴즈"]))
    
    all_display_cats = []
    for cat in candidates:
        if cat == "우정퀴즈" or cat in cats_with_quizzes:
            all_display_cats.append(cat)
    
    default_cat_name = app_settings.get("default_category", "우정퀴즈")
    if default_cat_name in all_display_cats:
        all_display_cats.remove(default_cat_name)
        all_display_cats.insert(0, default_cat_name)

    if not all_display_cats:
        st.info("표시할 카테고리가 없습니다.")
        return

    tabs = st.tabs(all_display_cats)
    for i, cat in enumerate(all_display_cats):
        with tabs[i]:
            st.write("") 
            if cat == "우정퀴즈":
                with st.expander("나만의 우정 파괴 퀴즈 만들기", expanded=False):
                    q_title = st.text_input("퀴즈 제목", placeholder="제목 입력", key="new_q_title")
                    q_topic = st.text_input("퀴즈 주제", placeholder="주제 입력", key="new_q_topic")
                    if st.button("AI 출제 시작", use_container_width=True):
                        api_key = st.secrets.get("GEMINI_API_KEY")
                        if api_key and q_title and q_topic:
                            with st.spinner("생성 중..."):
                                try:
                                    text = generate_quiz_with_ai(api_key, q_topic)
                                    save_quiz(q_title, "우정퀴즈", text)
                                    st.success("배포 완료")
                                    time.sleep(1)
                                    get_all_quizzes.clear()
                                    st.rerun()
                                except Exception as e:
                                    st.error(f"오류: {e}")
                st.divider()

            cat_qs = [q for q in quizzes if q.get('Category') == cat]
            if cat == "우정퀴즈":
                pop_counts = pd.DataFrame(season_res)['QuizTitle'].value_counts().to_dict() if season_res else {}
                cat_qs = sorted(cat_qs, key=lambda x: pop_counts.get(x['Title'], 0), reverse=True)
            else:
                cat_qs = sorted(cat_qs, key=lambda x: x['Title'])
            
            if not cat_qs: 
                st.caption("등록된 퀴즈가 없습니다")
            else:
                cols = st.columns(2)
                for j, q in enumerate(cat_qs):
                    if cols[j%2].button(q['Title'], use_container_width=True, key=f"q_{i}_{j}"):
                        st.session_state.selected_quiz = q['Title']
                        st.session_state.quiz_finished = False
                        st.session_state.user_answers = {}
                        st.session_state.answered_list = []
                        st.session_state.start_time = None
                        st.rerun()

            if st.session_state.selected_quiz:
                selected_q_item = next((q for q in quizzes if q['Title'] == st.session_state.selected_quiz), None)
                if selected_q_item and selected_q_item.get('Category') == cat:
                    render_quiz_detail(selected_q_item, season_res, app_settings, player_name, robust_parse)

def render_quiz_detail(q_item, season_res, app_settings, player_name, robust_parse):
    with st.container(border=True):
        st.markdown(f"**{q_item['Title']}**")
        q_res = [r for r in season_res if r.get('QuizTitle') == q_item['Title']]
        
        with st.expander("이 구역의 지배자들", expanded=True):
            if q_res:
                s_df = pd.DataFrame(q_res).sort_values(by=['Score', 'Duration'], ascending=[False, True]).reset_index(drop=True)
                s_df.index = range(1, len(s_df) + 1)
                st.table(s_df[['User', 'Score', 'Duration']].rename(columns={'User':'수험번호', 'Score':'점수', 'Duration':'시간'}))
            else: 
                st.info("첫 지배자가 되어보세요")

        if st.session_state.start_time is None and not st.session_state.quiz_finished:
            if st.button("시험 시작하기", use_container_width=True, type="primary"): 
                st.session_state.start_time = time.time()
                st.rerun()
        
        elif not st.session_state.quiz_finished:
            parsed = robust_parse(q_item['Content'])
            if not parsed:
                st.error("데이터 오류: 문제를 불러올 수 없습니다.")
            
            is_realtime = "실시간 팩폭" in app_settings.get('feedback_mode', '')
            
            for idx, it in enumerate(parsed):
                st.divider()
                if it.get('p'):
                    # 수식 지원을 위해 테두리 박스 + 마크다운 사용
                    with st.container(border=True):
                        st.markdown(f"**[지문]**\n\n{it['p']}")
                
                # 수식 충돌 방지를 위해 번호만 볼드 처리
                st.markdown(f"**Q{idx+1}.** {it['q']}")
                
                is_short = it['o'] == ["주관식"]
                is_answered = idx in st.session_state.answered_list
                
                if is_short: 
                    ans = st.text_input(f"답_{idx}", key=f"in_{idx}", disabled=is_answered)
                else: 
                    ans = st.radio(f"보기_{idx}", it['o'], index=None, key=f"in_{idx}", label_visibility="collapsed", disabled=is_answered)
                
                if ans and is_realtime:
                    if not is_answered:
                        st.session_state.user_answers[f"ans_{idx}"] = ans
                        st.session_state.answered_list.append(idx)
                        st.rerun()
                    
                    correct_ans = str(it['a']) if is_short else it['o'][it['a']]
                    user_ans_str = str(ans)
                    is_correct = (user_ans_str.replace(" ","").lower() == correct_ans.replace(" ","").lower()) if is_short else (user_ans_str == correct_ans)
                    
                    if is_correct: st.success("정답입니다!")
                    else: st.error(f"오답입니다! (정답: {correct_ans})")
                    st.markdown(f"**[해설]** {it['e']}")

            st.write("")
            if parsed and st.button("최종 제출", use_container_width=True):
                wrongs_for_results = [] # 기존 Results 기록용
                wrongs_for_conquest = [] # 오답 정복 기록용 (문제 원문)
                review_list = []
                
                for k, it in enumerate(parsed):
                    u = st.session_state.user_answers.get(f"ans_{k}")
                    if u is None or u == "":
                        u = st.session_state.get(f"in_{k}", "")
                        
                    c = str(it['a']) if it['o'] == ["주관식"] else it['o'][it['a']]
                    is_c = (str(u).replace(" ","").lower() == str(c).replace(" ","").lower()) if it['o'] == ["주관식"] else (str(u) == str(c))
                    
                    if not is_c: 
                        wrongs_for_results.append(it['k']) # 키워드
                        wrongs_for_conquest.append(it['q']) # 문제 원문
                        review_list.append({
                            'idx': k + 1, 'q': it['q'], 'u': u if u else "미입력", 'c': c, 'e': it['e']
                        })
                
                score = ((len(parsed)-len(review_list))/len(parsed))*100
                save_result(q_item['Title'], player_name, score, time.time()-st.session_state.start_time, wrongs_for_results)
                
                # 오답 정복 기록 저장
                if wrongs_for_conquest:
                    from database import save_wrong_answers
                    save_wrong_answers(q_item['Title'], player_name, wrongs_for_conquest)
                
                st.session_state.quiz_finished = True
                st.session_state.last_score = score
                st.session_state.review_data = review_list
                st.rerun()

    if st.session_state.quiz_finished:
        st.success(f"최종 점수: {int(st.session_state.last_score)}점")
        review_data = st.session_state.get('review_data', [])
        if review_data:
            st.error("오답 노트 (틀린 문제 해설)")
            for rev in review_data:
                with st.expander(f"Q{rev['idx']}. 오답 확인", expanded=True):
                    st.markdown(f"**문제:** {rev['q']}")
                    st.markdown(f"**[내 제출]** {rev['u']}")
                    st.markdown(f"**[정답]** {rev['c']}")
                    st.markdown(f"**[해설]** {rev['e']}")
        elif int(st.session_state.last_score) == 100:
            st.info("완벽합니다! 모두 맞혔습니다.")

        if st.button("목록으로 돌아가기", use_container_width=True): 
            st.session_state.selected_quiz = ""
            st.session_state.review_data = []
            st.rerun()

def show_wrong_answer_review(current_player, all_quizzes):
    """오답 정복 화면: 오답이 있는 유저만 드롭박스로 선택 가능"""
    st.subheader("오답 정복")
    st.caption("틀린 문제만 다시 풀어보세요. 맞히면 목록에서 사라집니다.")
    
    # 오답 기록이 남아있는 아이디만 가져오기
    all_users = get_all_users_with_wrongs()
    if not all_users:
        st.info("현재 정복할 오답이 없습니다. 열공 중이시군요!")
        return
        
    target_user = st.selectbox("리뷰할 아이디 선택", all_users, 
                               index=all_users.index(current_player) if current_player in all_users else 0)
    
    wrong_records = get_wrong_answers_by_user(target_user)
    
    if not wrong_records:
        st.success(f"🎉 {target_user}님은 모든 오답을 정복했습니다!")
        return

    st.write(f"현재 **{len(wrong_records)}개**의 오답이 남아있습니다.")
    
    with st.form("wrong_review_form"):
        user_inputs = {}
        for idx, wr in enumerate(wrong_records):
            q_title = wr.get('QuizTitle')
            q_text = wr.get('QuestionText')
            
            parent_quiz = next((q for q in all_quizzes if q['Title'] == q_title), None)
            if not parent_quiz: continue
            
            parsed = robust_parse(parent_quiz['Content'])
            q_data = next((p for p in parsed if p['q'] == q_text), None)
            if not q_data: continue

            st.divider()
            st.caption(f"출처: {q_title}")
            if q_data.get('p'):
                with st.container(border=True):
                    st.markdown(f"**[지문]**\n\n{q_data['p']}")
            
            st.markdown(f"**Q.** {q_data['q']}")
            
            is_short = q_data['o'] == ["주관식"]
            if is_short:
                user_inputs[idx] = st.text_input("답 입력", key=f"wr_in_{idx}")
            else:
                user_inputs[idx] = st.radio("보기", q_data['o'], index=None, key=f"wr_in_{idx}", label_visibility="collapsed")
        
        if st.form_submit_button("오답 정복 시도", use_container_width=True):
            for idx, wr in enumerate(wrong_records):
                u_ans = user_inputs.get(idx)
                if not u_ans: continue
                
                q_title = wr.get('QuizTitle')
                q_text = wr.get('QuestionText')
                parent_quiz = next((q for q in all_quizzes if q['Title'] == q_title), None)
                q_data = next((p for p in robust_parse(parent_quiz['Content']) if p['q'] == q_text), None)
                
                correct = str(q_data['a']) if q_data['o'] == ["주관식"] else q_data['o'][q_data['a']]
                is_ok = (str(u_ans).replace(" ","").lower() == str(correct).replace(" ","").lower()) if q_data['o'] == ["주관식"] else (str(u_ans) == str(correct))
                
                # 맞히면 '정복' 상태로 업데이트
                if is_ok:
                    update_wrong_answer_status(target_user, q_title, q_text, "정복")
            
            st.success("채점이 완료되었습니다!")
            time.sleep(1)
            st.rerun()
