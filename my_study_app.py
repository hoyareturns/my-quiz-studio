import streamlit as st
import re
import time
import pandas as pd
import os
import qrcode
from io import BytesIO
from collections import Counter

# --- 설정 및 파일 경로 ---
RESULTS_FILE = "quiz_results.csv"
WRONG_DATA_FILE = "wrong_answers.csv"
QUIZ_STORAGE_FILE = "last_quiz.txt"
APP_URL = "https://hoya-quiz-studio.streamlit.app"
ADMIN_PASSWORD = "1234"

# 브라우저 설정 (제목을 짧게 수정)
st.set_page_config(page_title="우정 파괴소", page_icon="🧪", layout="centered")

# --- 전역 상태 및 데이터 로드 ---
@st.cache_resource
def get_global_state():
    initial_quiz = []
    if os.path.exists(QUIZ_STORAGE_FILE):
        with open(QUIZ_STORAGE_FILE, "r", encoding="utf-8") as f:
            saved_text = f.read()
            if saved_text:
                initial_quiz = robust_parse(saved_text)
    return {"active_users": [], "quiz_version": time.time(), "current_quiz": initial_quiz}

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

global_state = get_global_state()

# --- 데이터 저장 로직 ---
def save_result_and_wrongs(user_id, score, duration, wrong_keywords):
    new_result = pd.DataFrame([[user_id, score, round(duration, 2), time.strftime('%H:%M:%S')]], 
                               columns=['아이디', '점수', '소요시간(초)', '완료시간'])
    new_result.to_csv(RESULTS_FILE, mode='a', header=not os.path.exists(RESULTS_FILE), index=False, encoding='utf-8-sig')
    if wrong_keywords:
        wrong_df = pd.DataFrame([{"아이디": user_id, "키워드": k, "일시": time.strftime('%Y-%m-%d %H:%M:%S')} for k in wrong_keywords])
        wrong_df.to_csv(WRONG_DATA_FILE, mode='a', header=not os.path.exists(WRONG_DATA_FILE), index=False, encoding='utf-8-sig')

def get_weak_points():
    if os.path.exists(WRONG_DATA_FILE):
        df = pd.read_csv(WRONG_DATA_FILE)
        counts = Counter(df['키워드'])
        common = counts.most_common(3)
        return ", ".join([f"{k}({c}회)" for k, c in common])
    return "데이터 없음"

# --- 세션 상태 ---
if 'user_id' not in st.session_state: st.session_state.user_id = ""
if 'local_quiz_version' not in st.session_state: st.session_state.local_quiz_version = 0
if 'start_time' not in st.session_state: st.session_state.start_time = None
if 'quiz_finished' not in st.session_state: st.session_state.quiz_finished = False

# --- UI 레이아웃 ---
st.title("🧪 우정 파괴소") # 제목 단축

with st.sidebar:
    st.header("🤳 스캔 후 입장")
    qr = qrcode.QRCode(version=1, box_size=10, border=4)
    qr.add_data(APP_URL); qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buf = BytesIO(); img.save(buf)
    st.image(buf.getvalue())
    
    st.divider()
    st.subheader("👑 관리자")
    pw_input = st.text_input("비밀번호", type="password")
    
    if pw_input == ADMIN_PASSWORD:
        weak_points = get_weak_points()
        st.warning(f"📊 취약: {weak_points}")
        prompt_to_copy = f"문서 바탕으로 5문제 출제. 취약주제({weak_points}) 참고.\n[Q]문제 [O]①.. [A]정답 [K]키워드"
        st.code(prompt_to_copy, language="text")
        
        st.divider()
        admin_text = st.text_area("📦 결과 붙여넣기", height=150)
        if st.button("🚀 퀴즈 배포", use_container_width=True):
            if admin_text:
                with open(QUIZ_STORAGE_FILE, "w", encoding="utf-8") as f:
                    f.write(admin_text)
                global_state['current_quiz'] = robust_parse(admin_text)
                global_state['quiz_version'] = time.time()
                global_state['active_users'] = []
                if os.path.exists(RESULTS_FILE): os.remove(RESULTS_FILE)
                st.success("배포 완료!")
                st.rerun()

# --- 메인 로직 (단순화) ---
# 새 퀴즈 배포 시 세션 초기화 자동 적용
if st.session_state.local_quiz_version != global_state['quiz_version']:
    st.session_state.local_quiz_version = global_state['quiz_version']
    st.session_state.quiz_finished = False
    st.session_state.start_time = None
    st.session_state.user_id = ""

if global_state['current_quiz']:
    if not st.session_state.user_id:
        st.subheader("👤 입장하기")
        u_id = st.text_input("이름(별명) 입력")
        if st.button("참여 시작", use_container_width=True):
            if u_id:
                st.session_state.user_id = u_id
                global_state['active_users'].append(u_id)
                st.rerun()
    
    elif not st.session_state.start_time and not st.session_state.quiz_finished:
        st.subheader(f"👋 {st.session_state.user_id}님!")
        if st.button("🚀 퀴즈 시작!", use_container_width=True):
            st.session_state.start_time = time.time()
            st.rerun()

    elif st.session_state.start_time and not st.session_state.quiz_finished:
        user_ans_list = []
        for i, item in enumerate(global_state['current_quiz']):
            st.markdown(f"**Q{i+1}. {item['q']}**")
            ans = st.radio(f"답안{i}", item['o'], key=f"ans_{i}", index=None, label_visibility="collapsed")
            user_ans_list.append(ans)
            st.divider()
        if st.button("🏁 제출하기", use_container_width=True):
            duration = time.time() - st.session_state.start_time
            wrong_ks = [global_state['current_quiz'][i]['k'] for i, ans in enumerate(user_ans_list) if ans != global_state['current_quiz'][i]['o'][global_state['current_quiz'][i]['a']]]
            save_result_and_wrongs(st.session_state.user_id, ((len(global_state['current_quiz'])-len(wrong_ks))/len(global_state['current_quiz']))*100, duration, wrong_ks)
            st.session_state.quiz_finished = True
            st.rerun()

    if st.session_state.quiz_finished:
        st.header("📊 순위표")
        if os.path.exists(RESULTS_FILE):
            st.dataframe(pd.read_csv(RESULTS_FILE).sort_values(by=['점수', '소요시간(초)'], ascending=[False, True]), use_container_width=True)
        if st.button("메인으로"):
            st.session_state.quiz_finished = False
            st.session_state.start_time = None
            st.session_state.user_id = ""
            st.rerun()
else:
    st.info("퀴즈 대기 중...")