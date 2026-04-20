import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
import time
from database import get_chats, save_chat, save_result, save_quiz, save_wrong_answers
from utils import generate_quiz_with_ai, robust_parse

def show_season_leaderboard(season_res, season_start):
    """[리뉴얼] 이모지 없이 퀴즈별 상위 3위만 표시"""
    st.subheader("구역별 최강자")
    st.caption(f"이번 시즌 시작일: {season_start[:10]}")
    
    if not season_res:
        st.info("이번 시즌 기록이 없습니다.")
        return

    df = pd.DataFrame(season_res)
    quiz_titles = df['QuizTitle'].unique()

    for title in quiz_titles:
        st.markdown(f"#### {title}")
        quiz_df = df[df['QuizTitle'] == title].sort_values(
            by=['Score', 'Duration'], ascending=[False, True]
        ).reset_index(drop=True)

        for i in range(min(3, len(quiz_df))):
            row = quiz_df.iloc[i]
            st.write(f"{i+1}위: {row['User']} ({int(row['Score'])}점 / {row['Duration']}초)")
        st.write("") 

def show_chat_room(player_name, ui_labels):
    """채팅방: ui_labels를 받아 상단 타이틀을 동적으로 변경"""
    st.markdown("<div id='chat_top_anchor'></div>", unsafe_allow_html=True)
    c1, c2 = st.columns([3, 1])
    c1.subheader(ui_labels["TAB_CHAT"])
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

def show_quiz_area(quizzes, season_res, app_settings, player_name, robust_parse, current_mode, ui_labels):
    """현재 접속 모드(work/personal)에 따라 퀴즈를 필터링하여 보여줍니다."""
    
    # --- [핵심] 모드별 퀴즈 필터링 ---
    if current_mode == "work":
        filtered_quizzes = [q for q in quizzes if str(q.get('IsWork', 'X')) == 'O']
    else:
        filtered_quizzes = [q for q in quizzes if str(q.get('IsWork', 'X')) != 'O']
        
    cats_with_quizzes = set(q.get('Category', '미분류') for q in filtered_quizzes)
    custom_cats = [c.strip() for c in app_settings.get("custom_categories", "").split(",") if c.strip()]
    
    def_cat = ui_labels["DEFAULT_CATEGORY"]
    candidates = list(dict.fromkeys(custom_cats + list(cats_with_quizzes) + [def_cat]))
    
    all_display_cats = []
    for cat in candidates:
        if cat == def_cat or cat in cats_with_quizzes:
            all_display_cats.append(cat)
    
    if def_cat in all_display_cats:
        all_display_cats.remove(def_cat)
        all_display_cats.insert(0, def_cat)

    if not all_display_cats:
        st.info("현재 모드에 표시할 퀴즈 카테고리가 없습니다.")
        return

    tabs = st.tabs(all_display_cats)
    for i, cat in enumerate(all_display_cats):
        with tabs[i]:
            st.write("") 
            # AI 퀴즈 생성기는 기본 카테고리(개인:우정퀴즈, 업무:공통 역량) 탭에서만 활성화
            if cat == def_cat:
                with st.expander("나만의 AI 퀴즈 만들기", expanded=False):
                    q_title = st.text_input("퀴즈 제목", placeholder="제목 입력", key=f"new_q_title_{i}")
                    q_topic = st.text_input("퀴즈 주제", placeholder="주제 입력", key=f"new_q_topic_{i}")
                    if st.button("AI 출제 시작", use_container_width=True, key=f"btn_ai_{i}"):
                        api_key = st.secrets.get("GEMINI_API_KEY")
                        if api_key and q_title and q_topic:
                            with st.spinner("생성 중..."):
                                try:
                                    text = generate_quiz_with_ai(api_key, q_topic)
                                    is_work_flag = (current_mode == "work")
                                    from database import get_all_quizzes
                                    save_quiz(def_cat, q_title, text, is_work=is_work_flag)
                                    st.success("배포 완료")
                                    time.sleep(1)
                                    get_all_quizzes.clear()
                                    st.rerun()
                                except Exception as e:
                                    st.error(f"오류: {e}")
                st.divider()

            cat_qs = [q for q in filtered_quizzes if q.get('Category') == cat]
            
            # 정렬 기준
            if cat == def_cat:
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
                        st.session_state.quiz_jump = True
                        st.rerun()

            if st.session_state.selected_quiz:
                selected_q_item = next((q for q in filtered_quizzes if q['Title'] == st.session_state.selected_quiz), None)
                if selected_q_item and selected_q_item.get('Category') == cat:
                    render_quiz_detail(selected_q_item, season_res, app_settings, player_name, robust_parse)

def render_quiz_detail(q_item, season_res, app_settings, player_name, robust_parse):
    # 자동 스크롤 기능
    st.markdown("<div id='quiz_start_anchor'></div>", unsafe_allow_html=True)
    if st.session_state.get('quiz_jump'):
        components.html(
            """
            <script>
                window.parent.document.getElementById('quiz_start_anchor').scrollIntoView({behavior: 'smooth'});
            </script>
            """,
            height=0
        )
        st.session_state.quiz_jump = False

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
                    with st.container(border=True):
                        st.markdown(f"📄 **[지문]**\n\n{it['p']}")
                
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
                    st.markdown(f"💡 **[해설]** {it['e']}")

            st.write("")
            if parsed and st.button("최종 제출", use_container_width=True):
                wrongs_for_results = []
                wrongs_for_conquest = []
                review_list = []
                
                for k, it in enumerate(parsed):
                    u = st.session_state.user_answers.get(f"ans_{k}")
                    if u is None or u == "":
                        u = st.session_state.get(f"in_{k}", "")
                        
                    c = str(it['a']) if it['o'] == ["주관식"] else it['o'][it['a']]
                    is_c = (str(u).replace(" ","").lower() == str(c).replace(" ","").lower()) if it['o'] == ["주관식"] else (str(u) == str(c))
                    
                    if not is_c: 
                        wrongs_for_results.append(it['k'])
                        wrongs_for_conquest.append(it['q'])
                        review_list.append({
                            'idx': k + 1, 'q': it['q'], 'u': u if u else "미입력", 'c': c, 'e': it['e']
                        })
                
                score = ((len(parsed)-len(review_list))/len(parsed))*100
                save_result(q_item['Title'], player_name, score, time.time()-st.session_state.start_time, wrongs_for_results)
                
                # 오답 시트에 기록
                if wrongs_for_conquest:
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
                    st.markdown(f"💡 **[해설]** {rev['e']}")
        elif int(st.session_state.last_score) == 100:
            st.info("완벽합니다! 모두 맞혔습니다.")

        if st.button("목록으로 돌아가기", use_container_width=True): 
            st.session_state.selected_quiz = ""
            st.session_state.review_data = []
            st.rerun()