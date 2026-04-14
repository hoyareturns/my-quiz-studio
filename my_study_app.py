import streamlit as st
import re
import socket
import time
import pandas as pd
import os
import qrcode
from io import BytesIO

# --- 설정 및 파일 경로 ---
RESULTS_FILE = "quiz_results.csv"
DEFAULT_PROMPT = """지금까지 내가 공부하고 질문한 내용을 바탕으로 가장 중요하고 자주 헷갈리는 개념 5문제를 출제해줘. 반드시 아래 형식을 엄격하게 지켜서 다른 설명 없이 텍스트만 출력해줘.

[Q] 문제 내용
[O] ①보기1 ②보기2 ③보기3 ④보기4 ⑤보기5
[A] 정답 기호(예: ②)
[K] 해당 문제의 핵심 키워드(오답 분석용)"""

def get_network_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(('8.8.8.8', 1))
        ip = s.getsockname()[0]
    except: ip = "127.0.0.1"
    finally: s.close()
    return ip

st.set_page_config(page_title="부서 퀴즈 스튜디오", layout="centered")

# --- 전역 상태 공유 시스템 ---
@st.cache_resource
def get_global_state():
    return {"active_users": [], "quiz_version": 0, "current_quiz": []}

global_state = get_global_state()

# --- 세션 상태 관리 ---
if 'user_id' not in st.session_state: st.session_state.user_id = ""
if 'local_quiz_version' not in st.session_state: st.session_state.local_quiz_version = 0
if 'start_time' not in st.session_state: st.session_state.start_time = None
if 'quiz_finished' not in st.session_state: st.session_state.quiz_finished = False

# --- 결과 저장 로직 ---
def save_result(user_id, score, duration):
    new_data = pd.DataFrame([[user_id, score, round(duration, 2), time.strftime('%H:%M:%S')]], 
                            columns=['아이디', '점수', '소요시간(초)', '완료시간'])
    new_data.to_csv(RESULTS_FILE, mode='a', header=not os.path.exists(RESULTS_FILE), index=False, encoding='utf-8-sig')

def get_leaderboard():
    if os.path.isfile(RESULTS_FILE):
        df = pd.read_csv(RESULTS_FILE)
        return df.sort_values(by=['점수', '소요시간(초)'], ascending=[False, True]).reset_index(drop=True)
    return None

def robust_parse(text):
    qs = re.findall(r"\[Q\d?\]\s*(.*)", text)
    os_raw = re.findall(r"\[O\]\s*(.*)", text)
    as_raw = re.findall(r"\[A\]\s*(.*)", text)
    ks = re.findall(r"\[K\]\s*(.*)", text)
    parsed = []
    ans_map = {'①':0, '②':1, '③':2, '④':3, '⑤':4, '1':0, '2':1, '3':2, '4':3, '5':4}
    for i in range(len(qs)):
        opts = re.findall(r'[①-⑤]\s*([^①-⑤]+)', os_raw[i])
        if not opts: opts = [o.strip() for o in os_raw[i].split(',') if o.strip()]
        ans_char = as_raw[i].strip()[0] if as_raw[i] else "1"
        parsed.append({"q": qs[i].replace('**', '').strip(), "o": [o.strip() for o in opts],
                       "a": ans_map.get(ans_char, 0), "k": ks[i] if i < len(ks) else "핵심개념"})
    return parsed

# --- UI 레이아웃 ---
st.title("🏆 부서 실시간 퀴즈 스튜디오")

# 네트워크 정보 및 QR 코드 생성
net_ip = get_network_ip()
app_url = f"http://{net_ip}:8501"

# --- 사이드바: 관리자 설정 및 QR 코드 ---
with st.sidebar:
    st.header("📸 간편 접속 QR")
    # QR 코드 생성 및 표시
    qr = qrcode.QRCode(version=1, box_size=10, border=4)
    qr.add_data(app_url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    
    buf = BytesIO()
    img.save(buf)
    st.image(buf.getvalue(), caption="카메라로 스캔하세요!")
    st.code(app_url) # 복사용 주소
    
    st.divider()
    st.subheader(f"👥 접속 중: {len(global_state['active_users'])}명")
    if global_state['active_users']:
        st.caption(", ".join(global_state['active_users']))
    
    st.divider()
    admin_text = st.text_area("퀴즈 데이터 등록", value=DEFAULT_PROMPT, height=200)
    if st.button("🚀 새 퀴즈 배포", use_container_width=True):
        global_state['current_quiz'] = robust_parse(admin_text)
        global_state['quiz_version'] = time.time()
        global_state['active_users'] = []
        if os.path.exists(RESULTS_FILE): os.remove(RESULTS_FILE)
        st.rerun()

# --- 메인 로직 (이전과 동일) ---
if st.session_state.local_quiz_version != global_state['quiz_version']:
    st.warning("🔔 새로운 퀴즈가 도착했습니다!")
    if st.button("새 문제 불러오기"):
        st.session_state.local_quiz_version = global_state['quiz_version']
        st.session_state.quiz_finished = False
        st.session_state.start_time = None
        st.session_state.user_id = ""
        st.rerun()

if not global_state['current_quiz']:
    st.info("관리자가 퀴즈를 배포할 때까지 대기 중입니다...")
else:
    if not st.session_state.user_id:
        st.subheader("👤 입장하기")
        u_id = st.text_input("아이디(이름)를 입력하세요")
        if st.button("참여 시작"):
            if u_id:
                if u_id not in global_state['active_users']: global_state['active_users'].append(u_id)
                st.session_state.user_id = u_id
                st.session_state.local_quiz_version = global_state['quiz_version']
                st.rerun()
    
    elif not st.session_state.start_time and not st.session_state.quiz_finished:
        my_pos = global_state['active_users'].index(st.session_state.user_id) + 1 if st.session_state.user_id in global_state['active_users'] else "?"
        st.subheader(f"👋 반갑습니다, {st.session_state.user_id}님!")
        st.info(f"📍 전체 {len(global_state['active_users'])}명 중 {my_pos}번째로 입장")
        if st.button("🚀 퀴즈 시작!", use_container_width=True):
            st.session_state.start_time = time.time()
            st.rerun()

    elif st.session_state.start_time and not st.session_state.quiz_finished:
        user_ans_list = []
        for i, item in enumerate(global_state['current_quiz']):
            st.markdown(f"**Q{i+1}. {item['q']}**")
            ans = st.radio(f"답안 {i}", item['o'], key=f"ans_{i}", index=None, label_visibility="collapsed")
            user_ans_list.append(ans)
        
        if st.button("🏁 제출 및 종료", use_container_width=True):
            duration = time.time() - st.session_state.start_time
            correct = sum(1 for i, item in enumerate(global_state['current_quiz']) if user_ans_list[i] == item['o'][item['a']])
            save_result(st.session_state.user_id, (correct/len(global_state['current_quiz']))*100, duration)
            if st.session_state.user_id in global_state['active_users']: global_state['active_users'].remove(st.session_state.user_id)
            st.session_state.quiz_finished = True
            st.rerun()

    elif st.session_state.quiz_finished:
        st.header("📊 실시간 순위표")
        leaderboard = get_leaderboard()
        if leaderboard is not None: st.table(leaderboard)
        if st.button("새로고침"): st.rerun()