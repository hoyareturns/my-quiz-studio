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
/* 지문 박스 스타일 */
.passage-box {
    background-color: #f8f9fa;
    border-left: 5px solid #ff4b4b;
    padding: 15px;
    border-radius: 5px;
    font-size: 14px;
    line-height: 1.6;
    margin-bottom: 20px;
    white-space: pre-wrap; /* 줄바꿈 보존 */
}
/* 모바일 2열 유지 (가로 모드용) */
@media (min-width: 768px) {
    [data-testid="stTabs"] div[data-testid="stVerticalBlock"] > div[style*="flex-direction: column;"] {
        flex-direction: row !important;
        flex-wrap: wrap !important;
        gap: 10px !important;
    }
    [data-testid="stTabs"] [data-testid="column"] {
        flex: 1 1 calc(50% - 15px) !important;
    }
}
</style>
""", unsafe_allow_html=True)

# --- 1. 구글 시트 연동 ---
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

# --- 2. 데이터 처리 및 파싱 (지문 보존 핵심) ---
@st.cache_data(ttl=15, show_spinner=False)
def get_all_quizzes():
    ws = get_worksheet("Quizzes", ["Category", "Title", "Content", "CreatedAt"])
    if ws:
        data = ws.get_all_records()
        return sorted(data, key=lambda x: str(x.get('CreatedAt', '')), reverse=True)
    return []

def robust_parse(text):
    # [Q] 또는 [Q1] 단위로 문제 덩어리를 나눕니다.
    chunks = re.split(r"\[Q\d*\]", text)
    parsed = []
    
    for chunk in chunks:
        if not chunk.strip(): continue
        try:
            # [O], [A], [K]를 기준으로 쪼갭니다.
            # 쪼개진 첫 번째 조각(parts[0])은 [O]가 나오기 전까지의 모든 내용(지문+발문)입니다.
            parts = re.split(r"(\[O\]|\[A\]|\[K\])", chunk)
            
            q_raw = parts[0].strip()
            o_raw = ""
            a_raw = "1"
            k_raw = "미분류"
            
            for i in range(len(parts)):
                tag = parts[i].strip()
                if tag == "[O]": o_raw = parts[i+1].strip()
                elif tag == "[A]": a_raw = parts[i+1].strip()
                elif tag == "[K]": k_raw = parts[i+1].strip()

            # 보기 추출 (①~⑤)
            opts = re.findall(r'[①-⑤]\s*([^①-⑤\n\r]+)', o_raw)
            if not opts: opts = [o.strip() for o in o_raw.split(',') if o.strip()]
            
            # 정답 변환
            ans_map = {'①':0, '②':1, '③':2, '④':3, '⑤':4, '1':0, '2':1, '3':2, '4':3, '5':4}
            ans_match = re.search(r'[①-⑤1-5]', a_raw)
            ans_idx = ans_map.get(ans_match.group(), 0) if ans_match else 0
            
            parsed.append({"q": q_raw, "o": opts, "a": ans_idx, "k": k_raw})
        except: continue
    return parsed

# --- 3. 공용 함수 ---
def save_result_to_gsheet(quiz_title, user_id, score, duration, wrong_keywords):
    res_ws = get_worksheet("Results", ["QuizTitle", "User", "Score", "Duration", "Time"])
    if res_ws:
        res_ws.append_row([quiz_title, user_id, score, round(duration, 2), time.strftime('%Y-%m-%d %H:%M:%S')])
    if wrong_keywords:
        wrong_ws = get_worksheet("WrongAnswers", ["User", "Keyword", "Time"])
        if wrong_ws:
            for k in wrong_keywords:
                wrong_ws.append_row([user_id, k, time.strftime('%Y-%m-%d %H:%M:%S')])
    get_all_results.clear()

@st.cache_data(ttl=15, show_spinner=False)
def get_all_results():
    ws = get_worksheet("Results", ["QuizTitle", "User", "Score", "Duration", "Time"])
    return ws.get_all_records() if ws else []

# --- 4. 세션 관리 ---
for key in ['player_name', 'selected_quiz_title', 'user_answers', 'quiz_finished']:
    if key not in st.session_state:
        if key == 'user_answers': st.session_state[key] = {}
        elif key == 'quiz_finished': st.session_state[key] = False
        else: st.session_state[key] = ""

if 'start_time' not in st.session_state: st.session_state.start_time = None

@st.cache_resource
def get_admin_settings():
    return {"feedback_mode": "⚡ 실시간 팩폭 (즉시 확인)", "allow_change": False, "default_category": ""}

admin_settings = get_admin_settings()

# --- 5. 사이드바 ---
with st.sidebar:
    st.header("⚙️ 관리자")
    pw = st.text_input("비밀번호", type="password")
    if pw == "1234":
        st.success("인증됨")
        admin_settings['default_category'] = st.text_input("📌 기본 카테고리", value=admin_settings.get('default_category', ''))
        mode_options = ["⚡ 실시간 팩폭 (즉시 확인)", "🏁 최후의 심판 (마지막에 한 번에)"]
        admin_settings['feedback_mode'] = st.selectbox("채점 방식", mode_options, index=mode_options.index(admin_settings['feedback_mode']))
        admin_settings['allow_change'] = (admin_settings['feedback_mode'] != mode_options[0])
        
        with st.expander("🆕 새 퀴즈 배포"):
            c = st.text_input("카테고리")
            t = st.text_input("제목")
            cont = st.text_area("내용 ([Q][O][A][K] 형식)")
            if st.button("배포"):
                ws = get_worksheet("Quizzes", ["Category", "Title", "Content", "CreatedAt"])
                ws.append_row([c, t, cont, time.strftime('%Y-%m-%d %H:%M:%S')])
                get_all_quizzes.clear(); st.rerun()

# --- 6. 메인 화면 ---
st.title("🧪 우정 파괴소")
st.session_state.player_name = st.text_input("👤 참가자 이름", value=st.session_state.player_name)
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
                if cols[j % 2].button(q['Title'], key=f"sel_{cat}_{j}", use_container_width=True):
                    st.session_state.selected_quiz_title = q['Title']
                    st.session_state.quiz_finished = False
                    st.session_state.start_time = None
                    st.session_state.user_answers = {}
                    st.rerun()

    if st.session_state.selected_quiz_title:
        q_data = next(q for q in quiz_list if q['Title'] == st.session_state.selected_quiz_title)
        parsed_qs = robust_parse(q_data['Content'])
        
        # 퀴즈 시작 전
        if st.session_state.start_time is None and not st.session_state.quiz_finished:
            if st.button(f"🚀 {st.session_state.selected_quiz_title} 시작!", use_container_width=True):
                st.session_state.start_time = time.time()
                st.rerun()
        
        # 퀴즈 진행 중
        elif not st.session_state.quiz_finished:
            st.subheader(f"📖 {st.session_state.selected_quiz_title}")
            
            # 실시간/최후의 심판 모드 분기
            if admin_settings['feedback_mode'] == "⚡ 실시간 팩폭 (즉시 확인)":
                for idx, item in enumerate(parsed_qs):
                    st.markdown(f"### Q{idx+1}")
                    # 📌 지문 출력 (pre-wrap 적용된 div 사용)
                    st.markdown(f'<div class="passage-box">{item["q"]}</div>', unsafe_allow_html=True)
                    
                    is_ans = f"ans_{idx}" in st.session_state.user_answers
                    ans = st.radio(f"보기_{idx}", item['o'], index=None, key=f"r_{idx}", disabled=is_ans, label_visibility="collapsed")
                    if ans and not is_ans:
                        st.session_state.user_answers[f"ans_{idx}"] = ans
                        if ans == item['o'][item['a']]: st.success("⭕ 정답!")
                        else: st.error(f"❌ 오답! (정답: {item['o'][item['a']]})")
                    st.divider()
                if st.button("🏁 제출하기"):
                    if len(st.session_state.user_answers) >= len(parsed_qs):
                        duration = time.time() - st.session_state.start_time
                        wrong = [q['k'] for k_i, q in enumerate(parsed_qs) if st.session_state.user_answers.get(f"ans_{k_i}") != q['o'][q['a']]]
                        score = ((len(parsed_qs)-len(wrong))/len(parsed_qs))*100
                        save_result_to_gsheet(st.session_state.selected_quiz_title, st.session_state.player_name, score, duration, wrong)
                        st.session_state.quiz_finished = True; st.rerun()
                    else: st.warning("모든 문제를 풀어주세요!")
            else:
                with st.form("quiz_form"):
                    for idx, item in enumerate(parsed_qs):
                        st.markdown(f"### Q{idx+1}")
                        st.markdown(f'<div class="passage-box">{item["q"]}</div>', unsafe_allow_html=True)
                        st.radio(f"보기_{idx}", item['o'], index=None, key=f"ans_form_{idx}", label_visibility="collapsed")
                        st.divider()
                    if st.form_submit_button("🏁 모든 답안 제출하기"):
                        if all(st.session_state.get(f"ans_form_{i}") for i in range(len(parsed_qs))):
                            duration = time.time() - st.session_state.start_time
                            wrong, review = [], []
                            for k_i, q in enumerate(parsed_qs):
                                u_ans = st.session_state.get(f"ans_form_{k_i}")
                                is_corr = (u_ans == q['o'][q['a']])
                                if not is_corr: wrong.append(q['k'])
                                review.append({"q": q['q'], "u": u_ans, "c": q['o'][q['a']], "is": is_corr})
                            score = ((len(parsed_qs)-len(wrong))/len(parsed_qs))*100
                            save_result_to_gsheet(st.session_state.selected_quiz_title, st.session_state.player_name, score, duration, wrong)
                            st.session_state.quiz_finished = True; st.session_state.review_data = review; st.rerun()
                        else: st.error("미기입 문항이 있습니다!")

        # 퀴즈 종료 후
        if st.session_state.quiz_finished:
            st.balloons(); st.success("🎉 수고하셨습니다!")
            if admin_settings['feedback_mode'] != "⚡ 실시간 팩폭 (즉시 확인)":
                with st.expander("📝 채점 결과 보기", expanded=True):
                    for i, r in enumerate(st.session_state.review_data):
                        st.markdown(f"**Q{i+1}.** {'⭕' if r['is'] else '❌'}")
                        if not r['is']: st.caption(f"정답: {r['c']}")
            if st.button("다른 퀴즈 하기"):
                st.session_state.quiz_finished = False; st.session_state.start_time = None; st.rerun()
