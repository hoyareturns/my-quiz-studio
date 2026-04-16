import streamlit as st
import pandas as pd
import time
from datetime import datetime, timedelta
import qrcode
import re
from io import BytesIO
from database import (get_all_quizzes, get_all_results, get_settings, save_setting, 
                      get_chats, save_chat, get_weak_points, update_quiz, delete_quiz, 
                      save_result)
from utils import robust_parse

# 💡 한국 표준시(KST) 계산 함수
def get_kst_time():
    return (datetime.utcnow() + timedelta(hours=9)).strftime('%Y-%m-%d %H:%M:%S')

# --- 0. 페이지 설정 및 디자인 ---
st.set_page_config(page_title="우정 파괴소", layout="centered")
st.markdown("""
<style>
[data-testid="stMain"] blockquote {
    background-color: var(--secondary-background-color) !important; 
    border: 1px solid var(--border-color) !important;
    border-left: 4px solid var(--primary-color) !important; 
    padding: 16px !important; border-radius: 6px !important; 
    color: var(--text-color) !important; font-style: normal !important;
}
.question-header { font-size: 16px; font-weight: 700; color: #ff4b4b; margin-top: 24px; margin-bottom: 8px; }

/* 채팅창 스타일 */
.chat-msg { padding: 10px; border-radius: 8px; margin-bottom: 8px; background-color: var(--secondary-background-color); color: var(--text-color); }
.chat-user { font-weight: 600; color: var(--primary-color); font-size: 13px; margin-right: 5px; }
.chat-sys { font-weight: 800; color: #ff4b4b; font-size: 13px; margin-right: 5px; }
.chat-time { font-size: 11px; opacity: 0.5; float: right; margin-left: 10px; }

/* 1등 도발 메시지 박스 */
.taunt-box { background-color: #2c3e50; color: white; padding: 12px; border-radius: 8px; text-align: center; font-weight: bold; margin-bottom: 15px; box-shadow: 0 4px 6px rgba(0,0,0,0.1); }
.taunt-author { font-size: 12px; opacity: 0.8; margin-top: 4px; }

/* 모바일 최적화 */
.stButton > button { padding: 0.3rem 0.5rem !important; min-height: 2.2rem !important; border-radius: 6px !important; font-size: 14px !important; }
[data-testid="column"] { padding: 0 4px !important; }
div[data-testid="stVerticalBlock"] > div { padding-bottom: 0.2rem !important; }
@media (max-width: 768px) { 
    [data-testid="stTabs"] [data-testid="column"] { flex: 1 1 calc(50% - 8px) !important; min-width: calc(45%) !important; } 
}
</style>
""", unsafe_allow_html=True)

# --- 1. 초기 설정 및 세션 ---
APP_URL = "https://hoya-quiz-studio.streamlit.app"
ADMIN_PASSWORD = "1234"
app_settings = get_settings()

if 'player_name' not in st.session_state or not st.session_state.player_name:
    results = get_all_results()
    nums = [int(re.match(r"우정파괴자(\d+)", str(r.get('User',''))).group(1)) 
            for r in results if re.match(r"우정파괴자(\d+)", str(r.get('User','')))]
    st.session_state.player_name = f"우정파괴자{max(nums + [0]) + 1}"

for k in ['selected_quiz', 'user_answers', 'quiz_finished', 'start_time', 'review_data']:
    if k not in st.session_state: st.session_state[k] = "" if k == 'selected_quiz' else {} if k == 'user_answers' else False if k == 'quiz_finished' else None

# 시즌 초기화 시간 확인
season_start = app_settings.get('season_start', '2000-01-01 00:00:00')

