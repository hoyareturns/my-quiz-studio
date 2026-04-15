import streamlit as st
import re
import time
import pandas as pd
import gspread
import json
import qrcode
from io import BytesIO
from collections import Counter

# --- 0. 페이지 설정 및 디자인 ---
st.set_page_config(page_title="우정 파괴소", page_icon="🧪", layout="centered")

st.markdown("""
<style>
/* 📖 지문 전용 상자 스타일 */
.passage-container {
    background-color: #f8f9fa;
    border: 1px solid #dee2e6;
    border-left: 5px solid #4A90E2;
    padding: 20px;
    border-radius: 8px;
    font-size: 15px;
    line-height: 1.8;
    color: #2c3e50;
    margin-bottom: 15px;
    white-space: pre-wrap; /* 줄바꿈 및 공백 보존 */
}
/* 문제 제목 스타일 */
.question-header {
    font-size: 18px;
    font-weight: 800;
    color: #ff4b4b;
    margin-top: 25px;
}
/* 모바일 2열 버튼 레이아웃 */
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
    except Exception as e:
        st.error(f"구글 시트 연결 오류: {e}")
        return None

# --- 2. 데이터 처리 및 정밀 파싱 ---
@st.cache_data(ttl=15, show_spinner=False)
def get_all_quizzes():
    ws = get_worksheet("Quizzes", ["Category", "Title", "Content", "CreatedAt"])
    return ws.get_all_records() if ws else []

def robust_parse(text):
    # [Q] 또는 [Q1] 단위 분리
    chunks = re.split(r"\[Q\d*\]", text)
    parsed = []
    for chunk in chunks:
        if not chunk.strip(): continue
        try:
            # [O], [A], [K] 기준으로 쪼개기
            parts = re.split(r"(\[O\]|\[A\]|\[K\])", chunk)
            q_raw = parts[0].strip()
            o_raw, a_raw, k_raw = "", "1", "미분류"
            for i in range(len(parts)):
                tag = parts[i].strip()
                if tag == "[O]": o_raw = parts[i+1].strip()
                elif tag == "[A]": a_raw = parts[i+1].strip()
                elif tag == "[K]": k_raw = parts[i+1].strip()

            # 보기 추출 (①~⑤)
            opts = re.findall(r'[①-⑤]\s*([^①-⑤\n\r]+)', o_raw)
            if not opts: opts = [o.strip() for o in o_raw.split(',') if o.strip()]
            
            # 정답 인덱스 변환
            ans_map = {'①':0, '②':1, '③':2, '④':3, '⑤':4, '1':0, '2':1, '3':2, '4':3, '5':4}
            ans_match = re.search(r'[①-⑤1-5]', a_raw)
            ans_idx = ans_map.get(ans_match.group(), 0) if ans_match else 0
            
            parsed.append({"q": q_raw, "o": opts, "a": ans_idx, "k": k_raw})
        except: continue
    return parsed

# --- 3. 공용 함수 및 세션 ---
@st.cache_data(ttl=15, show_spinner=False)
def get_all_results():
    ws = get_worksheet("Results", ["QuizTitle", "User", "Score", "Duration", "Time"])
    return ws.get_all_records() if ws else []

def save_result_to_gsheet(title, user, score, duration, wrong):
    ws = get_worksheet("Results", ["QuizTitle", "User", "Score", "Duration", "Time"])
    if ws: ws.append_row([title, user, score, round(duration, 2), time.strftime('%Y-%m-%d %H:%M:%S')])
    get_all_results.clear()

if 'player_name' not in st.session_state: st.session_state.player_name = ""
if 'selected_quiz_title' not in st.session_state: st.session_state.selected_quiz_title = ""
if 'user_answers' not in st.session_state: st.session_state.user_answers = {}
if 'quiz_finished' not in st.session_state: st.session_state.quiz_finished = False
if 'start_time' not in st.session_state: st.session_state.start_time = None

@st.cache_resource
def get_admin_settings():
    return {"mode": "⚡ 실시간 팩폭 (즉시 확인)", "cat": ""}
admin = get_admin_settings()

# --- 4. 사이드바 (관리자 설정) ---
with st.sidebar:
    st.header("🔑 Admin Settings")
    pw_input = st.text_input("관리자 암호", type="password")
    
    if pw_input == "1234":
        st.success("인증되었습니다.")
        
        # 📌 최적화된 프롬프트 예시창 복구
        st.markdown("**🪄 AI 출제 프롬프트 (복사해서 사용)**")
        new_prompt = """국어 문제 10개를 출제해줘. 지문이 있는 경우 반드시 포함하되, 아래 형식을 엄격히 지켜줘.

[Q]
<지문>
지문 내용 입력 (줄바꿈 포함 가능)
</지문>
발문(문제 내용) 입력

[O] ①보기1 ②보기2 ③보기3 ④보기4 ⑤보기5
[A] 정답 기호(예: ②)
[K] 핵심 키워드"""
        st.code(new_prompt, language="text")
        
        st.divider()
        admin['cat'] = st.text_input("📌 기본 카테고리", value=admin.get('cat', ''))
        modes = ["⚡ 실시간 팩폭 (즉시 확인)", "🏁 최후의 심판 (마지막에 한 번에)"]
        admin['mode'] = st.selectbox("채점 모드", modes, index=modes.index(admin['mode']))
        
        with st.expander("🆕 새 퀴즈 배포"):
            c = st.text_input("카테고리"); t = st.text_input("제목"); tx = st.text_area("내용")
            if st.button("배포하기"):
                ws = get_worksheet("Quizzes", ["Category", "Title", "Content", "CreatedAt"])
                ws.append_row([c, t, tx, time.strftime('%Y-%m-%d %H:%M:%S')])
                get_all_quizzes.clear(); st.rerun()

    st.divider()
    qr = qrcode.QRCode(version=1, box_size=3, border=2)
    qr.add_data("https://hoya-quiz-studio.streamlit.app"); qr.make(fit=True)
    buf = BytesIO(); qr.make_image().save(buf)
    st.image(buf.getvalue(), caption="App QR Code", width=120)

# --- 5. 메인 화면 ---
st.title("🧪 우정 파괴소")
st.session_state.player_name = st.text_input("👤 참가자 이름", value=st.session_state.player_name)
st.divider()

quiz_list = get_all_quizzes()
if quiz_list:
    cats = list(dict.fromkeys([q['Category'] or '미분류' for q in quiz_list]))
    if admin['cat'] in cats: cats.remove(admin['cat']); cats.insert(0, admin['cat'])
    
    tabs = st.tabs(cats)
    for i, cat in enumerate(cats):
        with tabs[i]:
            cat_qs = [q for q in quiz_list if (q['Category'] or '미분류') == cat]
            cols = st.columns(2)
            for j, q in enumerate(cat_qs):
                if cols[j % 2].button(q['Title'], key=f"sel_{cat}_{j}", use_container_width=True):
                    st.session_state.selected_quiz_title = q['Title']
                    st.session_state.quiz_finished = False; st.session_state.start_time = None
                    st.session_state.user_answers = {}; st.rerun()

    if st.session_state.selected_quiz_title:
        q_data = next(q for q in quiz_list if q['Title'] == st.session_state.selected_quiz_title)
        quiz_content = robust_parse(q_data['Content'])
        
        if st.session_state.start_time is None and not st.session_state.quiz_finished:
            if st.button(f"🚀 {st.session_state.selected_quiz_title} 시작!", use_container_width=True):
                st.session_state.start_time = time.time(); st.rerun()
        
        elif not st.session_state.quiz_finished:
            st.markdown(f"## 📖 {st.session_state.selected_quiz_title}")
            
            for idx, item in enumerate(quiz_content):
                st.markdown(f'<p class="question-header">문제 {idx+1}</p>', unsafe_allow_html=True)
                
                # 📌 지문 태그(<지문>)가 있으면 박스 처리, 없으면 일반 출력
                display_text = item['q']
                if "<지문>" in display_text and "</지문>" in display_text:
                    display_text = display_text.replace("<지문>", '<div class="passage-container">').replace("</지문>", '</div>')
                    st.markdown(display_text, unsafe_allow_html=True)
                else:
                    st.markdown(f'<div class="passage-container">{display_text}</div>', unsafe_allow_html=True)
                
                is_ans = f"ans_{idx}" in st.session_state.user_answers
                ans = st.radio(f"보기_{idx}", item['o'], index=None, key=f"r_{idx}", disabled=is_ans, label_visibility="collapsed")
                
                if ans and not is_ans:
                    st.session_state.user_answers[f"ans_{idx}"] = ans
                    if admin['mode'] == "⚡ 실시간 팩폭 (즉시 확인)":
                        if ans == item['o'][item['a']]: st.success("⭕ 정답!")
                        else: st.error(f"❌ 오답! (정답: {item['o'][item['a']]})")
                st.divider()

            if st.button("🏁 최종 제출하기"):
                if len(st.session_state.user_answers) >= len(quiz_content):
                    save_result_to_gsheet(st.session_state.selected_quiz_title, st.session_state.player_name, 100, 0, [])
                    st.session_state.quiz_finished = True; st.rerun()
                else: st.warning("모든 문제를 풀어주세요!")

        if st.session_state.quiz_finished:
            st.balloons(); st.success("🎉 모든 문제를 풀었습니다!"); st.button("다른 퀴즈 하기", on_click=lambda: st.rerun())
