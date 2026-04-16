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
.chat-user { font-weight: bold; color: var(--primary-color); font-size: 14px; margin-right: 5px; }
.chat-time { font-size: 11px; opacity: 0.6; float: right; margin-left: 10px; }
@media (max-width: 768px) { [data-testid="stTabs"] [data-testid="column"] { flex: 1 1 45% !important; } }
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

# --- 2. 사이드바 (관리자) ---
with st.sidebar:
    admin_btn_name = app_settings.get("admin_btn_name", "⚙️ 관리자 설정")
    st.subheader(admin_btn_name)
    
    pw_input = st.text_input("비밀번호", type="password", placeholder="Password", label_visibility="collapsed")
    
    if pw_input == ADMIN_PASSWORD:
        st.success("인증 완료")
        
        st.info("🪄 **AI 출제 프롬프트 (복사해서 바로 사용)**")
        prompt_text = """아래 형식에 맞춰 [ ] 10문제를 출제해.
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
[K] 키워드"""
        st.code(prompt_text, language="text")
        
        wp_data = get_weak_points()
        st.caption(f"💡 전체 취약 주제 참고: {wp_data}")
        st.divider()
        
        all_q = get_all_quizzes()
        custom_cats = [c.strip() for c in app_settings.get("custom_categories", "").split(",") if c.strip()]
        all_cats = list(dict.fromkeys(custom_cats + [q.get('Category', '미분류') for q in all_q]))
        if not all_cats: all_cats = ["미분류"]

        new_admin_name = st.text_input("관리자 메뉴 이름 변경", value=admin_btn_name)
        if new_admin_name != admin_btn_name: save_setting("admin_btn_name", new_admin_name); st.rerun()

        current_def = app_settings.get('default_category', all_cats[0])
        def_cat = st.selectbox("📌 처음 열릴 카테고리 설정", all_cats, index=all_cats.index(current_def) if current_def in all_cats else 0)
        if def_cat != current_def: save_setting("default_category", def_cat); st.rerun()
        
        v_opts = ["🎯 퀴즈 선택", "💬 우정파괴창"]
        def_view = st.selectbox("기본 시작 화면", v_opts, index=v_opts.index(app_settings.get('default_view', v_opts[0])))
        if def_view != app_settings.get('default_view'): save_setting("default_view", def_view); st.rerun()

        with st.expander("➕ 그룹(카테고리) 추가"):
            new_g = st.text_input("새 그룹 이름")
            if st.button("추가") and new_g:
                save_setting("custom_categories", app_settings.get("custom_categories","") + f",{new_g}"); st.rerun()

        with st.expander("🆕 새 퀴즈 배포"):
            nc = st.selectbox("소속 카테고리 선택", all_cats)
            nt = st.text_input("퀴즈 제목")
            nx = st.text_area("AI 결과물 붙여넣기", height=150)
            if st.button("🚀 배포", use_container_width=True):
                if nc and nt and nx:
                    from database import get_worksheet
                    ws_q = get_worksheet("Quizzes")
                    if ws_q: ws_q.append_row([nc, nt, nx, get_kst_time()]); get_all_quizzes.clear(); st.success("배포 성공!"); st.rerun()

        with st.expander("✏️ 퀴즈 수정/삭제"):
            if all_q:
                sel_q_tit = st.selectbox("관리할 퀴즈", [q['Title'] for q in all_q])
                curr_q = next(q for q in all_q if q['Title'] == sel_q_tit)
                e_cat = st.selectbox("그룹 변경", all_cats, index=all_cats.index(curr_q['Category']) if curr_q['Category'] in all_cats else 0)
                e_tit = st.text_input("제목 변경", curr_q['Title'])
                if st.button("💾 정보 수정"): update_quiz(sel_q_tit, e_cat, e_tit); st.rerun()
                if st.button("🗑️ 퀴즈 삭제"): delete_quiz(sel_q_tit); st.rerun()

    qr = qrcode.QRCode(box_size=3); qr.add_data(APP_URL); buf = BytesIO()
    qr.make_image().save(buf); st.image(buf.getvalue(), width=100)