# --- 2. 사이드바 (출제 위원실) ---
with st.sidebar:
    admin_btn_name = app_settings.get("admin_btn_name", "출제 위원실 (관리자)")
    st.subheader(admin_btn_name)
    
    pw_input = st.text_input("비밀번호", type="password", placeholder="Password", label_visibility="collapsed")
    
    if pw_input == ADMIN_PASSWORD:
        st.success("인증 완료")
        
        st.info("AI 출제 프롬프트 (복사해서 바로 사용)")
        st.code("""아래 형식에 맞춰 [ ] 10문제를 출제해.
인사말 쓰지 말고 [Q1]부터 출력해. 그림, 표, 그래프 등 텍스트로 표현할 수 없는 자료는 절대 포함하지 마.

[객관식 포맷]
[Q] <지문> (수식은 $ 기호 사용) </지문> 
[O] ① 보기1 ② 보기2 ③ 보기3 ④ 보기4 ⑤ 보기5
[A] 정답 기호(예: ②)
[K] 키워드

[주관식 포맷]
[Q] <지문> (수식은 $ 기호 사용) </지문> 
[O] 주관식
[A] 단답형 정답 (예: 아몬드)
[K] 키워드""", language="text")
        
        all_q = get_all_quizzes()
        custom_cats = [c.strip() for c in app_settings.get("custom_categories", "").split(",") if c.strip()]
        all_cats = list(dict.fromkeys(custom_cats + [q.get('Category', '미분류') for q in all_q]))
        if not all_cats: all_cats = ["미분류"]

        # 📌 [신규] 시즌제 리셋 기능
        if st.button("🔥 새 시즌 시작 (랭킹 초기화)", use_container_width=True, type="primary"):
            save_setting("season_start", get_kst_time())
            save_chat("💻 시스템", "🚨 새로운 시즌이 시작되었습니다! 모든 랭킹이 초기화됩니다.")
            st.success("새 시즌이 시작되었습니다!")
            st.rerun()

        new_admin_name = st.text_input("메뉴 이름 변경", value=admin_btn_name)
        if new_admin_name != admin_btn_name: save_setting("admin_btn_name", new_admin_name); st.rerun()

        current_def = app_settings.get('default_category', all_cats[0])
        def_cat = st.selectbox("처음 열릴 카테고리", all_cats, index=all_cats.index(current_def) if current_def in all_cats else 0)
        if def_cat != current_def: save_setting("default_category", def_cat); st.rerun()
        
        v_opts = ["퀴즈 선택", "우정파괴창", "구역별 최강자"]
        def_view = st.selectbox("기본 시작 화면", v_opts, index=v_opts.index(app_settings.get('default_view', v_opts[0])) if app_settings.get('default_view') in v_opts else 0)
        if def_view != app_settings.get('default_view'): save_setting("default_view", def_view); st.rerun()

        with st.expander("그룹(카테고리) 추가"):
            new_g = st.text_input("새 그룹 이름")
            if st.button("추가") and new_g:
                save_setting("custom_categories", app_settings.get("custom_categories","") + f",{new_g}"); st.rerun()

        with st.expander("새 퀴즈 배포"):
            nc = st.selectbox("소속 카테고리 선택", all_cats)
            nt = st.text_input("퀴즈 제목")
            nx = st.text_area("AI 결과물 붙여넣기", height=150)
            if st.button("배포", use_container_width=True):
                if nc and nt and nx:
                    from database import get_worksheet
                    ws_q = get_worksheet("Quizzes")
                    if ws_q: ws_q.append_row([nc, nt, nx, get_kst_time()]); get_all_quizzes.clear(); st.success("배포 성공!"); st.rerun()

        with st.expander("퀴즈 수정/삭제"):
            if all_q:
                sel_q_tit = st.selectbox("관리할 퀴즈", [q['Title'] for q in all_q])
                curr_q = next(q for q in all_q if q['Title'] == sel_q_tit)
                e_cat = st.selectbox("그룹 변경", all_cats, index=all_cats.index(curr_q['Category']) if curr_q['Category'] in all_cats else 0)
                e_tit = st.text_input("제목 변경", curr_q['Title'])
                if st.button("정보 수정"): update_quiz(sel_q_tit, e_cat, e_tit); st.rerun()
                if st.button("퀴즈 삭제"): delete_quiz(sel_q_tit); st.rerun()

# --- 3. 메인 화면 ---
st.title("우정 파괴소")
# 📌 세계관 반영: 수험번호
st.session_state.player_name = st.text_input("수험번호 (자동발급/변경가능)", value=st.session_state.player_name)
view_mode = st.radio("화면 전환", ["퀴즈 선택", "우정파괴창", "구역별 최강자"], horizontal=True, label_visibility="collapsed", index=["퀴즈 선택", "우정파괴창", "구역별 최강자"].index(app_settings.get('default_view', "퀴즈 선택") if app_settings.get('default_view') in ["퀴즈 선택", "우정파괴창", "구역별 최강자"] else 0))

