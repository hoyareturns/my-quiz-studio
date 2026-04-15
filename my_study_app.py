import streamlit as st
import re
import time
import pandas as pd
import gspread
import json
import qrcode
from io import BytesIO
from collections import Counter

# --- 구글 시트 연동 설정 ---
def get_gspread_client():
    # Streamlit Secrets에서 JSON 키와 시트 ID를 가져옴
    credentials = json.loads(st.secrets["GCP_JSON"])
    gc = gspread.service_account_from_dict(credentials)
    return gc.open_by_key(st.secrets["SHEET_ID"])

def get_worksheet(sheet_name, columns):
    try:
        sh = get_gspread_client()
        try:
            ws = sh.worksheet(sheet_name)
        except gspread.exceptions.WorksheetNotFound:
            # 시트가 없으면 생성하고 헤더 추가
            ws = sh.add_worksheet(title=sheet_name, rows="100", cols=len(columns))
            ws.append_row(columns)
        return ws
    except Exception as e:
        st.error(f"구글 시트 연결 오류: {e}")
        return None

# --- 설정 및 경로 ---
APP_URL = "https://hoya-quiz-studio.streamlit.app"
ADMIN_PASSWORD = "1234"

st.set_page_config(page_title="우정 파괴소", page_icon="🧪", layout="centered")

# --- 데이터 처리 로직 (구글 시트 기반) ---

# 1. 퀴즈 목록 및 내용 불러오기
def get_all_quizzes():
    ws = get_worksheet("Quizzes", ["Title", "Content", "CreatedAt"])
    if ws:
        data = ws.get_all_records()
        # 최신순 정렬
        return sorted(data, key=lambda x: x['CreatedAt'], reverse=True)
    return []

# 2. 결과 저장
def save_result_to_gsheet(quiz_title, user_id, score, duration, wrong_keywords):
    # 결과 저장
    res_ws = get_worksheet("Results", ["QuizTitle", "User", "Score", "Duration", "Time"])
    if res_ws:
        res_ws.append_row([quiz_title, user_id, score, round(duration, 2), time.strftime('%Y-%m-%d %H:%M:%S')])
    
    # 오답 키워드 저장
    if wrong_keywords:
        wrong_ws = get_worksheet("WrongAnswers", ["User", "Keyword", "Time"])
        if wrong_ws:
            for k in wrong_keywords:
                wrong_ws.append_row([user_id, k, time.strftime('%Y-%m-%d %H:%M:%S')])

# 3. 실시간 취약점 분석
def get_weak_points_from_gsheet():
    ws = get_worksheet("WrongAnswers", ["User", "Keyword", "Time"])
    if ws:
        data = ws.get_all_records()
        if data:
            counts = Counter([d['Keyword'] for d in data])
            return ", ".join([f"{k}({c}회)" for k, c in counts.most_common(3)])
    return "데이터 없음"

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

# --- 세션 상태 ---
if 'user_id' not in st.session_state: st.session_state.user_id = ""
if 'start_time' not in st.session_state: st.session_state.start_time = None
if 'quiz_finished' not in st.session_state: st.session_state.quiz_finished = False
if 'user_answers' not in st.session_state: st.session_state.user_answers = {}
if 'selected_quiz_title' not in st.session_state: st.session_state.selected_quiz_title = ""

# --- UI 레이아웃 ---
st.title("🧪 우정 파괴소")

with st.sidebar:
    st.header("🤳 스캔 후 입장")
    qr = qrcode.QRCode(version=1, box_size=10, border=4)
    qr.add_data(APP_URL); qr.make(fit=True)
    buf = BytesIO(); qr.make_image(fill_color="black", back_color="white").save(buf)
    st.image(buf.getvalue())
    
    st.divider()
    st.subheader("👑 관리자 설정")
    pw_input = st.text_input("비밀번호", type="password")
    
    if pw_input == ADMIN_PASSWORD:
        st.success("관리자 인증됨")
        weak_points = get_weak_points_from_gsheet()
        st.warning(f"📊 취약: {weak_points}")
        
        full_prompt = f"""이 문서의 내용을 바탕으로 친구들과 풀 퀴즈 5문제를 만들어줘. 
특히 친구들이 자주 틀린 주제({weak_points})가 있다면 더 심도 있게 다뤄줘.
반드시 아래 형식을 엄격하게 지켜서 다른 설명 없이 텍스트만 출력해줘.

[Q] 문제 내용
[O] ①보기1 ②보기2 ③보기3 ④보기4 ⑤보기5
[A] 정답 기호(예: ②)
[K] 해당 문제의 핵심 키워드(오답 분석용)"""
        st.code(full_prompt, language="text")
        
        with st.expander("🆕 새 퀴즈 만들기", expanded=False):
            new_title = st.text_input("퀴즈 제목")
            admin_text = st.text_area("NotebookLM 결과물 붙여넣기", height=150)
            if st.button("🚀 신규 배포", use_container_width=True):
                if new_title and admin_text:
                    ws = get_worksheet("Quizzes", ["Title", "Content", "CreatedAt"])
                    ws.append_row([new_title, admin_text, time.strftime('%Y-%m-%d %H:%M:%S')])
                    st.success(f"'{new_title}' 배포 완료!"); st.rerun()

