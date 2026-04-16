import streamlit as st
import pandas as pd
import time
import qrcode
import re
from io import BytesIO
# 분리된 파일에서 함수 불러오기
from database import (get_all_quizzes, get_all_results, get_settings, save_setting, 
                      get_chats, save_chat, get_weak_points, update_quiz, delete_quiz, 
                      save_result, get_worksheet)
from utils import robust_parse

# --- 디자인 설정 ---
st.set_page_config(page_title="우정 파괴소", page_icon="🧪", layout="centered")
st.markdown("""
<style>
[data-testid="stMain"] blockquote {
    background-color: var(--secondary-background-color) !important; 
    border: 1px solid var(--border-color) !important;
    border-left: 5px solid var(--primary-color) !important; 
    padding: 20px !important; border-radius: 8px !important; 
    color: var(--text-color) !important; font-style: normal !important;
}
.question-header { font-size: 18px; font-weight: 800; color: #ff4b4b; margin-top: 30px; }
.chat-msg { padding: 10px; border-radius: 10px; margin-bottom: 10px; background-color: var(--secondary-background-color); color: var(--text-color); }
.chat-user { font-weight: bold; color: var(--primary-color); font-size: 14px; }
.chat-time { font-size: 11px; opacity: 0.6; float: right; }
@media (max-width: 768px) { [data-testid="stTabs"] [data-testid="column"] { flex: 1 1 45% !important; } }
</style>
""", unsafe_allow_html=True)

# --- 초기 설정 및 세션 ---
APP_URL = "https://hoya-quiz-studio.streamlit.app"
ADMIN_PASSWORD = "1234"
app_settings = get_settings()

if 'player_name' not in st.session_state or not st.session_state.player_name:
    results = get_all_results()
    max_num = max([int(re.match(r"우정파괴자(\d+)", str(r.get('User',''))).group(1)) 
                   for r in results if re.match(r"우정파괴자(\d+)", str(r.get('User','')))] + [0])
    st.session_state.player_name = f"우정파괴자{max_num + 1}"

for k in ['selected_quiz', 'user_answers', 'quiz_finished', 'start_time', 'review_data']:
    if k not in st.session_state: st.session_state[k] = "" if k == 'selected_quiz' else {} if k == 'user_answers' else False if k == 'quiz_finished' else None

# --- 사이드바 (관리자) ---
with st.sidebar:
    st.subheader("⚙️ 관리자 설정")
    pw_input = st.text_input("비밀번호", type="password", placeholder="Password", label_visibility="collapsed")
    if pw_input == ADMIN_PASSWORD:
        st.success("인증 완료")
        wp = get_weak_points()
        st.info("🪄 AI 출제 프롬프트 가이드")
        st.code(f"과목 문제 10개 출제. 주제({wp}) 반영. 인사말 없이 [Q1]부터. 그림/표 금지.", language="text")
        
        all_q = get_all_quizzes()
        custom_cats = [c.strip() for c in app_settings.get("custom_categories", "").split(",") if c.strip()]
        all_cats = list(dict.fromkeys(custom_cats + [q.get('Category', '미분류') for q in all_q]))
        
        # 설정 변경
        def_cat = st.selectbox("📌 처음 카테고리", all_cats, index=all_cats.index(app_settings.get('default_category', all_cats[0])) if app_settings.get('default_category') in all_cats else 0)
        if def_cat != app_settings.get('default_category'): save_setting("default_category", def_cat); st.rerun()
        
        v_opts = ["🎯 퀴즈 선택", "💬 우정파괴창"]
        def_view = st.selectbox("기본 화면", v_opts, index=v_opts.index(app_settings.get('default_view', v_opts[0])))
        if def_view != app_settings.get('default_view'): save_setting("default_view", def_view); st.rerun()

        with st.expander("➕ 그룹 추가"):
            new_g = st.text_input("새 그룹")
            if st.button("추가") and new_g: save_setting("custom_categories", app_settings.get("custom_categories","") + f",{new_g}"); st.rerun()

        with st.expander("✏️ 퀴즈 수정/삭제"):
            if all_q:
                sel_q = st.selectbox("관리 퀴즈", [q['Title'] for q in all_q])
                curr_q = next(q for q in all_q if q['Title'] == sel_q)
                e_cat = st.text_input("그룹 변경", curr_q['Category'])
                e_tit = st.text_input("제목 변경", curr_q['Title'])
                if st.button("수정"): update_quiz(sel_q, e_cat, e_tit); st.rerun()
                if st.button("삭제"): delete_quiz(sel_q); st.rerun()

    qr = qrcode.QRCode(box_size=3); qr.add_data(APP_URL); buf = BytesIO()
    qr.make_image().save(buf); st.image(buf.getvalue(), width=100)