# 📌 데이터 필터링 (현재 시즌 기록만 가져오기)
all_res = get_all_results()
season_res = [r for r in all_res if r.get('Time', '') >= season_start]

# ==========================================
# 🏆 탭 1: 구역별 최강자 (종합 랭킹)
# ==========================================
if view_mode == "구역별 최강자":
    st.subheader("🏆 구역별 최강자 (시즌 랭킹)")
    st.caption(f"이번 시즌 시작일: {season_start[:10]}")
    
    if not season_res:
        st.info("아직 이번 시즌의 기록이 없습니다. 첫 번째 전설이 되어보세요!")
    else:
        df = pd.DataFrame(season_res)
        
        # 🥇 1. 우정 브레이커 (1위 탈환 횟수)
        st.markdown("### 🥇 우정 브레이커 (1위 횟수)")
        first_places = df.sort_values(by=['Score', 'Duration'], ascending=[False, True]).groupby('QuizTitle').first()
        breaker_counts = first_places['User'].value_counts()
        if not breaker_counts.empty:
            for idx, (user, count) in enumerate(breaker_counts.items()):
                st.write(f"{idx+1}위: **{user}** ({count}회 1등)")
        else: st.caption("아직 1등 기록이 없습니다.")
        
        st.divider()
        user_stats = df.groupby('User').agg(AvgScore=('Score', 'mean'), Attempts=('Score', 'count'))
        valid_users = user_stats[user_stats['Attempts'] >= 2] # 최소 2번 이상 푼 사람만
        
        col1, col2 = st.columns(2)
        # 🎯 2. 고인물 (평균 정답률 Top)
        with col1:
            st.markdown("### 🎯 고인물")
            st.caption("최고 평균 점수 (2회 이상)")
            if not valid_users.empty:
                masters = valid_users.sort_values(by='AvgScore', ascending=False).head(3)
                for i, (user, row) in enumerate(masters.iterrows()):
                    st.write(f"{i+1}위: **{user}** ({row['AvgScore']:.1f}점)")
            else: st.caption("참여 부족")
            
        # 💀 3. 불명예의 전당 (동네북)
        with col2:
            st.markdown("### 💀 동네북")
            st.caption("최저 평균 점수 (2회 이상)")
            if not valid_users.empty:
                noobs = valid_users.sort_values(by='AvgScore', ascending=True).head(3)
                for i, (user, row) in enumerate(noobs.iterrows()):
                    st.write(f"{i+1}위: **{user}** ({row['AvgScore']:.1f}점)")
            else: st.caption("참여 부족")
        
        st.divider()
        # 🔥 4. 연속 만점 (가장 많은 만점 횟수)
        st.markdown("### 🔥 만점 폭격기")
        st.caption("시즌 내 100점 달성 횟수")
        perfects = df[df['Score'] == 100].groupby('User').size().sort_values(ascending=False).head(3)
        if not perfects.empty:
            for i, (user, count) in enumerate(perfects.items()):
                st.write(f"{i+1}위: **{user}** (만점 {count}회)")
        else: st.caption("아직 만점자가 없습니다.")

# ==========================================
# 💬 탭 2: 우정파괴창 (채팅 및 시스템 알림)
# ==========================================
elif view_mode == "우정파괴창":
    c1, c2 = st.columns([3, 1])
    c1.subheader("우정파괴창")
    if c2.button("새로고침", use_container_width=True):
        get_chats.clear(); st.rerun()
        
    chat_container = st.container(height=400)
    for chat in get_chats():
        chat_time_str = str(chat.get('Time', ''))[:16] 
        # 시스템 메시지는 빨간색으로 특별 취급
        if chat["User"] == "💻 시스템":
            chat_container.markdown(f'<div class="chat-msg" style="border: 1px solid #ff4b4b;"><span class="chat-sys">{chat["User"]}:</span>{chat["Message"]}<span class="chat-time">{chat_time_str}</span></div>', unsafe_allow_html=True)
        else:
            chat_container.markdown(f'<div class="chat-msg"><span class="chat-user">{chat["User"]}:</span>{chat["Message"]}<span class="chat-time">{chat_time_str}</span></div>', unsafe_allow_html=True)
        
    with st.form("chat", clear_on_submit=True):
        m = st.text_input("메시지 입력", label_visibility="collapsed")
        if st.form_submit_button("전송", use_container_width=True) and m:
            save_chat(st.session_state.player_name, m); st.rerun()

