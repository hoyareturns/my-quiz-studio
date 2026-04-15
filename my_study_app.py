import streamlit as st
import re
import time
import pandas as pd
import gspread
import json
import qrcode
from io import BytesIO
from collections import Counter

# --- 0. 페이지 설정 및 강력한 2열 고정 CSS ---
st.set_page_config(page_title="우정 파괴소", page_icon="🧪", layout="centered")

# 📱 탭 안의 버튼들을 무조건 2열로 정렬하는 가장 강력한 CSS
st.markdown("""
<style>
/* 탭 내부의 수직 블록을 그리드로 강제 변환 */
[data-testid="stTabs"] div[data-testid="stVerticalBlock"] > div {
    display: grid !important;
    grid-template-columns: repeat(2, 1fr) !important;
    gap: 10px !important;
}

/* 버튼들을 감싸는 div가 100%를 차지하게 설정 */
[data-testid="stTabs"] div[data-testid="stVerticalBlock"] > div > div {
    width: 100% !important;
    max-width: 100% !important;
}

/* 버튼 스타일 조정 (2열일 때 글자 안 잘리게) */
.stButton > button {
    width: 100% !important;
    white-space: normal !important;
    word-break: keep-all !important;
    min-height: 60px !important;
    padding: 5px !important;
    font-size: 14px !important;
}
</style>
""", unsafe_allow_html=True)

# --- 1. 구글 시트 연동 설정 ---
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

# --- 2. 데이터 처리 로직 ---
@st.cache_data(ttl=15, show_spinner=False)
def get_all_quizzes():
    ws = get_worksheet("Quizzes", ["Category", "Title", "Content", "CreatedAt"])
    if ws:
        data = ws.get_all_records()
        return sorted(data, key=lambda x: str(x.get('CreatedAt', '')), reverse=True)
    return []

@st.cache_data(ttl=15, show_spinner=False)
def get_all_results():
    res_ws = get_worksheet("Results", ["QuizTitle", "User", "Score", "Duration", "Time"])
    if res_ws: return res_ws.get_all_records()
    return []

@st.cache_data(ttl=30, show_spinner=False)
def get_weak_points_from_gsheet():
    ws = get_worksheet("WrongAnswers", ["User", "Keyword", "Time"])
    if ws:
        data = ws.get_all_records()
        if data:
            counts = Counter([d.get('Keyword', '') for d in data if d.get('Keyword', '')])
            return ", ".join([f"{k}({c}회)" for k, c in counts.most_common(3)])
    return "데이터 없음"

def delete_quiz_from_gsheet(quiz_title):
    ws = get_worksheet("Quizzes", ["Category", "Title", "Content", "CreatedAt"])
    if ws:
        try:
            cell = ws.find(quiz_title)
            if cell:
                ws.delete_rows(cell.row)
                get_all_quizzes.clear()
                return True
        except Exception: pass
    return False

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
    get_weak_points_from_gsheet.clear()

def robust_parse(text):
    qs = re.findall(r"\[Q\d?\]\s*(.*)", text)
    os_raw = re.findall(r"\[O\]\s*(.*)", text)
    as_raw = re.findall(r"\[A\]\s*(.*)", text)
    ks = re.findall(r"\[K\]\s*(.*)", text)
    parsed = []
    ans_map = {'①':0, '②':1, '③':2, '④':3, '⑤':4, '1':0, '2':1, '3':2, '4':3, '5':4}
    for i in range(len(qs)):
        if i >= len(os_raw) or i >= len(as_raw): break
        opts = re.findall(r'[①-⑤]\s*([^①-⑤]+)', os_raw[i])
        if not opts: opts = [o.strip() for o in os_raw[i].split(',') if o.strip()]
        ans_char = as_raw[i].strip()[0] if as_raw[i] else "1"
        parsed.append({"q": qs[i].replace('**', '').strip(), "o": [o.strip() for o in opts],
                       "a": ans_map.get(ans_char, 0), "k": ks[i] if i < len(ks) else "미분류"})
    return parsed

# --- 3. 기본 설정 변수 ---
APP_URL = "https://hoya-quiz-studio.app"
ADMIN_PASSWORD = "1234"

# --- 4. 세션 및 접속자 관리 ---
if 'player_name' not in st.session_state: st.session_state.player_name = ""
if 'start_time' not in st.session_state: st.session_state.start_time = None
if 'quiz_finished' not in st.session_state: st.session_state.quiz_finished = False
if 'user_answers' not in st.session_state: st.session_state.user_answers = {}
if 'selected_quiz_title' not in st.session_state: st.session_state.selected_quiz_title = ""

