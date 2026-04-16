import streamlit as st
import pandas as pd
import time
from database import get_chats, save_chat, save_setting, get_all_quizzes, save_result

# --- 🏆 구역별 최강자 로직 ---
def show_season_leaderboard(season_res, season_start):
    st.subheader("🏆 구역별 최강자")
    st.caption(f"이번 시즌 시작일: {season_start[:10]}")
    if not season_res:
        st.info("이번 시즌 기록이 없습니다.")
    else:
        df = pd.DataFrame(season_res)
        st.markdown("### 🥇 우정 브레이커")
        first_places = df.sort_values(by=['Score', 'Duration'], ascending=[False, True]).groupby('QuizTitle').first()
        breaker_counts = first_places['User'].value_counts()
        for idx, (u, c) in enumerate(breaker_counts.items()):
            st.write(f"{idx+1}위: **{u}** ({c}회 1등)")
        
        st.divider()
        user_stats = df.groupby('User').agg(AvgScore=('Score', 'mean'), Attempts=('Score', 'count'))
        valid_u = user_stats[user_stats['Attempts'] >= 2]
        c1, c2 = st.columns(2)
        with c1:
            st.markdown("### 🎯 고인물")
            if not valid_u.empty:
                for u, r in valid_u.sort_values('AvgScore', ascending=False).head(3).iterrows():
                    st.write(f"**{u}** ({r['AvgScore']:.1f}점)")
        with c2:
            st.markdown("### 💀 동네북")
            if not valid_u.empty:
                for u, r in valid_u.sort_values('AvgScore', ascending=True).head(3).iterrows():
                    st.write(f"**{u}** ({r['AvgScore']:.1f}점)")

# --- 💬 우정파괴창 로직 ---
def show_chat_room(player_name):
    c1, c2 = st.columns([3, 1])
    c1.subheader("우정파괴창")
    if c2.button("새로고침"): get_chats.clear(); st.rerun()
    
    chat_box = st.container(height=400)
    for c in get_chats():
        t_str = str(c.get('Time', ''))[:16]
        cls = "chat-sys" if c["User"] == "💻 시스템" else "chat-user"
        chat_box.markdown(f'<div class="chat-msg"><span class="{cls}">{c["User"]}:</span>{c["Message"]}<span class="chat-time">{t_str}</span></div>', unsafe_allow_html=True)
    
    with st.form("chat_input", clear_on_submit=True):
        m = st.text_input("메시지 입력", label_visibility="collapsed")
        if st.form_submit_button("전송", use_container_width=True) and m:
            save_chat(player_name, m); st.rerun()

# --- 🎯 퀴즈 선택 및 풀이 로직 (위치 최적화 버전) ---
def show_quiz_area(quizzes, season_res, app_settings, player_name, robust_parse):
    all_cats = list(dict.fromkeys([q.get('Category','미분류') for q in quizzes]))
    custom_cats = [c.strip() for c in app_settings.get("custom_categories", "").split(",") if c.strip()]
    all_display_cats = list(dict.fromkeys(custom_cats + all_cats))
    
    tabs = st.tabs(all_display_cats)
    for i, cat in enumerate(all_display_cats):
        with tabs[i]:
            # 📌 퀴즈 목록 출력
            cat_qs = sorted([q for q in quizzes if q.get('Category') == cat], key=lambda x: x['Title'])
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
                        st.rerun()

            # 📌 [핵심 수정] 선택한 퀴즈가 현재 탭(Category)에 속해 있다면, 탭 내부 바로 아래에 상세 정보 출력
            if st.session_state.selected_quiz:
                # 현재 선택된 퀴즈 객체 찾기
                selected_q_item = next((q for q in quizzes if q['Title'] == st.session_state.selected_quiz), None)
                
                # 선택된 퀴즈의 카테고리가 현재 탭의 카테고리와 일치할 때만 여기에 그림
                if selected_q_item and selected_q_item.get('Category') == cat:
                    render_quiz_detail(selected_q_item, season_res, app_settings, player_name, robust_parse)