# --- 메인 영역 ---
quiz_data_list = get_all_quizzes()

if not quiz_data_list:
    st.info("현재 등록된 퀴즈가 없습니다. 관리자가 먼저 문제를 배포해주세요.")
else:
    st.subheader("🎯 퀴즈 선택")
    
    # 퀴즈 선택 버튼들 (최신 퀴즈는 🔥 표시)
    cols = st.columns(2)
    for i, q in enumerate(quiz_data_list):
        q_title = q['Title']
        is_active = (q_title == st.session_state.selected_quiz_title)
        btn_label = f"🔥 {q_title}" if is_active else q_title
        
        if cols[i % 2].button(btn_label, use_container_width=True, key=f"btn_{q_title}"):
            st.session_state.selected_quiz_title = q_title
            st.session_state.quiz_finished = False
            st.session_state.start_time = None
            st.session_state.user_id = ""
            st.session_state.user_answers = {}
            st.rerun()

    if st.session_state.selected_quiz_title:
        selected_quiz_data = next(q for q in quiz_data_list if q['Title'] == st.session_state.selected_quiz_title)
        quiz_title = selected_quiz_data['Title']
        quiz_content = robust_parse(selected_quiz_data['Content'])

        # 순위표
        with st.expander(f"📊 '{quiz_title}' 실시간 순위", expanded=False):
            res_ws = get_worksheet("Results", ["QuizTitle", "User", "Score", "Duration", "Time"])
            if res_ws:
                all_res = res_ws.get_all_records()
                quiz_res = [r for r in all_res if r['QuizTitle'] == quiz_title]
                if quiz_res:
                    st.table(pd.DataFrame(quiz_res).sort_values(by=['Score', 'Duration'], ascending=[False, True]))
                else:
                    st.caption("기록 없음")

        # 퀴즈 풀기
        if not st.session_state.user_id:
            st.divider()
            u_id = st.text_input(f"[{quiz_title}] 참여할 이름을 입력하세요")
            if st.button("참여 및 바로 시작 🚀", use_container_width=True):
                if u_id:
                    st.session_state.user_id = u_id
                    st.session_state.start_time = time.time(); st.rerun()
        
        elif st.session_state.start_time and not st.session_state.quiz_finished:
            st.subheader(f"🔥 {st.session_state.user_id}의 도전")
            for i, item in enumerate(quiz_content):
                st.markdown(f"**Q{i+1}. {item['q']}**")
                ans = st.radio(f"답안{i}", item['o'], key=f"ans_{i}", index=None, label_visibility="collapsed")
                if ans: st.session_state.user_answers[f"ans_{i}"] = ans
                st.divider()
            
            if st.button("🏁 제출하기", use_container_width=True):
                if len(st.session_state.user_answers) < len(quiz_content):
                    st.warning("모든 문제를 풀어야 합니다!")
                else:
                    duration = time.time() - st.session_state.start_time
                    wrong_ks = [q['k'] for i, q in enumerate(quiz_content) if st.session_state.user_answers.get(f"ans_{i}") != q['o'][q['a']]]
                    score = ((len(quiz_content)-len(wrong_ks))/len(quiz_content))*100
                    save_result_to_gsheet(quiz_title, st.session_state.user_id, score, duration, wrong_ks)
                    st.session_state.quiz_finished = True; st.rerun()

        if st.session_state.quiz_finished:
            st.balloons()
            st.success("제출 완료! 상단 순위표를 확인하세요.")
            if st.button("다른 퀴즈 하러 가기"):
                st.session_state.quiz_finished = False; st.session_state.start_time = None
                st.session_state.user_id = ""; st.session_state.user_answers = {}; st.rerun()
