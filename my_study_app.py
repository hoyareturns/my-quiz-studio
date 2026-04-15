import streamlit as st
import re
import time
import pandas as pd
import gspread
import json
import qrcode
from io import BytesIO
from collections import Counter

# --- 0. 페이지 설정 및 디자인 패치 ---
st.set_page_config(page_title="우정 파괴소", page_icon="🧪", layout="centered")

st.markdown("""
<style>
/* 📖 국어 지문 및 보기 상자 스타일 */
.passage-container {
    background-color: #fdfdfd;
    border: 1px solid #e1e4e8;
    border-left: 5px solid #4A90E2;
    padding: 20px;
    border-radius: 8px;
    font-size: 15px;
    line-height: 1.8;
    color: #2c3e50;
    margin-bottom: 15px;
    white-space: pre-wrap; 
}
/* 문제 번호 헤더 */
.question-header {
    font-size: 18px;
    font-weight: 800;
    color: #ff4b4b;
    margin-top: 30px;
}
/* 모바일 버튼 2열 레이아웃 강제 */
@media (max-width: 768px) {
    [data-testid="stTabs"] [data-testid="column"] {
        flex: 1 1 calc(50% - 10px) !important;
        min-width: calc(45%) !important;
    }
}
</style>
""", unsafe_allow_html=True)

# --- 1. 구글 시트 연동 (캐시 적용) ---
@st.cache_resource
def get_gspread_client():
    credentials = json.loads(st.secrets["GCP_JSON"], strict=False)
    gc = gspread.service_account_from_dict(credentials)
    return gc.open_by_key(st.secrets["SHEET_ID"])

def get_worksheet(sheet_name, columns):
    try:
        sh = get_gspread_client()
        try:
            ws = sh.worksheet(sheet_name)
        except gspread.exceptions.WorksheetNotFound:
            ws = sh.add_worksheet(title=sheet_name, rows="100", cols=len(columns))
            ws.append_row(columns)
        return ws
    except Exception:
        return None

# --- 2. 데이터 처리 및 파싱 (지문 보존 강화) ---
@st.cache_data(ttl=15, show_spinner=False)
def get_all_quizzes():
    ws = get_worksheet("Quizzes", ["Category", "Title", "Content", "CreatedAt"])
    return ws.get_all_records() if ws else []

@st.cache_data(ttl=15, show_spinner=False)
def get_all_results():
    ws = get_worksheet("Results", ["QuizTitle", "User", "Score", "Duration", "Time"])
    return ws.get_all_records() if ws else []

def robust_parse(text):
    chunks = re.split(r"\[Q\d*\]", text)
    parsed = []
    for chunk in chunks:
        if not chunk.strip(): continue
        try:
            parts = re.split(r"(\[O\]|\[A\]|\[K\])", chunk)
            q_raw = parts[0].strip()
            o_raw, a_raw, k_raw = "", "1", "미분류"
            for i in range(len(parts)):
                tag = parts[i].strip()
                if tag == "[O]": o_raw = parts[i+1].strip()
                elif tag == "[A]": a_raw = parts[i+1].strip()
                elif tag == "[K]": k_raw = parts[i+1].strip()

            opts = re.findall(r'[①-⑤]\s*([^①-⑤\n\r]+)', o_raw)
            if not opts: opts = [o.strip() for o in o_raw.split(',') if o.strip()]
            
            ans_map = {'①':0, '②':1, '③':2, '④':3, '⑤':4, '1':0, '2':1, '3':2, '4':3, '5':4}
            ans_match = re.search(r'[①-⑤1-5]', a_raw)
            ans_idx = ans_map.get(ans_match.group(), 0) if ans_match else 0
            
            parsed.append({"q": q_raw, "o": opts, "a": ans_idx, "k": k_raw})
        except: continue
    return parsed

# --- 3. 세션 관리 및 접속자 상태 ---
@st.cache_resource
def get_active_users(): return set()
active_users = get_active_users()

if 'player_name' not in st.session_state: st.session_state.player_name = ""
if 'selected_quiz_title' not in st.session_state: st.session_state.selected_quiz_title = ""
if 'user_answers' not in st.session_state: st.session_state.user_answers = {}
if 'quiz_finished' not in st.session_state: st.session_state.quiz_finished = False
if 'start_time' not in st.session_state: st.session_state.start_time = None

@st.cache_resource
def get_admin_settings():
    return {"feedback_mode": "⚡ 실시간 팩폭 (즉시 확인)", "default_category": "", "allow_change": False}
