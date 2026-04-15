import streamlit as st
import re
import time
import pandas as pd
import gspread
import json
import qrcode
from io import BytesIO
from collections import Counter

# --- 0. 페이지 설정 및 디자인 (지문 박스 + 모바일 최적화) ---
st.set_page_config(page_title="우정 파괴소", page_icon="🧪", layout="centered")

st.markdown("""
<style>
/* 📖 지문 전용 상자 (국어/영어/사회 지문 가독성) */
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
/* 문제 헤더 */
.question-header {
    font-size: 18px;
    font-weight: 800;
    color: #ff4b4b;
    margin-top: 30px;
}
/* 모바일 2열 레이아웃 */
@media (max-width: 768px) {
    [data-testid="stTabs"] [data-testid="column"] {
        flex: 1 1 calc(50% - 10px) !important;
        min-width: calc(45%) !important;
    }
}
</style>
""", unsafe_allow_html=True)

# --- 1. 구글 시트 연동 설정 ---
@st.cache_resource
def get_gspread_client():
    try:
        credentials = json.loads(st.secrets["GCP_JSON"], strict=False)
        gc = gspread.service_account_from_dict(credentials)
        return gc.open_by_key(st.secrets["SHEET_ID"])
    except: return None

def get_worksheet(sheet_name, columns=None):
    try:
        sh = get_gspread_client()
        if not sh: return None
        try:
            ws = sh.worksheet(sheet_name)
        except gspread.exceptions.WorksheetNotFound:
            if columns:
                ws = sh.add_worksheet(title=sheet_name, rows="100", cols=len(columns))
                ws.append_row(columns)
                return ws
            return None
        return ws
    except: return None

# --- 2. 데이터 처리 및 파싱 로직 ---
@st.cache_data(ttl=15, show_spinner=False)
def get_all_quizzes():
    ws = get_worksheet("Quizzes", ["Category", "Title", "Content", "CreatedAt"])
    return ws.get_all_records() if ws else []

@st.cache_data(ttl=15, show_spinner=False)
def get_all_results():
    ws = get_worksheet("Results", ["QuizTitle", "User", "Score", "Duration", "Time"])
    return ws.get_all_records() if ws else []

@st.cache_data(ttl=30, show_spinner=False)
def get_weak_points_from_gsheet():
    try:
        ws = get_worksheet("WrongAnswers")
        if ws:
            data = ws.get_all_records()
            if data:
                counts = Counter([d.get('Keyword', '') for d in data if d.get('Keyword', '')])
                return ", ".join([f"{k}({v}회)" for k, v in counts.most_common(2)])
    except: pass
    return "데이터 없음"

def robust_parse(text):
    chunks = re.split(r"\[Q\d*\]", text)
    parsed = []
    ans_map = {'①':0, '②':1, '③':2, '④':3, '⑤':4, '1':0, '2':1, '3':2, '4':3, '5':4}
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
            ans_idx = ans_map.get(a_raw.strip()[0] if a_raw else "1", 0)
            parsed.append({"q": q_raw, "o": [o.strip() for o in opts], "a": ans_idx, "k": k_raw})
        except: continue
    return parsed

# --- 3. 관리 및 저장 로직 ---
def delete_quiz(title):
    ws = get_worksheet("Quizzes")
    if ws:
        try:
            cell = ws.find(title)
            if cell: ws.delete_rows(cell.row); get_all_quizzes.clear(); return True
        except: pass
    return False

def save_result(title, user, score, duration, wrongs):
    res_ws = get_worksheet("Results", ["QuizTitle", "User", "Score", "Duration", "Time"])
    if res_ws:
        res_ws.append_row([title, user, score, round(duration, 2), time.strftime('%Y-%m-%d %H:%M:%S')])
    if wrongs:
        wr_ws = get_worksheet("WrongAnswers", ["User", "Keyword", "Time"])
        if wr_ws:
            for k in wrongs: wr_ws.append_row([user, k, time.strftime('%Y-%m-%d %H:%M:%S')])
    get_all_results.clear()

