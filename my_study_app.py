import streamlit as st
import re
import time
import pandas as pd
import gspread
import json
import qrcode
from io import BytesIO
from collections import Counter

# --- 0. 페이지 설정 ---
st.set_page_config(page_title="우정 파괴소", page_icon="🧪", layout="centered")

# --- 1. 구글 시트 연동 설정 (캐시 적용) ---
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

# --- 2. 데이터 처리 로직 (속도 최적화) ---
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
    # 1. 문제를 [Q] 또는 [Q1], [Q2] 단위로 크게 쪼갭니다.
    # (다음 [Q]가 나오기 전까지의 모든 내용을 하나의 문제 덩어리로 인식)
    raw_problems = re.split(r"\[Q\d?\]", text)
    
    parsed = []
    # split 결과의 첫 번째 요소는 보통 빈 문자열이므로 제외하고 반복
    for prob in raw_problems[1:]:
        try:
            # 2. 각 문제 덩어리 안에서 [O], [A], [K]를 기준으로 데이터를 분리합니다.
            # [O] 앞부분은 전부 지문 및 문제(Question Content)로 간주합니다.
            parts = re.split(r"(\[O\]|\[A\]|\[K\])", prob)
            
            q_content = ""
            o_content = ""
            a_content = "1"
            k_content = "미분류"
            
            for i in range(len(parts)):
                tag = parts[i]
                if i == 0: # 태그가 나오기 전 첫 부분은 문제 내용
                    q_content = tag.strip()
                elif tag == "[O]":
                    o_content = parts[i+1].strip()
                elif tag == "[A]":
                    a_content = parts[i+1].strip()
                elif tag == "[K]":
                    k_content = parts[i+1].strip()

            # 3. 보기(Options) 파싱 (①~⑤ 기호 기준)
            opts = re.findall(r'[①-⑤]\s*([^①-⑤\n\r]+)', o_content)
            if not opts:
                # 기호가 없으면 콤마 등으로 분리 시도
                opts = [o.strip() for o in o_content.split(',') if o.strip()]
            
            # 4. 정답 인덱스 변환
            ans_map = {'①':0, '②':1, '③':2, '④':3, '⑤':4, '1':0, '2':1, '3':2, '4':3, '5':4}
            ans_char = a_content[0] if a_content else "1"
            ans_idx = ans_map.get(ans_char, 0)
            
            parsed.append({
                "q": q_content.replace('**', '').strip(), 
                "o": [o.strip() for o in opts],
                "a": ans_idx, 
                "k": k_content
            })
        except Exception as e:
            continue
            
    return parsed

# --- 3. 기본 설정 변수 ---
APP_URL = "https://hoya-quiz-studio.streamlit.app"
ADMIN_PASSWORD = "1234"

# --- 4. 세션 관리 ---
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
    st.markdown(f"<div style='display: flex; justify-content: space-between; align-items: center; padding-bottom: 10px;'><h3 style='margin: 0;'>관리자 설정</h3><span style='font-size: 14px; color: #4CAF50;'>🟢 풀이중: {len(active_users)}명</span></div>", unsafe_allow_html=True)
    pw_input = st.text_input("PW", type="password", placeholder="Password", label_visibility="collapsed")
    
    if pw_input == ADMIN_PASSWORD:
        st.success("인증됨")
        weak_points = get_weak_points_from_gsheet()
        st.caption(f"📊 취약: {weak_points}")
        
        st.markdown("**⚙️ 퀴즈 룰 설정**")
        admin_settings['default_category'] = st.text_input("📌 기본 카테고리", value=admin_settings.get('default_category', ''))
        
        mode_options = ["⚡ 실시간 팩폭 (즉시 확인)", "🏁 최후의 심판 (마지막에 한 번에)"]
        selected_mode = st.selectbox("채점", mode_options, index=mode_options.index(admin_settings['feedback_mode']))
        admin_settings['feedback_mode'] = selected_mode
        admin_settings['allow_change'] = (selected_mode != mode_options[0])
        st.caption(f"{'🔒 수정 불가' if not admin_settings['allow_change'] else '🔓 수정 자유'}")
        
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
            cols = st.columns(2) # 표준 2열 방식 (모바일 1열 자동 전환)
            for j, q in enumerate(cat_quizzes):
                q_title = q['Title']
                label = f"🔥 {q_title}" if q_title == st.session_state.selected_quiz_title else q_title
                if cols[j % 2].button(label, use_container_width=True, key=f"btn_{cat}_{j}"):
                    st.session_state.selected_quiz_title = q_title
                    st.session_state.quiz_finished = False; st.session_state.start_time = None
                    st.session_state.user_answers = {}; st.rerun()

    if st.session_state.selected_quiz_title:
        selected_quiz_data = next((q for q in quiz_data_list if q['Title'] == st.session_state.selected_quiz_title), None)
        if selected_quiz_data:
            quiz_title = selected_quiz_data['Title']; quiz_content = robust_parse(selected_quiz_data['Content'])
            
            with st.expander("📊 순위표"):
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
                    if st.button("🏁 제출", use_container_width=True):
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
