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
APP_URL = "https://hoya-quiz-studio.streamlit.app"
ADMIN_PASSWORD = "1234"

# 브라우저 설정
st.set_page_config(page_title="우정 파괴 연구소", page_icon="🧪", layout="centered")

# --- 전역 상태 공유 시스템 ---
@st.cache_resource
def get_global_state():
    return {"active_users": [], "quiz_version": 0, "current_quiz": []}

global_state = get_global_state()

# --- 결과 및 오답 저장 로직 ---
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
        return ", ".join([f"{k}({c}번 탈탈 털림)" for k, c in common])
    return "아직은 모두가 지성인인 척하는 중"

# --- 세션 상태 관리 ---
if 'user_id' not in st.session_state: st.session_state.user_id = ""
if 'local_quiz_version' not in st.session_state: st.session_state.local_quiz_version = 0
if 'start_time' not in st.session_state: st.session_state.start_time = None
if 'quiz_finished' not in st.session_state: st.session_state.quiz_finished = False

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
                       "a": ans_map.get(ans_char, 0), "k": ks[i] if i < len(ks) else "미분류"})
    return parsed

# --- UI 레이아웃 ---
st.title("🧪 우정 파괴 연구소")
st.caption("진정한 친구라면... 이 정도 문제는 맞춰야지?")

with st.sidebar:
    st.header("🤳 빨리 찍고 들어와")
    qr = qrcode.QRCode(version=1, box_size=10, border=4)
    qr.add_data(APP_URL); qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buf = BytesIO(); img.save(buf)
    st.image(buf.getvalue(), caption="스캔해서 입장!")
    
    st.divider()
    st.subheader(f"👥 현재 감시 중: {len(global_state['active_users'])}명")
    if global_state['active_users']:
        st.caption(", ".join(global_state['active_users']))
    
    st.divider()
    st.subheader("👑 출제자(신)의 영역")
    pw_input = st.text_input("비밀번호를 대라", type="password")
    
    if pw_input == ADMIN_PASSWORD:
        weak_points = get_weak_points()
        st.warning(f"📊 실시간 굴욕 데이터: {weak_points}")
        
        # 1. NotebookLM용 프롬프트 복사 영역
        st.write("📋 **NotebookLM용 명령서**")
        prompt_to_copy = f"""이 문서의 내용을 바탕으로 친구들과 풀 퀴즈 5문제를 만들어줘. 
사람들이 자주 틀린 주제({weak_points})가 있다면 참고해줘.
반드시 아래 형식을 엄격하게 지키고, 다른 설명 없이 텍스트만 출력해줘.

[Q] 문제 내용
[O] ①보기1 ②보기2 ③보기3 ④보기4 ⑤보기5
[A] 정답 기호(예: ②)
[K] 해당 문제의 핵심 키워드(오답 분석용)"""
        
        st.code(prompt_to_copy, language="text") # 클릭하면 자동 복사됨
        st.caption("위 박스 오른쪽 버튼을 눌러 복사한 뒤 NotebookLM에 붙여넣으세요.")
        
        # 2. 퀴즈 데이터 입력창 (입력 후 배포 버튼)
        st.divider()
        admin_text = st.text_area("📦 NotebookLM 결과물 붙여넣기", height=200, placeholder="[Q] 문제1...")
        
        if st.button("🚀 오답 폭격 배포", use_container_width=True):
            if admin_text:
                global_state['current_quiz'] = robust_parse(admin_text)
                global_state['quiz_version'] = time.time()
                global_state['active_users'] = []
                st.success("지옥의 퀴즈가 전송되었습니다.")
                time.sleep(1) # 성공 메시지 보여줄 시간
                st.rerun()
            else:
                st.error("데이터를 입력해야 배포하지!")
    elif pw_input:
        st.error("비번도 모르면서 어딜 들어와?")

# --- 메인 퀴즈 로직 (이전과 동일) ---
if st.session_state.local_quiz_version != global_state['quiz_version']:
    st.info("🔔 새로운 우정 파괴 문제가 도착했습니다!")
    if st.button("살아남으러 가기"):
        st.session_state.local_quiz_version = global_state['quiz_version']
        st.session_state.quiz_finished = False; st.session_state.start_time = None
        st.session_state.user_id = ""; st.rerun()

if global_state['current_quiz']:
    if not st.session_state.user_id:
        st.subheader("👤 본인 확인")
        u_id = st.text_input("이름(또는 별명)을 적어라")
        if st.button("입장하기"):
            if u_id:
                st.session_state.user_id = u_id
                global_state['active_users'].append(u_id); st.rerun()
    
    elif st.session_state.start_time and not st.session_state.quiz_finished:
        user_ans_list = []
        for i, item in enumerate(global_state['current_quiz']):
            st.markdown(f"#### Q{i+1}. {item['q']}")
            ans = st.radio(f"답안{i}", item['o'], key=f"ans_{i}", index=None, label_visibility="collapsed")
            user_ans_list.append(ans)
            st.divider()
        
        if st.button("🏁 제출하고 심판받기", use_container_width=True):
            duration = time.time() - st.session_state.start_time
            wrong_ks = [global_state['current_quiz'][i]['k'] for i, ans in enumerate(user_ans_list) if ans != global_state['current_quiz'][i]['o'][global_state['current_quiz'][i]['a']]]
            correct_count = len(global_state['current_quiz']) - len(wrong_ks)
            
            save_result_and_wrongs(st.session_state.user_id, (correct_count/len(global_state['current_quiz']))*100, duration, wrong_ks)
            if st.session_state.user_id in global_state['active_users']: global_state['active_users'].remove(st.session_state.user_id)
            st.session_state.quiz_finished = True; st.rerun()
    
    elif not st.session_state.quiz_finished:
        st.subheader(f"👋 {st.session_state.user_id}, 준비됐나?")
        if st.button("🚀 전쟁 시작!", use_container_width=True):
            st.session_state.start_time = time.time(); st.rerun()

    if st.session_state.quiz_finished:
        st.header("📊 명예의 전당")
        if os.path.exists(RESULTS_FILE):
            df = pd.read_csv(RESULTS_FILE)
            st.dataframe(df.sort_values(by=['점수', '소요시간(초)'], ascending=[False, True]), use_container_width=True)
        if st.button("다시 도전?"):
            st.session_state.quiz_finished = False; st.session_state.start_time = None; st.rerun()