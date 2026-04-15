import streamlit as st
import re
import time
import pandas as pd
import gspread
import json
import qrcode
from io import BytesIO
from collections import Counter

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

# --- 3. 데이터 처리 및 삭제 로직 ---
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
    if res_ws:
        return res_ws.get_all_records()
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
        except Exception:
            pass
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

# --- 2. 기본 설정 ---
APP_URL = "https://hoya-quiz-studio.streamlit.app"
ADMIN_PASSWORD = "1234"

st.set_page_config(page_title="우정 파괴소", page_icon="🧪", layout="centered")

# --- 4. 세션 및 접속자 상태 관리 ---
if 'player_name' not in st.session_state: st.session_state.player_name = ""
if 'start_time' not in st.session_state: st.session_state.start_time = None
if 'quiz_finished' not in st.session_state: st.session_state.quiz_finished = False
if 'user_answers' not in st.session_state: st.session_state.user_answers = {}
if 'selected_quiz_title' not in st.session_state: st.session_state.selected_quiz_title = ""

@st.cache_resource
def get_admin_settings():
    return {"feedback_mode": "⚡ 실시간 팩폭 (즉시 확인)", "allow_change": False}

@st.cache_resource
def get_active_users():
    return set()

admin_settings = get_admin_settings()
if "feedback_mode" not in admin_settings:
    admin_settings["feedback_mode"] = "⚡ 실시간 팩폭 (즉시 확인)"

active_users = get_active_users()

# --- 5. UI (사이드바) ---
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
        weak_points = get_weak_points_from_gsheet()
        st.caption(f"📊 취약: {weak_points}")
        
        full_prompt = f"""이 문서의 내용을 바탕으로 친구들과 풀 퀴즈 5문제를 만들어줘. 
특히 친구들이 자주 틀린 주제({weak_points})가 있다면 더 심도 있게 다뤄줘.
반드시 아래 형식을 엄격하게 지켜서 다른 설명 없이 텍스트만 출력해줘.

[Q] 문제 내용
[O] ①보기1 ②보기2 ③보기3 ④보기4 ⑤보기5
[A] 정답 기호(예: ②)
[K] 해당 문제의 핵심 키워드(오답 분석용)"""
        st.code(full_prompt, language="text")
        
        st.markdown("**⚙️ 퀴즈 룰 설정**")
        mode_options = ["⚡ 실시간 팩폭 (즉시 확인)", "🏁 최후의 심판 (마지막에 한 번에)"]
        current_mode = admin_settings.get('feedback_mode', mode_options[0])
        
        selected_mode = st.selectbox("채점 방식", mode_options, index=mode_options.index(current_mode) if current_mode in mode_options else 0, label_visibility="collapsed")
        admin_settings['feedback_mode'] = selected_mode
        
        if selected_mode == "⚡ 실시간 팩폭 (즉시 확인)":
            admin_settings['allow_change'] = False
            st.caption("🔒 **답안 수정 불가** (한 번 누르면 끝)")
        else:
            admin_settings['allow_change'] = True
            st.caption("🔓 **답안 수정 자유** (제출 전 딜레이 없음)")
        
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
                col1.caption(f"{q['Category']} - {q['Title']}")
                if col2.button("X", key=f"del_btn_{idx}"):
                    if delete_quiz_from_gsheet(q['Title']):
                        if st.session_state.selected_quiz_title == q['Title']:
                            st.session_state.selected_quiz_title = ""
                        st.rerun()
    
    st.divider()
    qr = qrcode.QRCode(version=1, box_size=3, border=2)
    qr.add_data(APP_URL); qr.make(fit=True)
    buf = BytesIO(); qr.make_image(fill_color="black", back_color="white").save(buf)
    st.image(buf.getvalue(), width=120)

# --- 6. 메인 영역 ---
st.title("🧪 우정 파괴소")

st.text_input("👤 참가자 이름", key="player_name", placeholder="이름을 한 번만 입력하면 계속 유지됩니다")
st.divider()