# --- 메인 화면 ---
st.title("🧪 우정 파괴소")
st.session_state.player_name = st.text_input("👤 참가자 이름", value=st.session_state.player_name)
view_mode = st.radio("화면", ["🎯 퀴즈 선택", "💬 우정파괴창"], horizontal=True, label_visibility="collapsed", index=["🎯 퀴즈 선택", "💬 우정파괴창"].index(app_settings.get('default_view', "🎯 퀴즈 선택")))

if view_mode == "💬 우정파괴창":
    st.subheader("💬 우정파괴창")
    for chat in get_chats():
        st.markdown(f'<div class="chat-msg"><span class="chat-user">{chat["User"]}</span> <span class="chat-time">{chat["Time"][11:16]}</span><br>{chat["Message"]}</div>', unsafe_allow_html=True)
    with st.form("chat", clear_on_submit=True):
        m = st.text_input("메시지", label_visibility="collapsed")
        if st.form_submit_button("전송") and m: save_chat(st.session_state.player_name, m); st.rerun()

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
            if not cat_qs: st.caption("퀴즈 없음")
            else:
                cols = st.columns(2)
                for j, q in enumerate(cat_qs):
                    if cols[j%2].button(q['Title'], use_container_width=True, key=f"q_{cat}_{j}"):
                        st.session_state.selected_quiz = q['Title']; st.session_state.quiz_finished = False; st.rerun()

    if st.session_state.selected_quiz:
        st.divider()
        st.subheader(f"📖 {st.session_state.selected_quiz}")
        q_item = next(q for q in quiz_data if q['Title'] == st.session_state.selected_quiz)
        with st.expander("🏆 실시간 랭킹"):
            res = [r for r in get_all_results() if r.get('QuizTitle') == q_item['Title']]
            if res: st.dataframe(pd.DataFrame(res).sort_values(by=['Score','Duration'], ascending=[False,True]))
        
        if st.session_state.start_time is None and not st.session_state.quiz_finished:
            if st.button("🚀 시작하기", use_container_width=True, type="primary"): st.session_state.start_time = time.time(); st.rerun()
        elif not st.session_state.quiz_finished:
            parsed = robust_parse(q_item['Content'])
            for idx, it in enumerate(parsed):
                st.markdown(f'<p class="question-header">Q{idx+1}.</p>', unsafe_allow_html=True)
                if "<지문>" in it['q']:
                    p = it['q'].split("<지문>")
                    st.markdown(p[0]); st.markdown("\n".join([f"> {l}" for l in p[1].split("</지문>")[0].strip().split('\n')]))
                    if len(p[1].split("</지문>")) > 1: st.markdown(p[1].split("</지문>")[1])
                else: st.markdown("\n".join([f"> {l}" for l in it['q'].strip().split('\n')]))
                ans = st.radio(f"보기_{idx}", it['o'], index=None, key=f"r_{idx}", label_visibility="collapsed")
                if ans:
                    st.session_state.user_answers[f"ans_{idx}"] = ans
                    if app_settings.get('feedback_mode','').startswith("⚡") :
                        if ans == it['o'][it['a']]: st.success("⭕ 정답!")
                        else: st.error(f"❌ 오답! (정답: {it['o'][it['a']]})")
            
            if st.button("🏁 제출"):
                wrongs, revs = [], []
                for k, it in enumerate(parsed):
                    u = st.session_state.user_answers.get(f"ans_{k}"); c = it['o'][it['a']]
                    if not u: wrongs.append(it['k']); revs.append({"q":it['q'], "is_u":True})
                    else:
                        is_c = (u == c)
                        if not is_c: wrongs.append(it['k'])
                        revs.append({"q":it['q'], "u":u, "c":c, "is_c":is_c, "is_u":False})
                score = ((len(parsed)-len(wrongs))/len(parsed))*100
                save_result(q_item['Title'], st.session_state.player_name, score, time.time()-st.session_state.start_time, wrongs)
                st.session_state.quiz_finished = True; st.session_state.last_score = score; st.session_state.review_data = revs; st.rerun()

        if st.session_state.quiz_finished:
            if app_settings.get('feedback_mode','').startswith("🏁"):
                with st.expander("📝 채점 결과"):
                    for i, r in enumerate(st.session_state.review_data):
                        st.markdown(f"**Q{i+1}.** {'❌ 미응답' if r['is_u'] else '⭕ 정답' if r['is_c'] else '❌ 오답'}")
            st.success(f"🎉 종료! 점수: {int(st.session_state.last_score)}"); st.button("다른 퀴즈", on_click=lambda: st.rerun())