admin_settings = get_admin_settings()

APP_URL = "https://hoya-quiz-studio.streamlit.app"
ADMIN_PASSWORD = "1234"

# --- 4. 사이드바 (핵심 업데이트 영역) ---
with st.sidebar:
    st.markdown(
        f"""
        <div style='display: flex; justify-content: space-between; align-items: center; padding-bottom: 10px;'>
            <h3 style='margin: 0;'>관리자 설정</h3>
            <span style='font-size: 14px; color: #4CAF50;'>🟢 풀이중: {len(active_users)}명</span>
        </div>
        """, 
        unsafe_allow_html=True
    )
    
    pw_input = st.text_input("비밀번호", type="password", placeholder="Password", label_visibility="collapsed")
    
    if pw_input == ADMIN_PASSWORD:
        st.success("인증됨")
        
        # 📊 취약 주제 분석
        results = get_all_results()
        weak_points = "데이터 없음"
        ws_wrong = get_worksheet("WrongAnswers", ["User", "Keyword", "Time"])
        if ws_wrong:
            wrong_data = ws_wrong.get_all_records()
            if wrong_data:
                counts = Counter([d.get('Keyword', '') for d in wrong_data if d.get('Keyword', '')])
                weak_points = ", ".join([f"{k}({v}회)" for k, v in counts.most_common(2)])
        st.caption(f"📊 취약: {weak_points}")
        
        # 📌 [복구 및 업데이트] 국어 지문 최적화 프롬프트
        st.info("🪄 **AI 출제 프롬프트 (지문 포함용)**")
        full_prompt = f"""국어 문제 10개를 출제해줘. 특히 취약한 주제({weak_points})를 참고해줘.
지문이 있는 경우 반드시 포함하되, 아래 형식을 엄격히 지켜줘.

[Q]
<지문>
여기에 소설이나 시 지문 입력 (줄바꿈 가능)
</지문>
문제 내용(발문) 입력

[O] ①보기1 ②보기2 ③보기3 ④보기4 ⑤보기5
[A] 정답 기호(예: ②)
[K] 핵심 키워드"""
        st.code(full_prompt, language="text")
        
        st.markdown("**⚙️ 퀴즈 룰 설정**")
        admin_settings['default_category'] = st.text_input("📌 처음 열릴 카테고리", value=admin_settings.get('default_category', ''), placeholder="예: 배관기초")
        
        mode_options = ["⚡ 실시간 팩폭 (즉시 확인)", "🏁 최후의 심판 (마지막에 한 번에)"]
        selected_mode = st.selectbox("채점 방식", mode_options, index=mode_options.index(admin_settings['feedback_mode']) if admin_settings['feedback_mode'] in mode_options else 0, label_visibility="collapsed")
        admin_settings['feedback_mode'] = selected_mode
        admin_settings['allow_change'] = (selected_mode != mode_options[0])
        st.caption(f"{'🔒 답안 수정 불가' if not admin_settings['allow_change'] else '🔓 답안 수정 자유'}")
        
        with st.expander("🆕 새 퀴즈 만들기", expanded=False):
            new_category = st.text_input("카테고리")
            new_title = st.text_input("퀴즈 제목")
            admin_text = st.text_area("결과물 붙여넣기", height=120)
            if st.button("🚀 신규 배포", use_container_width=True):
                if new_category and new_title and admin_text:
                    ws = get_worksheet("Quizzes", ["Category", "Title", "Content", "CreatedAt"])
                    ws.append_row([new_category, new_title, admin_text, time.strftime('%Y-%m-%d %H:%M:%S')])
                    get_all_quizzes.clear()
                    st.success("완료!"); st.rerun()

        with st.expander("🗑️ 퀴즈 삭제", expanded=False):
            all_quizzes = get_all_quizzes()
            for idx, q in enumerate(all_quizzes):
                col1, col2 = st.columns([3, 1])
                col1.caption(q['Title'])
                if col2.button("X", key=f"del_btn_{idx}"):
                    ws = get_worksheet("Quizzes", ["Category", "Title", "Content", "CreatedAt"])
                    cell = ws.find(q['Title'])
                    if cell: ws.delete_rows(cell.row)
                    get_all_quizzes.clear(); st.rerun()
    
    st.divider()
    qr = qrcode.QRCode(version=1, box_size=3, border=2)
    qr.add_data(APP_URL); qr.make(fit=True)
    buf = BytesIO(); qr.make_image(fill_color="black", back_color="white").save(buf)
    st.image(buf.getvalue(), width=120)

