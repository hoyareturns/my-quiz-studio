import streamlit as st
import pandas as pd
import time
import streamlit.components.v1 as components
from database import get_chats, save_chat, save_setting, get_all_quizzes, save_result

# --- 🏆 구역별 최강자 로직 ---
def show_season_leaderboard(season_res, season_start):
    st.subheader("🏆 구역별 최강자")
    st.caption(f"이번 시즌 시작일: {season_start[:10]}")
    if not season_res:
        st.info("이번 시즌 기록이 없습니다.")
    else:
        df = pd.DataFrame(season_res)
        
        # 1. 🥇 우정 브레이커 (1등 횟수)
        st.markdown("### 🥇 우정 브레이커")
        first_places = df.sort_values(by=['Score', 'Duration'], ascending=[False, True]).groupby('QuizTitle').first()
        breaker_counts = first_places['User'].value_counts()
        if not breaker_counts.empty:
            for idx, (u, c) in enumerate(breaker_counts.items()):
                st.write(f"{idx+1}위: **{u}** ({c}회 1등)")
        else:
            st.write("아직 1등 기록이 없습니다.")
        
        st.divider()
        
        # 2. 🎯 고인물 & 💀 동네북 (평균 점수, 2회 이상 참여자 기준)
        user_stats = df.groupby('User').agg(AvgScore=('Score', 'mean'), Attempts=('Score', 'count'))
        valid_u = user_stats[user_stats['Attempts'] >= 2]
        
        c1, c2 = st.columns(2)
        with c1:
            st.markdown("### 🎯 고인물")
            if not valid_u.empty:
                for u, r in valid_u.sort_values('AvgScore', ascending=False).head(3).iterrows():
                    st.write(f"**{u}** ({r['AvgScore']:.1f}점)")
            else:
                st.caption("2회 이상 참여자가 부족합니다.")
        with c2:
            st.markdown("### 💀 동네북")
            if not valid_u.empty:
                for u, r in valid_u.sort_values('AvgScore', ascending=True).head(3).iterrows():
                    st.write(f"**{u}** ({r['AvgScore']:.1f}점)")
            else:
                st.caption("2회 이상 참여자가 부족합니다.")

# --- 💬 우정파괴채팅 로직 ---
def show_chat_room(player_name):
    # 📌 점프를 위한 상단 앵커
    st.markdown("<div id='chat_top_anchor'></div>", unsafe_allow_html=True)
    
    c1, c2 = st.columns([3, 1])
    c1.subheader("💬 우정파괴채팅")
    if c2.button("새로고침", key="chat_refresh"): 
        get_chats.clear()
        st.rerun()
    
    chat_box = st.container(height=400)
    for c in get_chats():
        t_str = str(c.get('Time', ''))[:16]
        cls = "chat-sys" if c["User"] == "💻 시스템" else "chat-user"
        chat_box.markdown(f'<div class="chat-msg"><span class="{cls}">{c["User"]}:</span>{c["Message"]}<span class="chat-time">{t_str}</span></div>', unsafe_allow_html=True)
    
    with st.form("chat_input", clear_on_submit=True):
        m = st.text_input("메시지 입력", label_visibility="collapsed")
        if st.form_submit_button("전송", use_container_width=True) and m:
            save_chat(player_name, m)
            st.session_state.chat_jump = True 
            st.rerun()

    # 📌 채팅 탭 진입 시나 메시지 전송 시 상단으로 자동 스크롤
    components.html(
        """
        <script>
            window.parent.document.getElementById('chat_top_anchor').scrollIntoView({behavior: 'smooth'});
        </script>
        """,
        height=0
    )

# --- 🎯 퀴즈 선택 영역 ---
def show_quiz_area(quizzes, season_res, app_settings, player_name, robust_parse):
    all_cats = list(dict.fromkeys([q.get('Category','미분류') for q in quizzes]))
    custom_cats = [c.strip() for c in app_settings.get("custom_categories", "").split(",") if c.strip()]
    
    # "우정퀴즈" 카테고리가 없어도 탭이 생성되도록 강제 추가
    if "우정퀴즈" not in all_cats and "우정퀴즈" not in custom_cats:
        all_cats.append("우정퀴즈")
        
    all_display_cats = list(dict.fromkeys(custom_cats + all_cats))
    
    default_cat = app_settings.get('default_category', all_display_cats[0] if all_display_cats else "")
    if default_cat in all_display_cats:
        all_display_cats.remove(default_cat)
        all_display_cats.insert(0, default_cat)

    tabs = st.tabs(all_display_cats)
    
    for i, cat in enumerate(all_display_cats):
        with tabs[i]:
            cat_qs = [q for q in quizzes if q.get('Category') == cat]
            
            # 📌 카테고리별 정렬 방식 분기 (우정퀴즈는 인기순 정렬 유지)
            if cat == "우정퀴즈":
                if season_res:
                    pop_counts = pd.DataFrame(season_res)['QuizTitle'].value_counts().to_dict()
                else:
                    pop_counts = {}
                cat_qs = sorted(cat_qs, key=lambda x: pop_counts.get(x['Title'], 0), reverse=True)
            else:
                cat_qs = sorted(cat_qs, key=lambda x: x['Title'])
            
            if not cat_qs: 
                st.caption("등록된 퀴즈 없음")
            else:
                cols = st.columns(2)
                for j, q in enumerate(cat_qs):
                    if cols[j%2].button(q['Title'], use_container_width=True, key=f"q_{i}_{j}"):
                        st.session_state.selected_quiz = q['Title']
                        st.session_state.quiz_finished = False
                        st.session_state.user_answers = {}
                        st.session_state.answered_list = []
                        st.session_state.start_time = None
                        st.session_state.should_jump = True
                        st.rerun()

            if st.session_state.selected_quiz:
                selected_q_item = next((q for q in quizzes if q['Title'] == st.session_state.selected_quiz), None)
                if selected_q_item and selected_q_item.get('Category') == cat:
                    st.markdown("<div id='quiz_bottom_anchor'></div>", unsafe_allow_html=True)
                    render_quiz_detail(selected_q_item, season_res, app_settings, player_name, robust_parse)
                    
                    if st.session_state.get('should_jump', False):
                        components.html(
                            """
                            <script>
                                window.parent.document.getElementById('quiz_bottom_anchor').scrollIntoView({behavior: 'smooth'});
                            </script>
                            """,
                            height=0
                        )
                        st.session_state.should_jump = False

