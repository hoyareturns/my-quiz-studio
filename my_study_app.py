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

st.set_page_config(page_title="우정 파괴소", page_icon="🧪", layout="centered")

# --- 전역 상태 관리 (실시간 설정 포함) ---
@st.cache_resource
def get_global_state():
    initial_quiz = []
    if os.path.exists(QUIZ_STORAGE_FILE):
        with open(QUIZ_STORAGE_FILE, "r", encoding="utf-8") as f:
            saved_text = f.read()
            if saved_text:
                initial_quiz = robust_parse(saved_text)
    return {
        "active_users": [], 
        "quiz_version": time.time(), 
        "current_quiz": initial_quiz,
        "instant_feedback": True,  # 정답 즉시 확인 여부
        "allow_change": False      # 답안 수정 허용 여부
    }

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

# --- 데이터 저장 및 불러오기 ---
def save_result(user_id, score, duration, wrong_keywords):
    new_result = pd.DataFrame([[user_id, score, round(duration, 2), time.strftime('%H:%M:%S')]], 
                               columns=['아이디', '점수', '소요시간(초)', '완료시간'])
    new_result.to_csv(RESULTS_FILE, mode='a', header=not os.path.exists(RESULTS_FILE), index=False, encoding='utf-8-sig')
    if wrong_keywords:
        wrong_df = pd.DataFrame([{"아이디": user_id, "키워드": k, "일시": time.strftime('%Y-%m-%d %H:%M:%S')} for k in wrong_keywords])
        wrong_df.to_csv(WRONG_DATA_FILE, mode='a', header=not os.path.exists(WRONG_DATA_FILE), index=False, encoding='utf-8-sig')

def get_weak_points():
    if os.path.exists(WRONG_DATA_FILE):
        df = pd.read_csv(WRONG_DATA_FILE)
        return ", ".join([f"{k}({c}회)" for k, c in Counter(df['키워드']).most_common(3)])
    return "데이터 없음"

# --- 세션 관리 ---
if 'user_id' not in st.session_state: st.session_state.user_id = ""
if 'local_quiz_version' not in st.session_state: st.session_state.local_quiz_version = 0
if 'start_time' not in st.session_state: st.session_state.start_time = None
if 'quiz_finished' not in st.session_state: st.session_state.quiz_finished = False
if 'user_answers' not in st.session_state: st.session_state.user_answers = {}

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
        weak_points = get_weak_points()
        st.warning(f"📊 취약: {weak_points}")
        
        # 1. 프롬프트 전체 문장 제공 (요약 없음)
        full_prompt = f"""지금까지 내가 공부하고 질문한 내용을 바탕으로 가장 중요하고 자주 헷갈리는 개념 5문제를 출제해줘. 
특히 사람들이 자주 틀린 주제({weak_points})가 있다면 더 심도 있게 다뤄줘.
반드시 아래 형식을 엄격하게 지켜서 다른 설명 없이 텍스트만 출력해줘.

[Q] 문제 내용
[O] ①보기1 ②보기2 ③보기3 ④보기4 ⑤보기5
[A] 정답 기호(예: ②)
[K] 해당 문제의 핵심 키워드(오답 분석용)"""
        st.code(full_prompt, language="text")
        
        # 2. 실시간 룰 제어
        st.divider()
        global_state['instant_feedback'] = st.toggle("정답 즉시 확인", value=global_state['instant_feedback'])
        global_state['allow_change'] = st.toggle("답안 수정 허용", value=global_state['allow_change'])
        
        st.divider()
        admin_text = st.text_area("📦 NotebookLM 결과물 붙여넣기", height=150)
        if st.button("🚀 퀴즈 배포", use_container_width=True):
            if admin_text:
                with open(QUIZ_STORAGE_FILE, "w", encoding="utf-8") as f: f.write(admin_text)
                global_state['current_quiz'] = robust_parse(admin_text)
                global_state['quiz_version'] = time.time()
                if os.path.exists(RESULTS_FILE): os.remove(RESULTS_FILE)
                st.success("배포 완료!"); st.rerun()

# --- 메인 로직 ---
# 버전 체크 및 초기화
if st.session_state.local_quiz_version != global_state['quiz_version']:
    st.session_state.local_quiz_version = global_state['quiz_version']
    st.session_state.quiz_finished = False; st.session_state.start_time = None
    st.session_state.user_id = ""; st.session_state.user_answers = {}

# 순위표 상시 확인 (문제 풀기 전/후 모두)
with st.expander("📊 실시간 순위표 확인 (클릭)", expanded=False):
    if st.button("🔄 순위 갱신"): st.rerun()
    if os.path.exists(RESULTS_FILE):
        st.dataframe(pd.read_csv(RESULTS_FILE).sort_values(by=['점수', '소요시간(초)'], ascending=[False, True]), use_container_width=True)
    else:
        st.info("아직 완료된 기록이 없습니다.")

if global_state['current_quiz']:
    # 1. 입장 및 참여 (참여 즉시 퀴즈 시작)
    if not st.session_state.user_id:
        st.subheader("👤 본인 확인")
        u_id = st.text_input("이름(별명) 입력")
        if st.button("참여 및 퀴즈 시작 🚀", use_container_width=True):
            if u_id:
                st.session_state.user_id = u_id
                st.session_state.start_time = time.time() # 참여 즉시 시작 시간 기록
                st.rerun()
    
    # 2. 퀴즈 진행 섹션
    elif st.session_state.start_time and not st.session_state.quiz_finished:
        st.subheader(f"🔥 {st.session_state.user_id}의 서바이벌")
        
        for i, item in enumerate(global_state['current_quiz']):
            st.markdown(f"**Q{i+1}. {item['q']}**")
            
            # 답안 수정 허용 여부에 따른 비활성화 처리
            is_answered = f"ans_{i}" in st.session_state.user_answers
            disabled = is_answered and not global_state['allow_change']
            
            ans = st.radio(f"답안{i}", item['o'], key=f"ans_{i}", index=None, 
                           label_visibility="collapsed", disabled=disabled)
            
            if ans:
                st.session_state.user_answers[f"ans_{i}"] = ans
                # 즉시 확인 모드일 때
                if global_state['instant_feedback']:
                    if ans == item['o'][item['a']]:
                        st.success("⭕ 정답!")
                    else:
                        st.error(f"❌ 오답! (정답: {item['o'][item['a']]})")
            st.divider()
            
        if st.button("🏁 모든 문제 제출 및 종료", use_container_width=True):
            if len(st.session_state.user_answers) < len(global_state['current_quiz']):
                st.warning("모든 문제를 풀어야 제출할 수 있습니다!")
            else:
                duration = time.time() - st.session_state.start_time
                wrong_ks = [q['k'] for i, q in enumerate(global_state['current_quiz']) 
                            if st.session_state.user_answers.get(f"ans_{i}") != q['o'][q['a']]]
                score = ((len(global_state['current_quiz'])-len(wrong_ks))/len(global_state['current_quiz']))*100
                save_result(st.session_state.user_id, score, duration, wrong_ks)
                st.session_state.quiz_finished = True; st.rerun()

    # 3. 결과 화면
    if st.session_state.quiz_finished:
        st.balloons()
        st.success(f"축하합니다! 모든 문제를 제출했습니다. 위 순위표에서 결과를 확인하세요!")
        if st.button("다시 처음으로"):
            st.session_state.quiz_finished = False; st.session_state.start_time = None
            st.session_state.user_id = ""; st.session_state.user_answers = {}; st.rerun()
else:
    st.info("실험체가 대기 중입니다. 출제자가 문제를 배포할 때까지 기다리세요.")