# --- 4. 세션 및 기본 설정 ---
APP_URL = "https://hoya-quiz-studio.streamlit.app"
ADMIN_PASSWORD = "1234"

if 'player_name' not in st.session_state: st.session_state.player_name = ""
if 'selected_quiz_title' not in st.session_state: st.session_state.selected_quiz_title = ""
if 'user_answers' not in st.session_state: st.session_state.user_answers = {}
if 'quiz_finished' not in st.session_state: st.session_state.quiz_finished = False
if 'start_time' not in st.session_state: st.session_state.start_time = None

@st.cache_resource
def get_admin_settings():
    return {"feedback_mode": "⚡ 실시간 팩폭 (즉시 확인)", "default_category": "", "allow_change": False}
admin_settings = get_admin_settings()

@st.cache_resource
def get_active_users(): return set()
active_users = get_active_users()

# --- 5. 사이드바 (프롬프트 상단 고정 + 전 기능 복구) ---
with st.sidebar:
    # 🟢 실시간 접속자
    st.markdown(f"<div style='text-align:right;'><span style='font-size: 13px; color: #4CAF50;'>🟢 풀이중: {len(active_users)}명</span></div>", unsafe_allow_html=True)
    
    # 📌 [최상단 고정] AI 출제 프롬프트 가이드 (Raw String 사용으로 에러 차단)
    st.info("🪄 **AI 출제 프롬프트 (지문 포함)**")
    st.code("""국어/영어 문제 10개를 출제해줘. 지문이 있는 경우 반드시 포함하되, 아래 형식을 엄격히 지켜줘.

[Q]
<지문>
여기에 소설, 시, 영어 본문 등 지문 입력 (줄바꿈 가능)
</지문>
문제 내용(발문) 입력

[O] ①보기1 ②보기2 ③보기3 ④보기4 ⑤보기5
[A] 정답 기호(예: ②)
[K] 핵심 키워드""", language="text")
    st.divider()

    # 🔑 관리자 인증 영역
    pw_input = st.text_input("관리자 암호", type="password", placeholder="Password")
    if pw_input == ADMIN_PASSWORD:
        st.success("인증됨")
        w_points = get_weak_points_from_gsheet()
        st.caption(f"📊 취약 분석: {w_points}")
        
        admin_settings['default_category'] = st.text_input("📌 초기 카테고리", value=admin_settings.get('default_category', ''))
        
        with st.expander("🆕 새 퀴즈 배포", expanded=False):
            c = st.text_input("카테고리"); t = st.text_input("제목"); tx = st.text_area("내용")
            if st.button("🚀 배포"):
                ws = get_worksheet("Quizzes", ["Category", "Title", "Content", "CreatedAt"])
                if ws: ws.append_row([c, t, tx, time.strftime('%Y-%m-%d %H:%M:%S')])
                get_all_quizzes.clear(); st.success("완료!"); st.rerun()

        with st.expander("🗑️ 퀴즈 삭제", expanded=False):
            all_q = get_all_quizzes()
            for idx, q in enumerate(all_q):
                col1, col2 = st.columns([3, 1])
                col1.caption(f"{q.get('Title')}")
                if col2.button("X", key=f"del_{idx}"):
                    if delete_quiz(q.get('Title')): st.rerun()

    st.divider()
    qr = qrcode.QRCode(version=1, box_size=3, border=2)
    qr.add_data(APP_URL); qr.make(fit=True)
    buf = BytesIO(); qr.make_image().save(buf)
    st.image(buf.getvalue(), width=100)

# --- 6. 메인 영역 (순위표 + 지문 지원 퀴즈) ---
st.title("🧪 우정 파괴소")
st.session_state.player_name = st.text_input("👤 이름", value=st.session_state.player_name, placeholder="이름을 입력하세요")
st.divider()