# --- 5. 메인 영역 ---
st.title("🧪 우정 파괴소")
st.session_state.player_name = st.text_input("👤 참가자 이름", value=st.session_state.player_name, placeholder="이름을 입력하세요")
st.divider()

quiz_list = get_all_quizzes()
if quiz_list:
    cats = list(dict.fromkeys([q['Category'] or '미분류' for q in quiz_list]))
    pref = admin_settings.get('default_category', '').strip()
    if pref in cats: cats.remove(pref); cats.insert(0, pref)
    
    tabs = st.tabs(cats)
    for i, cat in enumerate(cats):
        with tabs[i]:
            cat_qs = [q for q in quiz_list if (q['Category'] or '미분류') == cat]
            cols = st.columns(2)
            for j, q in enumerate(cat_qs):
                if cols[j % 2].button(q['Title'], key=f"q_{cat}_{j}", use_container_width=True):
                    st.session_state.selected_quiz_title = q['Title']
                    st.session_state.quiz_finished = False; st.session_state.start_time = None
                    st.session_state.user_answers = {}; st.rerun()

    if st.session_state.selected_quiz_title:
        q_data = next(q for q in quiz_list if q['Title'] == st.session_state.selected_quiz_title)
        quiz_content = robust_parse(q_data['Content'])
        
        if st.session_state.start_time is None and not st.session_state.quiz_finished:
            if st.button(f"🚀 {st.session_state.selected_quiz_title} 시작!", use_container_width=True):
                st.session_state.start_time = time.time(); active_users.add(st.session_state.player_name); st.rerun()
        
        elif not st.session_state.quiz_finished:
            st.markdown(f"## 📖 {st.session_state.selected_quiz_title}")
            
            for idx, item in enumerate(quiz_content):
                st.markdown(f'<p class="question-header">문제 {idx+1}</p>', unsafe_allow_html=True)
                
                # 📌 지문 인식 및 박스 처리 로직
                display_q = item['q']
                if "<지문>" in display_q and "</지문>" in display_q:
                    display_q = display_q.replace("<지문>", '<div class="passage-container">').replace("</지문>", '</div>')
                    st.markdown(display_q, unsafe_allow_html=True)
                else:
                    st.markdown(f'<div class="passage-container">{display_q}</div>', unsafe_allow_html=True)
                
                is_ans = f"ans_{idx}" in st.session_state.user_answers
                ans = st.radio(f"보기_{idx}", item['o'], index=None, key=f"r_{idx}", disabled=is_ans and not admin_settings['allow_change'], label_visibility="collapsed")
                
                if ans:
                    st.session_state.user_answers[f"ans_{idx}"] = ans
                    if admin_settings['feedback_mode'] == "⚡ 실시간 팩폭 (즉시 확인)":
                        if ans == item['o'][item['a']]: st.success("⭕ 정답!")
                        else: st.error(f"❌ 오답! (정답: {item['o'][item['a']]})")
                st.divider()

            if st.button("🏁 최종 제출하기", use_container_width=True):
                if len(st.session_state.user_answers) >= len(quiz_content):
                    ws_res = get_worksheet("Results", ["QuizTitle", "User", "Score", "Duration", "Time"])
                    if ws_res:
                        correct_count = sum(1 for i, q in enumerate(quiz_content) if st.session_state.user_answers.get(f"ans_{i}") == q['o'][q['a']])
                        score = (correct_count / len(quiz_content)) * 100
                        duration = time.time() - st.session_state.start_time
                        ws_res.append_row([st.session_state.selected_quiz_title, st.session_state.player_name, score, round(duration, 2), time.strftime('%Y-%m-%d %H:%M:%S')])
                    
                        # 오답 키워드 저장
                        ws_wrong = get_worksheet("WrongAnswers", ["User", "Keyword", "Time"])
                        if ws_wrong:
                            for i, q in enumerate(quiz_content):
                                if st.session_state.user_answers.get(f"ans_{i}") != q['o'][q['a']]:
                                    ws_wrong.append_row([st.session_state.player_name, q['k'], time.strftime('%Y-%m-%d %H:%M:%S')])
                    
                    st.session_state.quiz_finished = True
                    active_users.discard(st.session_state.player_name)
                    st.rerun()
                else: st.warning("모든 문제를 풀어주세요!")

        if st.session_state.quiz_finished:
            st.balloons(); st.success("🎉 수고하셨습니다!"); st.button("다른 퀴즈 하기", on_click=lambda: st.rerun())