# --- 3. 메인 화면 ---
st.title("🧪 우정 파괴소")
st.session_state.player_name = st.text_input("👤 참가자 이름", value=st.session_state.player_name)
view_mode = st.radio("화면 전환", ["🎯 퀴즈 선택", "💬 우정파괴창"], horizontal=True, label_visibility="collapsed", index=["🎯 퀴즈 선택", "💬 우정파괴창"].index(app_settings.get('default_view', "🎯 퀴즈 선택")))

if view_mode == "💬 우정파괴창":
    c1, c2 = st.columns([3, 1])
    c1.subheader("💬 우정파괴창")
    if c2.button("🔄 새로고침", use_container_width=True):
        get_chats.clear()
        st.rerun()
        
    chat_container = st.container(height=400)
    for chat in get_chats():
        chat_time_str = str(chat.get('Time', ''))[:16] 
        # 📌 [UI 수정] 줄바꿈(<br>)을 삭제하고 콜론(:)을 붙여 한 줄로 출력되도록 변경
        chat_container.markdown(f'<div class="chat-msg"><span class="chat-user">{chat["User"]}:</span>{chat["Message"]}<span class="chat-time">{chat_time_str}</span></div>', unsafe_allow_html=True)
        
    with st.form("chat", clear_on_submit=True):
        m = st.text_input("메시지 입력", label_visibility="collapsed")
        if st.form_submit_button("전송", use_container_width=True) and m:
            save_chat(st.session_state.player_name, m); st.rerun()

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
        st.subheader(f"📖 {st.session_state.selected_quiz}")
        q_item = next(q for q in quiz_data if q['Title'] == st.session_state.selected_quiz)
        
        with st.expander("🏆 실시간 랭킹 확인", expanded=False):
            res = [r for r in get_all_results() if r.get('QuizTitle') == q_item['Title']]
            if res: st.dataframe(pd.DataFrame(res).sort_values(by=['Score','Duration'], ascending=[False,True]), use_container_width=True)
            
        if st.session_state.start_time is None and not st.session_state.quiz_finished:
            if st.button("🚀 퀴즈 시작하기!", use_container_width=True, type="primary"):
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
                f_mode = app_settings.get('feedback_mode','⚡ 실시간 팩폭 (즉시 확인)')
                
                is_short_answer = (it['o'] == ["주관식"])
                
                if is_short_answer:
                    ans = st.text_input(f"정답 입력_{idx}", key=f"r_{idx}", disabled=is_ans if f_mode.startswith("⚡") else False, placeholder="여기에 정답을 입력하세요")
                    correct_ans = str(it['a'])
                else:
                    ans = st.radio(f"보기_{idx}", it['o'], index=None, key=f"r_{idx}", disabled=is_ans if f_mode.startswith("⚡") else False, label_visibility="collapsed")
                    correct_ans = it['o'][it['a']]
                
                if ans:
                    st.session_state.user_answers[f"ans_{idx}"] = ans
                    if f_mode.startswith("⚡"):
                        if is_short_answer:
                            is_correct = (ans.replace(" ", "").lower() == correct_ans.replace(" ", "").lower())
                        else:
                            is_correct = (ans == correct_ans)
                            
                        if is_correct: st.success("⭕ 정답!")
                        else: st.error(f"❌ 오답! (정답: {correct_ans})")
            
            if st.button("🏁 답안 제출 (미응답 시 오답)", use_container_width=True):
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
                save_result(q_item['Title'], st.session_state.player_name, score, time.time()-st.session_state.start_time, wrongs)
                st.session_state.quiz_finished = True; st.session_state.last_score = score; st.session_state.review_data = revs; st.rerun()

        if st.session_state.quiz_finished:
            if app_settings.get('feedback_mode','').startswith("🏁"):
                with st.expander("📝 전체 채점 결과 보기", expanded=True):
                    for i, r in enumerate(st.session_state.review_data):
                        if r.get('is_u'):
                            st.markdown(f"**Q{i+1}.** ❌ 미응답"); st.write("⚠️ 정답 미제공")
                        else:
                            st.markdown(f"**Q{i+1}.** {'⭕ 정답' if r['is_c'] else '❌ 오답'}")
                            if not r['is_c']: st.write(f"내 답: {r['u']} / 정답: **{r['c']}**")
            st.success(f"🎉 종료! 최종 점수: {int(st.session_state.last_score)}점"); st.button("다른 퀴즈 하러 가기", on_click=lambda: st.rerun(), use_container_width=True)