# --- 🛠️ 퀴즈 상세 화면 렌더링 함수 ---
def render_quiz_detail(q_item, season_res, app_settings, player_name, robust_parse):
    with st.container(border=True):
        st.markdown(f"### 📍 {q_item['Title']}")
        q_res = [r for r in season_res if r.get('QuizTitle') == q_item['Title']]
        
        with st.expander("🥇 이 구역의 지배자들", expanded=True):
            if q_res:
                s_df = pd.DataFrame(q_res).sort_values(by=['Score', 'Duration'], ascending=[False, True]).reset_index(drop=True)
                s_df.index += 1
                st.table(s_df[['User', 'Score', 'Duration']].rename(columns={'User':'수험번호', 'Score':'점수', 'Duration':'시간'}))
                taunt = app_settings.get(f"taunt_{q_item['Title']}", "")
                if taunt: st.markdown(f'<div class="taunt-box">"{taunt}"<div class="taunt-author">- 1등 {s_df.iloc[0]["User"]} -</div></div>', unsafe_allow_html=True)
            else: st.info("첫 지배자가 되어보세요!")

        if st.session_state.start_time is None and not st.session_state.quiz_finished:
            if st.button("🚀 시험 시작하기", use_container_width=True, type="primary", key=f"start_{q_item['Title']}"): 
                st.session_state.start_time = time.time()
                st.rerun()
        
        elif not st.session_state.quiz_finished:
            parsed = robust_parse(q_item['Content'])
            is_realtime = "실시간" in app_settings.get('feedback_mode', '')
            for idx, it in enumerate(parsed):
                st.markdown(f"**Q{idx+1}.**")
                q_text = it['q']
                if "<지문>" in q_text:
                    parts = q_text.split("<지문>")
                    st.markdown(parts[0].strip())
                    st.markdown("\n".join([f"> {l}" for l in parts[1].split("</지문>")[0].strip().split('\n')]))
                    if "</지문>" in parts[1]: st.markdown(parts[1].split("</지문>")[1].strip())
                else: st.markdown(q_text)
                
                is_short = it['o'] == ["주관식"]
                is_disabled = is_realtime and (idx in st.session_state.answered_list)
                if is_short: ans = st.text_input(f"답_{idx}", key=f"in_{idx}", disabled=is_disabled)
                else: ans = st.radio(f"보기_{idx}", it['o'], index=None, key=f"in_{idx}", label_visibility="collapsed", disabled=is_disabled)
                
                if ans and is_realtime:
                    if idx not in st.session_state.answered_list:
                        st.session_state.user_answers[f"ans_{idx}"] = ans
                        st.session_state.answered_list.append(idx); st.rerun()
                    c_ans = str(it['a']) if is_short else it['o'][it['a']]
                    is_c = (ans.replace(" ","").lower() == c_ans.replace(" ","").lower()) if is_short else (ans == c_ans)
                    if is_c: st.success("정답!")
                    else: st.error(f"오답! (정답: {c_ans})"); st.markdown(f'<div class="exp-box">{it["e"]}</div>', unsafe_allow_html=True)

            if st.button("🏁 최종 제출", use_container_width=True, key=f"sub_{q_item['Title']}"):
                wrongs, revs = [], []
                for k, it in enumerate(parsed):
                    u = st.session_state.user_answers.get(f"ans_{k}")
                    c = str(it['a']) if it['o'] == ["주관식"] else it['o'][it['a']]
                    is_c = (u and u.replace(" ","").lower() == c.replace(" ","").lower()) if it['o'] == ["주관식"] else (u == c)
                    if not is_c: wrongs.append(it['k'])
                    revs.append({"is_c":is_c, "u":u, "c":c, "e":it['e']})
                score = ((len(parsed)-len(wrongs))/len(parsed))*100
                save_result(q_item['Title'], player_name, score, time.time()-st.session_state.start_time, wrongs)
                st.session_state.quiz_finished = True; st.session_state.last_score = score; st.session_state.review_data = revs; st.rerun()

    if st.session_state.quiz_finished:
        st.success(f"🎊 점수: {int(st.session_state.last_score)}점")
        if st.button("목록으로 돌아가기", use_container_width=True, key=f"bk_{q_item['Title']}"): 
            st.session_state.selected_quiz = ""; st.rerun()