# --- 🛠️ 퀴즈 상세 화면 렌더링 함수 (중복 제거용 분리) ---
def render_quiz_detail(q_item, season_res, app_settings, player_name, robust_parse):
    st.divider()
    st.subheader(f"📍 {q_item['Title']}")
    q_res = [r for r in season_res if r.get('QuizTitle') == q_item['Title']]
    
    # 지배자 랭킹 및 도발
    with st.expander("🥇 이 구역의 지배자들", expanded=True):
        if q_res:
            s_df = pd.DataFrame(q_res).sort_values(by=['Score', 'Duration'], ascending=[False, True]).reset_index(drop=True)
            s_df.index += 1
            st.table(s_df[['User', 'Score', 'Duration']].rename(columns={'User':'수험번호', 'Score':'점수', 'Duration':'시간'}))
            taunt = app_settings.get(f"taunt_{q_item['Title']}", "")
            if taunt: st.markdown(f'<div class="taunt-box">"{taunt}"<div class="taunt-author">- 1등 {s_df.iloc[0]["수험번호"]} -</div></div>', unsafe_allow_html=True)
            if s_df.iloc[0]['수험번호'] == player_name:
                new_t = st.text_input("도발 수정", value=taunt, key=f"taunt_edit_{q_item['Title']}")
                if st.button("도발 저장", key=f"taunt_save_{q_item['Title']}"): save_setting(f"taunt_{q_item['Title']}", new_t); st.rerun()
        else: st.info("첫 지배자가 되어보세요!")

    # 시험 시작 및 문제 풀이
    if st.session_state.start_time is None and not st.session_state.quiz_finished:
        if st.button("🚀 시험 시작", use_container_width=True, type="primary"): 
            st.session_state.start_time = time.time(); st.rerun()
    
    elif not st.session_state.quiz_finished:
        parsed = robust_parse(q_item['Content'])
        is_realtime = "실시간" in app_settings.get('feedback_mode', '')
        
        for idx, it in enumerate(parsed):
            st.markdown(f'<p class="question-header">Q{idx+1}.</p>', unsafe_allow_html=True)
            q_text = it['q']
            if "<지문>" in q_text:
                parts = q_text.split("<지문>")
                st.markdown(parts[0].strip())
                st.markdown("\n".join([f"> {l}" for l in parts[1].split("</지문>")[0].strip().split('\n')]))
                if "</지문>" in parts[1]:
                    after = parts[1].split("</지문>")[1].strip()
                    if after: st.markdown(after)
            else: st.markdown(q_text)
            
            is_short = it['o'] == ["주관식"]
            is_disabled = is_realtime and (idx in st.session_state.answered_list)
            
            if is_short:
                ans = st.text_input(f"답_{idx}", key=f"in_{idx}", disabled=is_disabled)
            else:
                ans = st.radio(f"보기_{idx}", it['o'], index=None, key=f"in_{idx}", label_visibility="collapsed", disabled=is_disabled)
            
            if ans:
                st.session_state.user_answers[f"ans_{idx}"] = ans
                if is_realtime and idx not in st.session_state.answered_list:
                    st.session_state.answered_list.append(idx); st.rerun()
                if is_realtime:
                    c_ans = str(it['a']) if is_short else it['o'][it['a']]
                    is_c = (ans.replace(" ","").lower() == c_ans.replace(" ","").lower()) if is_short else (ans == c_ans)
                    if is_c: st.success("정답!")
                    else: st.error(f"오답! (정답: {c_ans})"); st.markdown(f'<div class="exp-box"><b>📝 해설:</b><br>{it["e"]}</div>', unsafe_allow_html=True)

        if st.button("🏁 최종 제출", use_container_width=True):
            wrongs, revs = [], []
            for k, it in enumerate(parsed):
                u = st.session_state.user_answers.get(f"ans_{k}")
                c = str(it['a']) if it['o'] == ["주관식"] else it['o'][it['a']]
                is_c = (u and u.replace(" ","").lower() == c.replace(" ","").lower()) if it['o'] == ["주관식"] else (u == c)
                if not is_c: wrongs.append(it['k'])
                revs.append({"is_c":is_c, "u":u, "c":c, "e":it['e']})
            
            score = ((len(parsed)-len(wrongs))/len(parsed))*100
            save_result(q_item['Title'], player_name, score, time.time()-st.session_state.start_time, wrongs)
            if score == 100: save_chat("💻 시스템", f"🎉 [{player_name}]님이 '{q_item['Title']}' 만점!")
            st.session_state.quiz_finished = True; st.session_state.last_score = score; st.session_state.review_data = revs; st.rerun()

    if st.session_state.quiz_finished:
        if "최후" in app_settings.get('feedback_mode', ''):
            with st.expander("📝 전체 해설", expanded=True):
                for i, r in enumerate(st.session_state.review_data):
                    st.markdown(f"**Q{i+1}. {'⭕' if r['is_c'] else '❌'}**")
                    if not r['is_c']: st.write(f"내 답: {r['u']} / 정답: **{r['c']}**"); st.markdown(f'<div class="exp-box">{r["e"]}</div>', unsafe_allow_html=True)
        st.success(f"🎊 점수: {int(st.session_state.last_score)}점")
        if st.button("목록으로", use_container_width=True, key=f"back_btn_{q_item['Title']}"): 
            st.session_state.selected_quiz = ""; st.rerun()