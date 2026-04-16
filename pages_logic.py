import streamlit as st
import pandas as pd
import time
from database import get_chats, save_chat, save_setting, get_all_quizzes, save_result

# --- 🏆 구역별 최강자 로직 (유지) ---
def show_season_leaderboard(season_res, season_start):
    st.subheader("🏆 구역별 최강자")
    if not season_res: st.info("기록 없음")
    else:
        df = pd.DataFrame(season_res)
        st.markdown("### 🥇 우정 브레이커")
        top1 = df.sort_values(by=['Score', 'Duration'], ascending=[False, True]).groupby('QuizTitle').first()
        for idx, (u, c) in enumerate(top1['User'].value_counts().items()):
            st.write(f"{idx+1}위: **{u}** ({c}회 1등)")

# --- 💬 우정파괴창 로직 (유지) ---
def show_chat_room(player_name):
    c1, c2 = st.columns([3, 1])
    if c2.button("새로고침"): get_chats.clear(); st.rerun()
    chat_box = st.container(height=400)
    for c in get_chats():
        cls = "chat-sys" if c["User"] == "💻 시스템" else "chat-user"
        chat_box.markdown(f'<div class="chat-msg"><span class="{cls}">{c["User"]}:</span>{c["Message"]}</div>', unsafe_allow_html=True)
    with st.form("chat_input", clear_on_submit=True):
        m = st.text_input("메시지 입력", label_visibility="collapsed")
        if st.form_submit_button("전송") and m: save_chat(player_name, m); st.rerun()

# --- 🎯 퀴즈 선택 및 풀이 로직 (빈 공간 예약석 패치) ---
def show_quiz_area(quizzes, season_res, app_settings, player_name, robust_parse):
    all_cats = list(dict.fromkeys([q.get('Category','미분류') for q in quizzes]))
    custom_cats = [c.strip() for c in app_settings.get("custom_categories", "").split(",") if c.strip()]
    all_display_cats = list(dict.fromkeys(custom_cats + all_cats))
    
    # 기본 카테고리 설정
    default_cat = app_settings.get('default_category', all_display_cats[0] if all_display_cats else "")
    if default_cat in all_display_cats:
        all_display_cats.remove(default_cat)
        all_display_cats.insert(0, default_cat)

    tabs = st.tabs(all_display_cats)
    
    for i, cat in enumerate(all_display_cats):
        with tabs[i]:
            # 📌 [핵심 1] 상세 정보가 나타날 '예약석'을 버튼 목록보다 위에 선언
            # 이렇게 하면 버튼을 누르는 순간 이 자리에 랭킹과 시작 버튼이 쏙 들어갑니다.
            detail_placeholder = st.empty()

            cat_qs = sorted([q for q in quizzes if q.get('Category') == cat], key=lambda x: x['Title'])
            
            if not cat_qs: 
                st.caption("등록된 퀴즈 없음")
            else:
                st.caption("👇 퀴즈를 선택하면 위쪽에 상세 정보가 나타납니다.")
                cols = st.columns(2)
                for j, q in enumerate(cat_qs):
                    if cols[j%2].button(q['Title'], use_container_width=True, key=f"q_{i}_{j}"):
                        st.session_state.selected_quiz = q['Title']
                        st.session_state.quiz_finished = False
                        st.session_state.user_answers = {}
                        st.session_state.answered_list = []
                        st.session_state.start_time = None
                        st.rerun()

            # 📌 [핵심 2] 선택된 퀴즈 정보를 '예약석(placeholder)' 안으로 밀어넣기
            if st.session_state.selected_quiz:
                selected_q_item = next((q for q in quizzes if q['Title'] == st.session_state.selected_quiz), None)
                if selected_q_item and selected_q_item.get('Category') == cat:
                    with detail_placeholder.container():
                        render_quiz_detail(selected_q_item, season_res, app_settings, player_name, robust_parse)

# --- 🛠️ 퀴즈 상세 화면 렌더링 함수 ---
def render_quiz_detail(q_item, season_res, app_settings, player_name, robust_parse):
    # 시각적 구분 박스
    with st.container(border=True):
        st.markdown(f"### 📍 {q_item['Title']}")
        q_res = [r for r in season_res if r.get('QuizTitle') == q_item['Title']]
        
        # 지배자 랭킹
        with st.expander("🥇 이 구역의 지배자들", expanded=True):
            if q_res:
                s_df = pd.DataFrame(q_res).sort_values(by=['Score', 'Duration'], ascending=[False, True]).reset_index(drop=True)
                s_df.index += 1
                st.table(s_df[['User', 'Score', 'Duration']].rename(columns={'User':'수험번호', 'Score':'점수', 'Duration':'시간'}))
                taunt = app_settings.get(f"taunt_{q_item['Title']}", "")
                if taunt: st.markdown(f'<div class="taunt-box">"{taunt}"<div class="taunt-author">- 1등 {s_df.iloc[0]["User"]} -</div></div>', unsafe_allow_html=True)
            else: st.info("첫 지배자가 되어보세요!")

        # 시작 버튼
        if st.session_state.start_time is None and not st.session_state.quiz_finished:
            if st.button("🚀 시험 시작하기", use_container_width=True, type="primary", key=f"start_{q_item['Title']}"): 
                st.session_state.start_time = time.time()
                st.rerun()
        
        # 퀴즈 풀이 로직
        elif not st.session_state.quiz_finished:
            parsed = robust_parse(q_item['Content'])
            is_realtime = "실시간" in app_settings.get('feedback_mode', '')
            for idx, it in enumerate(parsed):
                st.markdown(f"**Q{idx+1}.**")
                # 지문 처리
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