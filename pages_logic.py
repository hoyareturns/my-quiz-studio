import streamlit as st
import pandas as pd
import time
import streamlit.components.v1 as components
from database import get_chats, save_chat, save_setting, get_all_quizzes, save_result, save_quiz
from utils import generate_quiz_with_ai

# --- 구역별 최강자 로직 ---
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

# --- 우정파괴채팅 로직 ---
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
            st.session_state.chat_jump = True 
            st.rerun()

# --- 퀴즈 선택 영역 ---
# (pages_logic.py 내 show_quiz_area 함수 부분 교체)
def show_quiz_area(quizzes, season_res, app_settings, player_name, robust_parse):
    # 카테고리 리스트 생성
    all_cats = list(dict.fromkeys([q.get('Category','미분류') for q in quizzes]))
    custom_cats = [c.strip() for c in app_settings.get("custom_categories", "").split(",") if c.strip()]
    if "우정퀴즈" not in all_cats: all_cats.append("우정퀴즈")
    
    all_display_cats = list(dict.fromkeys(custom_cats + all_cats))
    
    # [관리자 설정 연동] 처음 열릴 카테고리를 리스트 맨 앞으로 이동
    default_cat_name = app_settings.get("default_category", "우정퀴즈")
    if default_cat_name in all_display_cats:
        all_display_cats.remove(default_cat_name)
        all_display_cats.insert(0, default_cat_name)

    tabs = st.tabs(all_display_cats)
    
    for i, cat in enumerate(all_display_cats):
        with tabs[i]:
            # 우정퀴즈 탭인 경우 상단에 출제 메뉴 노출
            if cat == "우정퀴즈":
                with st.expander("나만의 우정 파괴 퀴즈 만들기", expanded=False):
                    q_title = st.text_input("퀴즈 제목", placeholder="예: 우리들의 비밀", key="new_q_title")
                    q_topic = st.text_input("퀴즈 주제", placeholder="예: 어제 먹은 점심 메뉴", key="new_q_topic")
                    if st.button("AI 출제 시작", use_container_width=True):
                        api_key = st.secrets.get("GEMINI_API_KEY")
                        if api_key and q_title and q_topic:
                            with st.spinner("생성 중..."):
                                try:
                                    # utils에서 함수를 가져와 실행하는 로직 유지
                                    generated_text = generate_quiz_with_ai(api_key, q_topic)
                                    save_quiz(q_title, "우정퀴즈", generated_text)
                                    st.success("배포 완료!")
                                    time.sleep(1)
                                    get_all_quizzes.clear()
                                    st.rerun()
                                except Exception as e:
                                    st.error(f"생성 실패: {e}")
                st.divider()

            # 해당 카테고리 퀴즈 목록 출력
            cat_qs = [q for q in quizzes if q.get('Category') == cat]
            # ... (이하 기존 퀴즈 버튼 생성 로직 유지)

            cat_qs = [q for q in quizzes if q.get('Category') == cat]
            if cat == "우정퀴즈":
                pop_counts = pd.DataFrame(season_res)['QuizTitle'].value_counts().to_dict() if season_res else {}
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
                    render_quiz_detail(selected_q_item, season_res, app_settings, player_name, robust_parse)

# --- 퀴즈 상세 화면 렌더링 ---
def render_quiz_detail(q_item, season_res, app_settings, player_name, robust_parse):
    with st.container(border=True):
        st.markdown(f"**{q_item['Title']}**")
        q_res = [r for r in season_res if r.get('QuizTitle') == q_item['Title']]
        
        with st.expander("이 구역의 지배자들", expanded=True):
            if q_res:
                s_df = pd.DataFrame(q_res).sort_values(by=['Score', 'Duration'], ascending=[False, True]).reset_index(drop=True)
                s_df.index += 1
                st.table(s_df[['User', 'Score', 'Duration']].rename(columns={'User':'수험번호', 'Score':'점수', 'Duration':'시간'}))
            else: st.info("첫 지배자가 되어보세요!")

        if st.session_state.start_time is None and not st.session_state.quiz_finished:
            if st.button("시험 시작하기", use_container_width=True, type="primary"): 
                st.session_state.start_time = time.time(); st.rerun()
        
        elif not st.session_state.quiz_finished:
            parsed = robust_parse(q_item['Content'])
            is_realtime = "실시간" in app_settings.get('feedback_mode', '')
            for idx, it in enumerate(parsed):
                st.markdown(f"**Q{idx+1}. {it['q']}**")
                is_short = it['o'] == ["주관식"]
                is_disabled = is_realtime and (idx in st.session_state.answered_list)
                if is_short: ans = st.text_input(f"답_{idx}", key=f"in_{idx}", disabled=is_disabled)
                else: ans = st.radio(f"보기_{idx}", it['o'], index=None, key=f"in_{idx}", label_visibility="collapsed", disabled=is_disabled)
                
                if ans and is_realtime and idx not in st.session_state.answered_list:
                    st.session_state.user_answers[f"ans_{idx}"] = ans
                    st.session_state.answered_list.append(idx); st.rerun()

            if st.button("최종 제출", use_container_width=True):
                wrongs = []
                for k, it in enumerate(parsed):
                    u = st.session_state.user_answers.get(f"ans_{k}")
                    c = str(it['a']) if it['o'] == ["주관식"] else it['o'][it['a']]
                    is_c = (u and u.replace(" ","").lower() == c.replace(" ","").lower()) if it['o'] == ["주관식"] else (u == c)
                    if not is_c: wrongs.append(it['k'])
                score = ((len(parsed)-len(wrongs))/len(parsed))*100
                save_result(q_item['Title'], player_name, score, time.time()-st.session_state.start_time, wrongs)
                st.session_state.quiz_finished = True; st.session_state.last_score = score; st.rerun()

    if st.session_state.quiz_finished:
        st.success(f"점수: {int(st.session_state.last_score)}점")
        if st.button("목록으로 돌아가기", use_container_width=True): 
            st.session_state.selected_quiz = ""; st.rerun()