@st.cache_resource
def get_admin_settings():
    return {"feedback_mode": "⚡ 실시간 팩폭 (즉시 확인)", "allow_change": False, "default_category": ""}

@st.cache_resource
def get_active_users(): return set()

admin_settings = get_admin_settings()
active_users = get_active_users()

# --- 5. UI (사이드바) ---
with st.sidebar:
    st.markdown(f"<div style='display: flex; justify-content: space-between; align-items: center;'><h3 style='margin: 0;'>관리자 설정</h3><span style='font-size: 14px; color: #4CAF50;'>🟢 풀이중: {len(active_users)}명</span></div>", unsafe_allow_html=True)
    pw_input = st.text_input("PW", type="password", placeholder="PW", label_visibility="collapsed")
    
    if pw_input == ADMIN_PASSWORD:
        st.success("인증됨")
        weak_points = get_weak_points_from_gsheet()
        st.caption(f"📊 취약: {weak_points}")
        admin_settings['default_category'] = st.text_input("📌 기본 카테고리", value=admin_settings.get('default_category', ''))
        mode_options = ["⚡ 실시간 팩폭 (즉시 확인)", "🏁 최후의 심판 (마지막에 한 번에)"]
        admin_settings['feedback_mode'] = st.selectbox("채점", mode_options, index=mode_options.index(admin_settings['feedback_mode']))
        admin_settings['allow_change'] = (admin_settings['feedback_mode'] != mode_options[0])
        
        with st.expander("🆕 새 퀴즈"):
            c1 = st.text_input("카테고리"); t1 = st.text_input("제목"); tx = st.text_area("내용")
            if st.button("🚀 배포"):
                ws = get_worksheet("Quizzes", ["Category", "Title", "Content", "CreatedAt"])
                ws.append_row([c1, t1, tx, time.strftime('%Y-%m-%d %H:%M:%S')])
                get_all_quizzes.clear(); st.rerun()
        with st.expander("🗑️ 삭제"):
            for idx, q in enumerate(get_all_quizzes()):
                col1, col2 = st.columns([3, 1])
                col1.caption(f"{q['Title']}")
                if col2.button("X", key=f"del_{idx}"):
                    if delete_quiz_from_gsheet(q['Title']): st.rerun()

    st.divider()
    qr = qrcode.QRCode(version=1, box_size=3, border=2)
    qr.add_data(APP_URL); qr.make(fit=True)
    buf = BytesIO(); qr.make_image(fill_color="black", back_color="white").save(buf)
    st.image(buf.getvalue(), width=100)

# --- 6. 메인 영역 ---
st.title("🧪 우정 파괴소")
st.text_input("👤 참가자 이름", key="player_name", placeholder="이름을 입력하세요")
st.divider()

quiz_data_list = get_all_quizzes()
if not quiz_data_list:
    st.info("등록된 퀴즈가 없습니다.")
