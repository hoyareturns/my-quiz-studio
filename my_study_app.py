import streamlit as st
import pandas as pd
import time
from datetime import datetime, timedelta
import qrcode
import re
from io import BytesIO
from database import (get_all_quizzes, get_all_results, get_settings, 
                      get_chats, save_chat, save_result)
from utils import robust_parse
from prompts import VIEW_OPTIONS, FEEDBACK_MODES
# 📌 분리된 관리자 메뉴 로드
from admin import show_admin_sidebar

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

# --- 🎨 디자인 및 페이지 설정 ---
st.set_page_config(page_title="우정 파괴소", layout="centered")
st.markdown("""
<style>
[data-testid="stMain"] blockquote { background-color: var(--secondary-background-color) !important; border-left: 4px solid var(--primary-color) !important; padding: 16px !important; border-radius: 6px !important; color: var(--text-color) !important; font-style: normal !important; }
.question-header { font-size: 16px; font-weight: 700; color: #ff4b4b; margin-top: 24px; margin-bottom: 8px; }
.chat-msg { padding: 10px; border-radius: 8px; margin-bottom: 8px; background-color: var(--secondary-background-color); color: var(--text-color); }
.chat-user { font-weight: 600; color: var(--primary-color); font-size: 13px; margin-right: 5px; }
.chat-sys { font-weight: 800; color: #ff4b4b; font-size: 13px; margin-right: 5px; }
.chat-time { font-size: 11px; opacity: 0.5; float: right; margin-left: 10px; }
.taunt-box { background-color: #2c3e50; color: white; padding: 12px; border-radius: 8px; text-align: center; font-weight: bold; margin-bottom: 15px; }
.taunt-author { font-size: 12px; opacity: 0.8; margin-top: 4px; }
.stButton > button { padding: 0.3rem 0.5rem !important; min-height: 2.2rem !important; border-radius: 6px !important; font-size: 14px !important; }
.exp-box { background-color: #f0f2f6; border-left: 5px solid #007bff; padding: 12px; border-radius: 5px; margin-top: 8px; color: #1f2d3d; font-size: 14px; }
[data-testid="column"] { padding: 0 4px !important; }
@media (max-width: 768px) { [data-testid="stTabs"] [data-testid="column"] { flex: 1 1 calc(50% - 8px) !important; } }
</style>
""", unsafe_allow_html=True)

# --- ⚙️ 설정 로드 ---
APP_URL = "https://hoya-quiz-studio.streamlit.app"
app_settings = get_settings()

if 'player_name' not in st.session_state or not st.session_state.player_name:
    results = get_all_results()
    nums = [int(re.match(r"우정파괴자(\d+)", str(r.get('User',''))).group(1)) for r in results if re.match(r"우정파괴자(\d+)", str(r.get('User','')))]
    st.session_state.player_name = f"우정파괴자{max(nums + [0]) + 1}"

for k in ['selected_quiz', 'user_answers', 'quiz_finished', 'start_time', 'review_data']:
    if k not in st.session_state: st.session_state[k] = "" if k == 'selected_quiz' else {} if k == 'user_answers' else False if k == 'quiz_finished' else None

# --- 📂 사이드바 통합 ---
with st.sidebar:
    st.caption("📱 친구 초대용 QR코드")
    st.image(generate_qr_code(APP_URL), width=120)
    st.divider()
    # 📌 admin.py의 함수 호출
    show_admin_sidebar(app_settings, get_kst_time)

# --- 🎯 메인 로직 ---
st.title("우정 파괴소")
st.session_state.player_name = st.text_input("수험번호", value=st.session_state.player_name)
season_start = app_settings.get('season_start', '2000-01-01 00:00:00')
saved_view = app_settings.get('default_view', "퀴즈 선택")
def_view_idx = VIEW_OPTIONS.index(saved_view) if saved_view in VIEW_OPTIONS else 0
view_mode = st.radio("탭", VIEW_OPTIONS, horizontal=True, label_visibility="collapsed", index=def_view_idx)

all_res = get_all_results()
season_res = [r for r in all_res if r.get('Time', '') >= season_start]

if view_mode == "구역별 최강자":
    st.subheader("🏆 구역별 최강자")
    if not season_res: st.info("기록 없음")
    else:
        df = pd.DataFrame(season_res)
        st.markdown("### 🥇 우정 브레이커")
        top1 = df.sort_values(by=['Score', 'Duration'], ascending=[False, True]).groupby('QuizTitle').first()
        for idx, (u, c) in enumerate(top1['User'].value_counts().items()): st.write(f"{idx+1}위: **{u}** ({c}회 1등)")

elif view_mode == "우정파괴창":
    c1, c2 = st.columns([3, 1])
    if c2.button("새로고침"): get_chats.clear(); st.rerun()
    chat_box = st.container(height=400)
    for c in get_chats():
        t_str = str(c.get('Time', ''))[:16]
        cls = "chat-sys" if c["User"] == "💻 시스템" else "chat-user"
        chat_box.markdown(f'<div class="chat-msg"><span class="{cls}">{c["User"]}:</span>{c["Message"]}<span class="chat-time">{t_str}</span></div>', unsafe_allow_html=True)
    with st.form("c_f", clear_on_submit=True):
        m = st.text_input("입력", label_visibility="collapsed")
        if st.form_submit_button("전송") and m: save_chat(st.session_state.player_name, m); st.rerun()