quiz_data = get_all_quizzes()
if quiz_data:
    cats = list(dict.fromkeys([q.get('Category', '미분류') or '미분류' for q in quiz_data]))
    pref = admin_settings.get('default_category', '').strip()
    if pref in cats: cats.remove(pref); cats.insert(0, pref)
    
    tabs = st.tabs(cats)
    for i, cat in enumerate(cats):
        with tabs[i]:
            cat_qs = [q for q in quiz_data if (q.get('Category') or '미분류') == cat]
            cols = st.columns(2)
            for j, q in enumerate(cat_qs):
                t = q.get('Title')
                if cols[j % 2].button(t, key=f"q_{cat}_{j}", use_container_width=True):
                    st.session_state.selected_quiz_title = t
                    st.session_state.quiz_finished = False; st.session_state.start_time = None
                    st.session_state.user_answers = {}; st.rerun()

    if st.session_state.selected_quiz_title:
        curr_q = next((q for q in quiz_data if q['Title'] == st.session_state.selected_quiz_title), None)
        if curr_q:
            parsed_content = robust_parse(curr_q['Content'])

            # 📊 순위표 (복구)
            with st.expander("📊 실시간 순위표", expanded=False):
                if st.button("🔄 갱신"): get_all_results.clear(); st.rerun()
                q_res = [r for r in get_all_results() if r.get('QuizTitle') == curr_q['Title']]
                if q_res: st.dataframe(pd.DataFrame(q_res).sort_values(by=['Score', 'Duration'], ascending=[False, True]), use_container_width=True)
                else: st.caption("기록 없음")

            if not st.session_state.player_name:
                st.warning("👤 이름을 입력해야 시작할 수 있습니다.")
            elif st.session_state.start_time is None and not st.session_state.quiz_finished:
                if st.button(f"🚀 {curr_q['Title']} 시작!", use_container_width=True):
                    st.session_state.start_time = time.time(); active_users.add(st.session_state.player_name); st.rerun()
            elif st.session_state.start_time and not st.session_state.quiz_finished:
                for idx, item in enumerate(parsed_content):
                    st.markdown(f'<p class="question-header">Q{idx+1}.</p>', unsafe_allow_html=True)
                    
                    # 📌 지문 인식 및 전용 박스 처리
                    disp = item['q']
                    if "<지문>" in disp and "</지문>" in disp:
                        disp = disp.replace("<지문>", '<div class="passage-container">').replace("</지문>", '</div>')
                        st.markdown(disp, unsafe_allow_html=True)
                    else:
                        st.markdown(f'<div class="passage-container">{disp}</div>', unsafe_allow_html=True)
                    
                    is_ans = f"ans_{idx}" in st.session_state.user_answers
                    ans = st.radio(f"보기_{idx}", item['o'], index=None, key=f"r_{idx}", disabled=is_ans, label_visibility="collapsed")
                    if ans:
                        st.session_state.user_answers[f"ans_{idx}"] = ans
                        if ans == item['o'][item['a']]: st.success("⭕ 정답!")
                        else: st.error(f"❌ 오답! (정답: {item['o'][item['a']]})")
                    st.divider()

                if st.button("🏁 최종 제출"):
                    if len(st.session_state.user_answers) >= len(parsed_content):
                        wrongs = [q['k'] for k_i, q in enumerate(parsed_content) if st.session_state.user_answers.get(f"ans_{k_i}") != q['o'][q['a']]]
                        score = ((len(parsed_content)-len(wrongs))/len(parsed_content))*100
                        save_result(curr_q['Title'], st.session_state.player_name, score, time.time()-st.session_state.start_time, wrongs)
                        st.session_state.quiz_finished = True; st.rerun()
                    else: st.warning("모든 문제를 풀어주세요!")

        if st.session_state.quiz_finished:
            active_users.discard(st.session_state.player_name)
            st.balloons(); st.success("🎉 수고하셨습니다!"); st.button("다른 퀴즈", on_click=lambda: st.rerun())
