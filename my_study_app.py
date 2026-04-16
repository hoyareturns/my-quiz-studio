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
from prompts import QUIZ_GENERATION_PROMPT

# --- 💡 공통 유틸리티 함수 ---
def get_kst_time():
    return (datetime.utcnow() + timedelta(hours=9)).strftime('%Y-%m-%d %H:%M:%S')

@st.cache_data(ttl=3600)
def generate_qr_code(url):
    qr = qrcode.QRCode(version=1, box_size=4, border=2)
    qr.add_data(url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buf = BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()

# --- 🎨 디자인 시스템 ---
st.set_page_config(page_title="우정 파괴소", layout="centered")
st.markdown("""
<style>
/* 지문/수식 박스 */
[data-testid="stMain"] blockquote {
    background-color: var(--secondary-background-color) !important; 
    border: 1px solid var(--border-color) !important;
    border-left: 4px solid var(--primary-color) !important; 
    padding: 16px !important; border-radius: 6px !important; 
    color: var(--text-color) !important; font-style: normal !important;
}
.question-header { font-size: 16px; font-weight: 700; color: #ff4b4b; margin-top: 24px; margin-bottom: 8px; }

/* 채팅 메시지 */
.chat-msg { padding: 10px; border-radius: 8px; margin-bottom: 8px; background-color: var(--secondary-background-color); color: var(--text-color); }
.chat-user { font-weight: 600; color: var(--primary-color); font-size: 13px; margin-right: 5px; }
.chat-sys { font-weight: 800; color: #ff4b4b; font-size: 13px; margin-right: 5px; }
.chat-time { font-size: 11px; opacity: 0.5; float: right; margin-left: 10px; }

/* 도발 박스 */
.taunt-box { background-color: #2c3e50; color: white; padding: 12px; border-radius: 8px; text-align: center; font-weight: bold; margin-bottom: 15px; box-shadow: 0 4px 6px rgba(0,0,0,0.1); }
.taunt-author { font-size: 12px; opacity: 0.8; margin-top: 4px; }

/* 해설 박스 */
.exp-box { background-color: #f0f2f6; border-left: 5px solid #007bff; padding: 15px; border-radius: 5px; margin-top: 10px; color: #1f2d3d; font-size: 14px; }

/* 모바일/버튼 촘촘한 디자인 */
.stButton > button { padding: 0.3rem 0.5rem !important; min-height: 2.2rem !important; border-radius: 6px !important; font-size: 14px !important; }
[data-testid="column"] { padding: 0 4px !important; }
div[data-testid="stVerticalBlock"] > div { padding-bottom: 0.2rem !important; }
@media (max-width: 768px) { 
    [data-testid="stTabs"] [data-testid="column"] { flex: 1 1 calc(50% - 8px) !important; min-width: calc(45%) !important; } 
}
</style>
""", unsafe_allow_html=True)

# --- ⚙️ 초기 설정 및 세션 관리 ---
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

season_start = app_settings.get('season_start', '2000-01-01 00:00:00')
v_opts = ["퀴즈 선택", "우정파괴창", "구역별 최강자"]
saved_view = app_settings.get('default_view', "퀴즈 선택")
def_view_idx = v_opts.index(saved_view) if saved_view in v_opts else 0

# --- 📂 사이드바 (출제 위원실) ---
with st.sidebar:
    st.caption("📱 친구 초대용 QR코드")
    st.image(generate_qr_code(APP_URL), width=120)
    st.divider()
    st.subheader("출제 위원실 (관리자)")
    pw = st.text_input("비밀번호", type="password", label_visibility="collapsed")
    if pw == ADMIN_PASSWORD:
        st.success("인증 완료")
        if st.button("🔥 새 시즌 시작 (랭킹 초기화)", use_container_width=True, type="primary"):
            save_setting("season_start", get_kst_time())
            save_chat("💻 시스템", "🚨 새로운 시즌이 시작되었습니다! 모든 랭킹이 초기화됩니다.")
            st.rerun()
        st.divider()
        all_q = get_all_quizzes()
        custom_cats = [c.strip() for c in app_settings.get("custom_categories", "").split(",") if c.strip()]
        all_cats = list(dict.fromkeys(custom_cats + [q.get('Category', '미분류') for q in all_q]))
        
        st.caption("⚙️ 앱 기본 설정")
        cur_def = app_settings.get('default_category', all_cats[0] if all_cats else "미분류")
        def_cat = st.selectbox("처음 열릴 카테고리", all_cats, index=all_cats.index(cur_def) if cur_def in all_cats else 0)
        if def_cat != cur_def: save_setting("default_category", def_cat); st.rerun()
        
        def_view = st.selectbox("기본 시작 화면", v_opts, index=def_view_idx)
        if def_view != saved_view: save_setting("default_view", def_view); st.rerun()

        st.divider()
        with st.expander("🆕 새 퀴즈 배포"):
            nc = st.selectbox("소속 카테고리 선택", all_cats); nt = st.text_input("퀴즈 제목"); nx = st.text_area("AI 텍스트 붙여넣기", height=150)
            if st.button("배포", use_container_width=True):
                from database import get_worksheet
                ws = get_worksheet("Quizzes")
                if ws and nc and nt and nx: ws.append_row([nc, nt, nx, get_kst_time()]); get_all_quizzes.clear(); st.success("배포 성공!"); st.rerun()

        with st.expander("✏️ 퀴즈 수정/삭제"):
            if all_q:
                sel_tit = st.selectbox("대상 퀴즈", [q['Title'] for q in all_q])
                curr_q = next(q for q in all_q if q['Title'] == sel_tit)
                e_cat = st.selectbox("그룹 변경", all_cats, index=all_cats.index(curr_q['Category']) if curr_q['Category'] in all_cats else 0)
                e_tit = st.text_input("제목 변경", curr_q['Title'])
                if st.button("정보 수정"): update_quiz(sel_tit, e_cat, e_tit); st.rerun()
                if st.button("퀴즈 삭제"): delete_quiz(sel_tit); st.rerun()
        
        st.info("🪄 AI 출제 프롬프트 가이드")
        st.code(QUIZ_GENERATION_PROMPT, language="text")

# --- 🎯 데이터 준비 (시즌 필터링) ---
all_res = get_all_results()
season_res = [r for r in all_res if r.get('Time', '') >= season_start]

# ==========================================
# 🏆 탭 1: 구역별 최강자 (전체 명예의 전당)
# ==========================================
if view_mode == "구역별 최강자":
    st.title("🏆 구역별 최강자")
    st.caption(f"이번 시즌 시작일: {season_start[:10]}")
    
    if not season_res:
        st.info("아직 이번 시즌의 전설이 기록되지 않았습니다.")
    else:
        df = pd.DataFrame(season_res)
        
        # 🥇 1. 우정 브레이커 (다관왕 랭킹)
        st.markdown("### 🥇 우정 브레이커")
        st.caption("가장 많은 종목에서 1위를 차지한 지배자")
        first_places = df.sort_values(by=['Score', 'Duration'], ascending=[False, True]).groupby('QuizTitle').first()
        breaker_counts = first_places['User'].value_counts()
        for idx, (user, count) in enumerate(breaker_counts.items()):
            st.write(f"{idx+1}위: **{user}** ({count}개 종목 지배 중)")
        
        st.divider()
        user_stats = df.groupby('User').agg(AvgScore=('Score', 'mean'), Attempts=('Score', 'count'))
        valid_u = user_stats[user_stats['Attempts'] >= 2]
        
        col1, col2 = st.columns(2)
        with col1:
            st.markdown("### 🎯 고인물")
            st.caption("최고 평균 정답률 (2회 이상)")
            if not valid_u.empty:
                masters = valid_u.sort_values('AvgScore', ascending=False).head(3)
                for i, (u, r) in enumerate(masters.iterrows()): st.write(f"{i+1}위: **{u}** ({r['AvgScore']:.1f}점)")
        with col2:
            st.markdown("### 💀 동네북")
            st.caption("최저 평균 정답률 (2회 이상)")
            if not valid_u.empty:
                noobs = valid_u.sort_values('AvgScore', ascending=True).head(3)
                for i, (u, r) in enumerate(noobs.iterrows()): st.write(f"{i+1}위: **{u}** ({r['AvgScore']:.1f}점)")

# ==========================================
# 💬 탭 2: 우정파괴창 (커뮤니티/알림)
# ==========================================
elif view_mode == "우정파괴창":
    c1, c2 = st.columns([3, 1])
    c1.subheader("우정파괴창")
    if c2.button("새로고침"): get_chats.clear(); st.rerun()
    
    chat_box = st.container(height=400)
    for c in get_chats():
        t_str = str(c.get('Time', ''))[:16]
        user_style = "chat-sys" if c["User"] == "💻 시스템" else "chat-user"
        chat_box.markdown(f'<div class="chat-msg"><span class="{user_style}">{c["User"]}:</span>{c["Message"]}<span class="chat-time">{t_str}</span></div>', unsafe_allow_html=True)
    
    with st.form("chat_f", clear_on_submit=True):
        m = st.text_input("메시지 입력", label_visibility="collapsed")
        if st.form_submit_button("전송", use_container_width=True) and m:
            save_chat(st.session_state.player_name, m); st.rerun()

# ==========================================
# 🎯 탭 3: 퀴즈 선택 및 종목별 지배자 확인
# ==========================================
else:
    quizzes = get_all_quizzes()
    all_cats = list(dict.fromkeys([q.get('Category','미분류') for q in quizzes]))
    tabs = st.tabs(all_cats)
    
    for i, cat in enumerate(all_cats):
        with tabs[i]:
            # 📌 [요청 반영] 퀴즈 제목(Title) 이름순 정렬
            cat_qs = sorted([q for q in quizzes if q.get('Category') == cat], key=lambda x: x['Title'])
            cols = st.columns(2)
            for j, q in enumerate(cat_qs):
                if cols[j%2].button(q['Title'], use_container_width=True, key=f"q_{i}_{j}"):
                    st.session_state.selected_quiz = q['Title']
                    st.session_state.quiz_finished = False
                    st.session_state.user_answers = {}
                    st.session_state.start_time = None
                    st.rerun()

    # 📌 퀴즈 선택 시 나타나는 개별 랭킹 화면 (지배자들)
    if st.session_state.selected_quiz:
        st.divider()
        st.subheader(f"📍 {st.session_state.selected_quiz}")
        q_item = next(q for q in quizzes if q['Title'] == st.session_state.selected_quiz)
        q_res = [r for r in season_res if r.get('QuizTitle') == q_item['Title']]
        
        # 👑 [종목별 지배자 순위판]
        with st.expander("🥇 이 구역의 지배자들 (현재 종목 순위)", expanded=True):
            if q_res:
                s_df = pd.DataFrame(q_res).sort_values(by=['Score', 'Duration'], ascending=[False, True]).reset_index(drop=True)
                s_df.index += 1
                st.table(s_df[['User', 'Score', 'Duration']].rename(columns={'User':'수험번호', 'Score':'점수', 'Duration':'시간(초)'}))
                
                # 도발 메시지 노출
                taunt = app_settings.get(f"taunt_{q_item['Title']}", "")
                if taunt:
                    st.markdown(f'<div class="taunt-box">"{taunt}"<div class="taunt-author">- 현재 1등 {s_df.iloc[0]["수험번호"]} -</div></div>', unsafe_allow_html=True)
                
                # 1등이면 도발 작성 권한 부여
                if s_df.iloc[0]['수험번호'] == st.session_state.player_name:
                    with st.container():
                        new_t = st.text_input("지배자의 한마디(도발)", value=taunt, placeholder="도발 메시지를 남기세요")
                        if st.button("도발 저장"):
                            save_setting(f"taunt_{q_item['Title']}", new_t); st.rerun()
            else:
                st.info("아직 도전자가 없습니다. 첫 번째 지배자가 되어보세요!")

        # 시험 시작 전/후 로직
        if st.session_state.start_time is None and not st.session_state.quiz_finished:
            if st.button("🚀 시험 시작하기", use_container_width=True, type="primary"):
                st.session_state.start_time = time.time(); st.rerun()
        
        elif not st.session_state.quiz_finished:
            parsed = robust_parse(q_item['Content'])
            for idx, it in enumerate(parsed):
                st.markdown(f'<p class="question-header">Q{idx+1}.</p>', unsafe_allow_html=True)
                if "<지문>" in it['q']:
                    p = it['q'].split("<지문>")
                    st.markdown(p[0]); st.markdown("\n".join([f"> {l}" for l in p[1].split("</지문>")[0].strip().split('\n')]))
                else: st.markdown(it['q'])
                
                is_short = it['o'] == ["주관식"]
                if is_short: ans = st.text_input(f"답 입력_{idx}", key=f"in_{idx}")
                else: ans = st.radio(f"보기 선택_{idx}", it['o'], index=None, key=f"in_{idx}", label_visibility="collapsed")
                
                if ans:
                    st.session_state.user_answers[f"ans_{idx}"] = ans
                    if "실시간" in app_settings.get('feedback_mode','실시간'):
                        c_ans = str(it['a']) if is_short else it['o'][it['a']]
                        is_c = (ans.replace(" ","").lower() == c_ans.replace(" ","").lower()) if is_short else (ans == c_ans)
                        if is_c: st.success("정답입니다!")
                        else:
                            st.error(f"오답! (정답: {c_ans})")
                            st.markdown(f'<div class="exp-box"><b>📝 해설:</b><br>{it["e"]}</div>', unsafe_allow_html=True)

            if st.button("🏁 최종 제출", use_container_width=True):
                wrongs = []
                for k, it in enumerate(parsed):
                    u = st.session_state.user_answers.get(f"ans_{k}")
                    c = str(it['a']) if it['o'] == ["주관식"] else it['o'][it['a']]
                    is_c = (u and u.replace(" ","").lower() == c.replace(" ","").lower()) if it['o'] == ["주관식"] else (u == c)
                    if not is_c: wrongs.append(it['k'])
                
                score = ((len(parsed)-len(wrongs))/len(parsed))*100
                duration = time.time()-st.session_state.start_time
                save_result(q_item['Title'], st.session_state.player_name, score, duration, wrongs)
                
                # 시스템 알림 (만점/탈환)
                if score == 100: save_chat("💻 시스템", f"🎉 [{st.session_state.player_name}]님이 '{q_item['Title']}'에서 만점을 달성했습니다!")
                if not q_res or score > max([r['Score'] for r in q_res]):
                    save_chat("💻 시스템", f"🚨 [{st.session_state.player_name}]님이 '{q_item['Title']}'의 새로운 지배자가 되었습니다!")
                
                st.session_state.quiz_finished = True; st.session_state.last_score = score; st.rerun()

        if st.session_state.quiz_finished:
            st.success(f"🎊 시험 종료! 최종 점수: {int(st.session_state.last_score)}점")
            if st.button("목록으로 돌아가기", use_container_width=True):
                st.session_state.selected_quiz = ""; st.rerun()