else:
    quizzes = get_all_quizzes()
    all_cats = list(dict.fromkeys([q.get('Category','미분류') for q in quizzes]))
    custom_cats = [c.strip() for c in app_settings.get("custom_categories", "").split(",") if c.strip()]
    all_display_cats = list(dict.fromkeys(custom_cats + all_cats))
    
    tabs = st.tabs(all_display_cats)
    for i, cat in enumerate(all_display_cats):
        with tabs[i]:
            cat_qs = sorted([q for q in quizzes if q.get('Category') == cat], key=lambda x: x['Title'])
            if not cat_qs: st.caption("등록된 퀴즈 없음")
            else:
                cols = st.columns(2)
                for j, q in enumerate(cat_qs):
                    if cols[j%2].button(q['Title'], use_container_width=True, key=f"q_{i}_{j}"):
                        st.session_state.selected_quiz = q['Title']; st.session_state.quiz_finished = False; st.session_state.user_answers = {}; st.session_state.start_time = None; st.rerun()

    if st.session_state.selected_quiz:
        st.divider()
        q_item = next(q for q in quizzes if q['Title'] == st.session_state.selected_quiz)
        q_res = [r for r in season_res if r.get('QuizTitle') == q_item['Title']]
        
        with st.expander("🥇 이 구역의 지배자들", expanded=True):
            if q_res:
                s_df = pd.DataFrame(q_res).sort_values(by=['Score', 'Duration'], ascending=[False, True]).reset_index(drop=True)
                s_df.index += 1
                st.table(s_df[['User', 'Score', 'Duration']].rename(columns={'User':'수험번호', 'Score':'점수', 'Duration':'시간'}))
                taunt = app_settings.get(f"taunt_{q_item['Title']}", "")
                if taunt: st.markdown(f'<div class="taunt-box">"{taunt}"<div class="taunt-author">- 1등 {s_df.iloc[0]["수험번호"]} -</div></div>', unsafe_allow_html=True)
                if s_df.iloc[0]['수험번호'] == st.session_state.player_name:
                    new_t = st.text_input("지배자의 한마디(도발)", value=taunt)
                    if st.button("도발 저장"): save_setting(f"taunt_{q_item['Title']}", new_t); st.rerun()

        if st.session_state.start_time is None and not st.session_state.quiz_finished:
            if st.button("🚀 시험 시작", use_container_width=True, type="primary"): st.session_state.start_time = time.time(); st.rerun()
        elif not st.session_state.quiz_finished:
            parsed = robust_parse(q_item['Content'])
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
                if is_short: ans = st.text_input(f"답_{idx}", key=f"in_{idx}")
                else: ans = st.radio(f"보기_{idx}", it['o'], index=None, key=f"in_{idx}", label_visibility="collapsed")
                
                if ans:
                    st.session_state.user_answers[f"ans_{idx}"] = ans
                    if "실시간" in app_settings.get('feedback_mode', ''):
                        c_ans = str(it['a']) if is_short else it['o'][it['a']]
                        is_c = (ans.replace(" ","").lower() == c_ans.replace(" ","").lower()) if is_short else (ans == c_ans)
                        if is_c: st.success("정답!")
                        else: st.error(f"오답! (정답: {c_ans})"); st.markdown(f'<div class="exp-box">{it["e"]}</div>', unsafe_allow_html=True)

            if st.button("🏁 최종 제출", use_container_width=True):
                wrongs, revs = [], []
                for k, it in enumerate(parsed):
                    u = st.session_state.user_answers.get(f"ans_{k}")
                    c = str(it['a']) if it['o'] == ["주관식"] else it['o'][it['a']]
                    is_c = (u and u.replace(" ","").lower() == c.replace(" ","").lower()) if it['o'] == ["주관식"] else (u == c)
                    if not is_c: wrongs.append(it['k'])
                    revs.append({"is_c":is_c, "u":u, "c":c, "e":it['e']})
                
                score = ((len(parsed)-len(wrongs))/len(parsed))*100
                save_result(q_item['Title'], st.session_state.player_name, score, time.time()-st.session_state.start_time, wrongs)
                if score == 100: save_chat("💻 시스템", f"🎉 [{st.session_state.player_name}]님이 '{q_item['Title']}' 만점!")
                st.session_state.quiz_finished = True; st.session_state.last_score = score; st.session_state.review_data = revs; st.rerun()

        if st.session_state.quiz_finished:
            if "최후" in app_settings.get('feedback_mode', ''):
                with st.expander("📝 채점 결과 및 해설", expanded=True):
                    for i, r in enumerate(st.session_state.review_data):
                        st.markdown(f"**Q{i+1}. {'⭕' if r['is_c'] else '❌'}**")
                        if not r['is_c']: st.write(f"내 답: {r['u']} / 정답: **{r['c']}**"); st.markdown(f'<div class="exp-box">{r["e"]}</div>', unsafe_allow_html=True)
            st.success(f"🎊 점수: {int(st.session_state.last_score)}점")
            if st.button("목록으로", use_container_width=True): st.session_state.selected_quiz = ""; st.rerun()