else:
    st.subheader("🎯 퀴즈 선택")
    categories = list(dict.fromkeys([q.get('Category', '미분류') or '미분류' for q in quiz_data_list]))
    pref_cat = admin_settings.get('default_category', '').strip()
    if pref_cat in categories:
        categories.remove(pref_cat); categories.insert(0, pref_cat)
        
    tabs = st.tabs(categories)
    for i, cat in enumerate(categories):
        with tabs[i]:
            cat_quizzes = [q for q in quiz_data_list if (q.get('Category') or '미분류') == cat]
            # 📌 st.columns를 쓰지 않고 버튼을 나열합니다. CSS 그리드가 2열로 만들어줍니다.
            for j, q in enumerate(cat_quizzes):
                q_title = q['Title']
                label = f"🔥 {q_title}" if q_title == st.session_state.selected_quiz_title else q_title
                if st.button(label, use_container_width=True, key=f"btn_{cat}_{j}"):
                    st.session_state.selected_quiz_title = q_title
                    st.session_state.quiz_finished = False; st.session_state.start_time = None
                    st.session_state.user_answers = {}; st.rerun()

    if st.session_state.selected_quiz_title:
        selected_quiz_data = next((q for q in quiz_data_list if q['Title'] == st.session_state.selected_quiz_title), None)
        if selected_quiz_data:
            quiz_title = selected_quiz_data['Title']; quiz_content = robust_parse(selected_quiz_data['Content'])
            
            with st.expander("📊 실시간 순위"):
                if st.button("🔄 갱신"): get_all_results.clear(); st.rerun()
                all_res = get_all_results()
                quiz_res = [r for r in all_res if r.get('QuizTitle') == quiz_title]
                if quiz_res: st.dataframe(pd.DataFrame(quiz_res).sort_values(by=['Score', 'Duration'], ascending=[False, True]), use_container_width=True)
                else: st.caption("기록 없음")

            if not st.session_state.player_name:
                st.warning("👤 이름을 입력하세요!")
            elif st.session_state.start_time is None and not st.session_state.quiz_finished:
                if st.button(f"🚀 {quiz_title} 시작!", use_container_width=True):
                    st.session_state.start_time = time.time(); active_users.add(st.session_state.player_name); st.rerun()
            elif st.session_state.start_time and not st.session_state.quiz_finished:
                st.subheader(f"🔥 {st.session_state.player_name}의 도전")
                
                if admin_settings['feedback_mode'] == "⚡ 실시간 팩폭 (즉시 확인)":
                    for idx, item in enumerate(quiz_content):
                        st.markdown(f"**Q{idx+1}. {item['q']}**")
                        ans = st.radio(f"답안{idx}", item['o'], key=f"ans_{idx}", index=None, label_visibility="collapsed", disabled=f"ans_{idx}" in st.session_state.user_answers)
                        if ans:
                            st.session_state.user_answers[f"ans_{idx}"] = ans
                            if ans == item['o'][item['a']]: st.success("⭕ 정답!")
                            else: st.error(f"❌ 오답! (정답: {item['o'][item['a']]})")
                        st.divider()
                    if st.button("🏁 제출하기", use_container_width=True):
                        if len(st.session_state.user_answers) < len(quiz_content): st.warning("다 푸세요!")
                        else:
                            duration = time.time() - st.session_state.start_time
                            wrong = [q['k'] for k_i, q in enumerate(quiz_content) if st.session_state.user_answers.get(f"ans_{k_i}") != q['o'][q['a']]]
                            score = ((len(quiz_content)-len(wrong))/len(quiz_content))*100
                            save_result_to_gsheet(quiz_title, st.session_state.player_name, score, duration, wrong)
                            st.session_state.quiz_finished = True; st.session_state.last_score = score
                            st.session_state.review_data = [{"q": q['q'], "u_ans": st.session_state.user_answers.get(f"ans_{k_i}"), "c_ans": q['o'][q['a']], "is_correct": st.session_state.user_answers.get(f"ans_{k_i}") == q['o'][q['a']]} for k_i, q in enumerate(quiz_content)]
                            active_users.discard(st.session_state.player_name); st.rerun()
                else:
                    with st.form("quiz_form"):
                        for idx, item in enumerate(quiz_content):
                            st.markdown(f"**Q{idx+1}. {item['q']}**")
                            st.radio(f"답안{idx}", item['o'], key=f"ans_form_{idx}", index=None, label_visibility="collapsed")
                            st.divider()
                        if st.form_submit_button("🏁 제출", use_container_width=True):
                            if any(st.session_state.get(f"ans_form_{i}") is None for i in range(len(quiz_content))): st.warning("다 푸세요!")
                            else:
                                duration = time.time() - st.session_state.start_time
                                wrong = [q['k'] for k_i, q in enumerate(quiz_content) if st.session_state.get(f"ans_form_{k_i}") != q['o'][q['a']]]
                                score = ((len(quiz_content)-len(wrong))/len(quiz_content))*100
                                save_result_to_gsheet(quiz_title, st.session_state.player_name, score, duration, wrong)
                                st.session_state.quiz_finished = True; st.session_state.last_score = score
                                st.session_state.review_data = [{"q": q['q'], "u_ans": st.session_state.get(f"ans_form_{k_i}"), "c_ans": q['o'][q['a']], "is_correct": st.session_state.get(f"ans_form_{k_i}") == q['o'][q['a']]} for k_i, q in enumerate(quiz_content)]
                                active_users.discard(st.session_state.player_name); st.rerun()

            if st.session_state.quiz_finished:
                st.balloons(); st.success(f"🏁 점수: {int(st.session_state.last_score)}점!")
                if admin_settings['feedback_mode'] != "⚡ 실시간 팩폭 (즉시 확인)":
                    with st.expander("📝 채점 결과", expanded=True):
                        for i, r in enumerate(st.session_state.review_data):
                            st.markdown(f"**Q{i+1}. {r['q']}**\n{'⭕ 정답' if r['is_correct'] else f'❌ 오답 (정답: {r['c_ans']})'}")
                if st.button("다른 퀴즈 하기"):
                    st.session_state.quiz_finished = False; st.session_state.start_time = None; st.session_state.user_answers = {}; st.rerun()