quiz_data_list = get_all_quizzes()

if not quiz_data_list:
    st.info("등록된 퀴즈가 없습니다.")
else:
    st.subheader("🎯 퀴즈 선택")
    
    categories = []
    for q in quiz_data_list:
        cat = q.get('Category', '미분류') or '미분류'
        if cat not in categories: categories.append(cat)
            
    tabs = st.tabs(categories)
    
    for i, cat in enumerate(categories):
        with tabs[i]:
            cat_quizzes = [q for q in quiz_data_list if (q.get('Category') or '미분류') == cat]
            cols = st.columns(2)
            for j, q in enumerate(cat_quizzes):
                q_title = q['Title']
                is_active = (q_title == st.session_state.selected_quiz_title)
                btn_label = f"🔥 {q_title}" if is_active else q_title
                
                if cols[j % 2].button(btn_label, use_container_width=True, key=f"btn_{cat}_{q_title}_{j}"):
                    st.session_state.selected_quiz_title = q_title
                    st.session_state.quiz_finished = False
                    st.session_state.start_time = None
                    if st.session_state.player_name in active_users:
                        active_users.discard(st.session_state.player_name)
                    st.session_state.user_answers = {}
                    st.rerun()

    if st.session_state.selected_quiz_title:
        selected_quiz_data = next((q for q in quiz_data_list if q['Title'] == st.session_state.selected_quiz_title), None)
        
        if selected_quiz_data:
            quiz_title = selected_quiz_data['Title']
            quiz_category = selected_quiz_data.get('Category', '미분류')
            quiz_content = robust_parse(selected_quiz_data['Content'])

            with st.expander(f"📊 [{quiz_category}] '{quiz_title}' 실시간 순위", expanded=False):
                if st.button("🔄 갱신", key="refresh_rank"):
                    get_all_results.clear()
                    st.rerun()
                
                all_res = get_all_results()
                quiz_res = [r for r in all_res if r.get('QuizTitle') == quiz_title]
                if quiz_res:
                    st.dataframe(pd.DataFrame(quiz_res).sort_values(by=['Score', 'Duration'], ascending=[False, True]), use_container_width=True)
                else:
                    st.caption("기록 없음")

            if not st.session_state.player_name:
                st.warning("👆 위에서 참가자 이름을 먼저 입력해야 퀴즈를 시작할 수 있습니다!")
            
            elif st.session_state.start_time is None and not st.session_state.quiz_finished:
                st.subheader(f"📍 '{quiz_title}' 도전 준비")
                if st.button("🚀 퀴즈 시작!", use_container_width=True):
                    st.session_state.start_time = time.time()
                    active_users.add(st.session_state.player_name)
                    st.rerun()
            
            elif st.session_state.start_time and not st.session_state.quiz_finished:
                st.subheader(f"🔥 {st.session_state.player_name}의 도전")
                
                # =======================================================
                # 📌 모드에 따라 로직(UI 렌더링 방식)을 완전히 분리합니다.
                # =======================================================
                current_mode = admin_settings.get('feedback_mode')
                
                if current_mode == "⚡ 실시간 팩폭 (즉시 확인)":
                    # [모드 1] 즉각 반응 (클릭 시 새로고침 발생)
                    for idx, item in enumerate(quiz_content):
                        st.markdown(f"**Q{idx+1}. {item['q']}**")
                        
                        is_answered = f"ans_{idx}" in st.session_state.user_answers
                        disabled = is_answered
                        
                        ans = st.radio(f"답안{idx}", item['o'], key=f"ans_{idx}", index=None, label_visibility="collapsed", disabled=disabled)
                        
                        if ans:
                            st.session_state.user_answers[f"ans_{idx}"] = ans
                            if ans == item['o'][item['a']]: st.success("⭕ 정답!")
                            else: st.error(f"❌ 오답! (정답: {item['o'][item['a']]})")
                        st.divider()
                    
                    if st.button("🏁 제출하기", use_container_width=True):
                        if len(st.session_state.user_answers) < len(quiz_content):
                            st.warning("모든 문제를 풀어야 합니다!")
                        else:
                            duration = time.time() - st.session_state.start_time
                            wrong_ks, review_data = [], []
                            for k_i, q in enumerate(quiz_content):
                                u_ans = st.session_state.user_answers.get(f"ans_{k_i}")
                                c_ans = q['o'][q['a']]
                                is_correct = (u_ans == c_ans)
                                if not is_correct: wrong_ks.append(q['k'])
                                review_data.append({"q": q['q'], "u_ans": u_ans, "c_ans": c_ans, "is_correct": is_correct})
                                
                            score = ((len(quiz_content)-len(wrong_ks))/len(quiz_content))*100
                            save_result_to_gsheet(quiz_title, st.session_state.player_name, score, duration, wrong_ks)
                            
                            st.session_state.quiz_finished = True
                            st.session_state.last_score = score
                            st.session_state.review_data = review_data
                            
                            if st.session_state.player_name in active_users:
                                active_users.discard(st.session_state.player_name)
                            st.rerun()

                else:
                    # [모드 2] 최후의 심판 (Form 적용 - 클릭 시 새로고침 방지)
                    with st.form(key="quiz_form"):
                        for idx, item in enumerate(quiz_content):
                            st.markdown(f"**Q{idx+1}. {item['q']}**")
                            # form 내부이므로 아무리 눌러도 화면이 깜빡이지 않습니다.
                            st.radio(f"답안{idx}", item['o'], key=f"ans_form_{idx}", index=None, label_visibility="collapsed")
                            st.divider()
                        
                        # 폼의 제출 버튼
                        submitted = st.form_submit_button("🏁 모든 답안 제출하기", use_container_width=True)
                        
                        if submitted:
                            # 폼 안의 값들은 제출 시점에만 session_state에 등록됩니다.
                            if any(st.session_state.get(f"ans_form_{i}") is None for i in range(len(quiz_content))):
                                st.warning("모든 문제를 풀어야 제출할 수 있습니다!")
                            else:
                                duration = time.time() - st.session_state.start_time
                                wrong_ks, review_data = [], []
                                for k_i, q in enumerate(quiz_content):
                                    u_ans = st.session_state.get(f"ans_form_{k_i}")
                                    c_ans = q['o'][q['a']]
                                    is_correct = (u_ans == c_ans)
                                    if not is_correct: wrong_ks.append(q['k'])
                                    review_data.append({"q": q['q'], "u_ans": u_ans, "c_ans": c_ans, "is_correct": is_correct})
                                    
                                score = ((len(quiz_content)-len(wrong_ks))/len(quiz_content))*100
                                save_result_to_gsheet(quiz_title, st.session_state.player_name, score, duration, wrong_ks)
                                
                                st.session_state.quiz_finished = True
                                st.session_state.last_score = score
                                st.session_state.review_data = review_data
                                
                                if st.session_state.player_name in active_users:
                                    active_users.discard(st.session_state.player_name)
                                st.rerun()

            # 📌 퀴즈 종료 화면
            if st.session_state.quiz_finished:
                st.balloons()
                st.success(f"🎉 제출 완료! 당신의 점수는 **{int(st.session_state.last_score)}점** 입니다.")
                
                if admin_settings.get('feedback_mode') == "🏁 최후의 심판 (마지막에 한 번에)":
                    with st.expander("📝 내 답안지 채점 결과 보기", expanded=True):
                        for i, r in enumerate(st.session_state.review_data):
                            st.markdown(f"**Q{i+1}. {r['q']}**")
                            if r['is_correct']:
                                st.info(f"⭕ 내 답: {r['u_ans']} (정답)")
                            else:
                                st.error(f"❌ 내 답: {r['u_ans']} / **진짜 정답: {r['c_ans']}**")
                            st.divider()

                if st.button("다른 퀴즈 하러 가기"):
                    st.session_state.quiz_finished = False
                    st.session_state.start_time = None
                    st.session_state.user_answers = {}
                    st.rerun()