# ==========================================
# 🎯 탭 3: 퀴즈 선택 및 풀이
# ==========================================
else:
    quiz_data = get_all_quizzes()
    custom_cats = [c.strip() for c in app_settings.get("custom_categories", "").split(",") if c.strip()]
    all_cats = list(dict.fromkeys(custom_cats + [q.get('Category', '미분류') for q in quiz_data]))
    pref = app_settings.get('default_category', '').strip()
    if pref in all_cats: all_cats.remove(pref); all_cats.insert(0, pref)
    
    tabs = st.tabs(all_cats)
    for i, cat in enumerate(all_cats):
        with tabs[i]:
            cat_qs = sorted([q for q in quiz_data if q.get('Category','미분류') == cat], key=lambda x: x['Title'])
            if not cat_qs: st.caption("아직 이 그룹에 등록된 퀴즈가 없습니다.")
            else:
                cols = st.columns(2)
                for j, q in enumerate(cat_qs):
                    if cols[j%2].button(q['Title'], use_container_width=True, key=f"q_{cat}_{j}"):
                        st.session_state.selected_quiz = q['Title']; st.session_state.quiz_finished = False; st.rerun()

    if st.session_state.selected_quiz:
        st.divider()
        st.subheader(f"{st.session_state.selected_quiz}")
        q_item = next(q for q in quiz_data if q['Title'] == st.session_state.selected_quiz)
        
        # 📌 해당 퀴즈의 시즌 결과 필터링
        q_res = [r for r in season_res if r.get('QuizTitle') == q_item['Title']]
        
        # 📌 [신규] 1등 정보 계산 및 도발 메시지 출력
        current_1st_user = None
        current_best_score = -1
        current_best_time = 9999
        
        if q_res:
            sorted_res = sorted(q_res, key=lambda x: (-x['Score'], x['Duration']))
            current_1st_user = sorted_res[0]['User']
            current_best_score = sorted_res[0]['Score']
            current_best_time = sorted_res[0]['Duration']
            
            # 도발 메시지가 있으면 출력
            taunt_msg = app_settings.get(f"taunt_{q_item['Title']}", "")
            if taunt_msg:
                st.markdown(f'<div class="taunt-box">"{taunt_msg}"<div class="taunt-author">- 현재 1등 {current_1st_user} -</div></div>', unsafe_allow_html=True)
            
            # 내가 1등이면 도발 메시지 작성 폼 표시
            if current_1st_user == st.session_state.player_name:
                with st.expander("👑 1등의 특권: 도발 메시지 남기기", expanded=False):
                    new_taunt = st.text_input("친구들을 도발해보세요!", value=taunt_msg, placeholder="ㅋㅋ 아직도 안 풀었냐?")
                    if st.button("메시지 걸기"):
                        save_setting(f"taunt_{q_item['Title']}", new_taunt); st.success("적용 완료!"); st.rerun()

        with st.expander("이 구역의 지배자들 (실시간 랭킹)", expanded=False):
            if q_res: st.dataframe(pd.DataFrame(sorted_res)[['User', 'Score', 'Duration']], use_container_width=True)
            else: st.caption("첫 번째 지배자가 되어보세요!")
            
        if st.session_state.start_time is None and not st.session_state.quiz_finished:
            if st.button("시험 시작하기", use_container_width=True, type="primary"):
                st.session_state.start_time = time.time(); st.rerun()
        
        elif not st.session_state.quiz_finished:
            parsed = robust_parse(q_item['Content'])
            for idx, it in enumerate(parsed):
                st.markdown(f'<p class="question-header">Q{idx+1}.</p>', unsafe_allow_html=True)
                if "<지문>" in it['q']:
                    p = it['q'].split("<지문>")
                    st.markdown(p[0]); st.markdown("\n".join([f"> {l}" for l in p[1].split("</지문>")[0].strip().split('\n')]))
                    if len(p[1].split("</지문>")) > 1: st.markdown(p[1].split("</지문>")[1])
                else: st.markdown("\n".join([f"> {l}" for l in it['q'].strip().split('\n')]))
                
                is_ans = f"ans_{idx}" in st.session_state.user_answers
                f_mode = app_settings.get('feedback_mode','실시간 팩폭 (즉시 확인)')
                
                if it['o'] == ["주관식"]:
                    ans = st.text_input(f"정답 입력_{idx}", key=f"r_{idx}", disabled=is_ans if "실시간" in f_mode else False, placeholder="정답을 입력하세요")
                    correct_ans = str(it['a'])
                else:
                    ans = st.radio(f"보기_{idx}", it['o'], index=None, key=f"r_{idx}", disabled=is_ans if "실시간" in f_mode else False, label_visibility="collapsed")
                    correct_ans = it['o'][it['a']]
                
                if ans:
                    st.session_state.user_answers[f"ans_{idx}"] = ans
                    if "실시간" in f_mode:
                        is_correct = (ans.replace(" ", "").lower() == correct_ans.replace(" ", "").lower()) if it['o'] == ["주관식"] else (ans == correct_ans)
                        if is_correct: st.success("정답입니다!")
                        else: st.error(f"오답! (정답: {correct_ans})")
            
            if st.button("답안 제출 (미응답 시 오답)", use_container_width=True):
                wrongs, revs = [], []
                for k, it in enumerate(parsed):
                    u = st.session_state.user_answers.get(f"ans_{k}")
                    if it['o'] == ["주관식"]:
                        c = str(it['a'])
                        is_c = (u is not None and u.replace(" ", "").lower() == c.replace(" ", "").lower())
                    else:
                        c = it['o'][it['a']]
                        is_c = (u == c)
                        
                    if not u: wrongs.append(it['k']); revs.append({"q":it['q'], "is_u":True})
                    else:
                        if not is_c: wrongs.append(it['k'])
                        revs.append({"q":it['q'], "u":u, "c":c, "is_c":is_c, "is_u":False})
                        
                score = ((len(parsed)-len(wrongs))/len(parsed))*100
                duration = time.time()-st.session_state.start_time
                
                # DB 저장
                save_result(q_item['Title'], st.session_state.player_name, score, duration, wrongs)
                
                # 📌 [신규] 시스템 알림 로직 (만점 및 1등 탈환)
                if score == 100:
                    save_chat("💻 시스템", f"🎉 [{st.session_state.player_name}]님이 '{q_item['Title']}'에서 만점을 달성했습니다!")
                
                if q_res: # 기존 기록이 있을 때만 1등 비교
                    if score > current_best_score or (score == current_best_score and duration < current_best_time):
                        save_chat("💻 시스템", f"🚨 [{st.session_state.player_name}]님이 '{q_item['Title']}'의 새로운 1등으로 등극했습니다!")
                else: # 첫 도전자일 경우
                    save_chat("💻 시스템", f"🚀 [{st.session_state.player_name}]님이 '{q_item['Title']}'의 첫 번째 지배자가 되었습니다!")

                st.session_state.quiz_finished = True; st.session_state.last_score = score; st.session_state.review_data = revs; st.rerun()

        if st.session_state.quiz_finished:
            if "실시간" not in app_settings.get('feedback_mode',''):
                with st.expander("전체 채점 결과 보기", expanded=True):
                    for i, r in enumerate(st.session_state.review_data):
                        if r.get('is_u'):
                            st.markdown(f"**Q{i+1}.** 미응답"); st.caption("정답 미제공")
                        else:
                            st.markdown(f"**Q{i+1}.** {'정답' if r['is_c'] else '오답'}")
                            if not r['is_c']: st.write(f"내 답: {r['u']} / 정답: **{r['c']}**")
            st.success(f"수고하셨습니다! 최종 점수: {int(st.session_state.last_score)}점"); st.button("다른 퀴즈 하러 가기", on_click=lambda: st.rerun(), use_container_width=True)