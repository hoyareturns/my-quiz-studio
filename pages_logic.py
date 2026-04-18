import streamlit as st
import pandas as pd
import time
from database import get_chats, save_chat, save_setting, get_all_quizzes, save_result, save_quiz
from utils import generate_quiz_with_ai, robust_parse

def show_season_leaderboard(season_res, season_start):
    st.subheader("구역별 최강자")
    st.caption(f"이번 시즌 시작일: {season_start[:10]}")
    if not season_res:
        st.info("이번 시즌 기록이 없습니다.")
    else:
        df = pd.DataFrame(season_res)
        st.markdown("### 우정 브레이커")
        first_places = df.sort_values(by=['Score', 'Duration'], ascending=[False, True]).groupby('QuizTitle').first()
        breaker_counts = first_places['User'].value_counts()
        if not breaker_counts.empty:
            for idx, (u, c) in enumerate(breaker_counts.items()):
                st.write(f"{idx+1}위: {u} ({c}회 1등)")
        
        st.divider()
        user_stats = df.groupby('User').agg(AvgScore=('Score', 'mean'), Attempts=('Score', 'count'))
        valid_u = user_stats[user_stats['Attempts'] >= 2]
        
        c1, c2 = st.columns(2)
        with c1:
            st.markdown("### 고인물")
            if not valid_u.empty:
                for u, r in valid_u.sort_values('AvgScore', ascending=False).head(3).iterrows():
                    st.write(f"{u} ({r['AvgScore']:.1f}점)")
        with c2:
            st.markdown("### 동네북")
            if not valid_u.empty:
                for u, r in valid_u.sort_values('AvgScore', ascending=True).head(3).iterrows():
                    st.write(f"{u} ({r['AvgScore']:.1f}점)")

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
            get_chats.clear()
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
                                    if not text or text.startswith("오류 발생") or text.startswith("AI API 호출 실패"):
                                        st.error(f"생성 실패: {text}")
                                    else:
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
                    st.markdown(f"""
                        <div style="background-color: #f0f2f6; padding: 15px; border-radius: 10px; margin-bottom: 10px; border-left: 5px solid #ccc;">
                            <p style="color: #333; line-height: 1.6; margin: 0;">{it['p']}</p>
                        </div>
                    """, unsafe_allow_html=True)
                
                st.markdown(f"**Q{idx+1}. {it['q']}**")
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
                    st.info(f"해설: {it['e']}")

            st.write("")
            if parsed and st.button("최종 제출", use_container_width=True):
                wrongs = []
                review_list = [] # 오답 노트용 데이터 리스트
                
                for k, it in enumerate(parsed):
                    u = st.session_state.user_answers.get(f"ans_{k}")
                    if u is None or u == "":
                        u = st.session_state.get(f"in_{k}", "")
                        
                    c = str(it['a']) if it['o'] == ["주관식"] else it['o'][it['a']]
                    is_c = (str(u).replace(" ","").lower() == str(c).replace(" ","").lower()) if it['o'] == ["주관식"] else (str(u) == str(c))
                    
                    if not is_c: 
                        wrongs.append(it['k'])
                        # 틀린 문제의 상세 정보 저장
                        review_list.append({
                            'idx': k + 1,
                            'q': it['q'],
                            'u': u if u else "미입력",
                            'c': c,
                            'e': it['e']
                        })
                
                score = ((len(parsed)-len(wrongs))/len(parsed))*100
                save_result(q_item['Title'], player_name, score, time.time()-st.session_state.start_time, wrongs)
                st.session_state.quiz_finished = True
                st.session_state.last_score = score
                st.session_state.review_data = review_list # 세션에 오답 기록 저장
                st.rerun()

    # 시험 종료 후 결과 출력 화면
    if st.session_state.quiz_finished:
        st.success(f"최종 점수: {int(st.session_state.last_score)}점")
        
        # 오답 노트 출력 로직 추가
        review_data = st.session_state.get('review_data', [])
        if review_data:
            st.error("오답 노트 (틀린 문제 해설)")
            for rev in review_data:
                with st.expander(f"Q{rev['idx']}. {rev['q']}", expanded=True):
                    st.markdown(f"**[내 제출]** {rev['u']}")
                    st.markdown(f"**[정답]** {rev['c']}")
                    st.info(f"**[해설]** {rev['e']}")
        elif int(st.session_state.last_score) == 100:
            st.info("완벽합니다! 모두 맞혔습니다.")

        if st.button("목록으로 돌아가기", use_container_width=True): 
            st.session_state.selected_quiz = ""
            st.session_state.review_data = [] # 다른 퀴즈를 위해 오답 기록 초기화
            st.rerun()
