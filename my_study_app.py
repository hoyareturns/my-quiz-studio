import streamlit as st
import re
import time
import pandas as pd
import os
import qrcode
from io import BytesIO
from collections import Counter

# --- 설정 및 디렉토리 관리 ---
QUIZ_DIR = "quizzes"
RESULTS_DIR = "results"
WRONG_DATA_FILE = "wrong_answers.csv"
QUIZ_STORAGE_FILE = "last_quiz.txt"
APP_URL = "https://hoya-quiz-studio.streamlit.app"
ADMIN_PASSWORD = "1234"

for directory in [QUIZ_DIR, RESULTS_DIR]:
    if not os.path.exists(directory):
        os.makedirs(directory)

st.set_page_config(page_title="우정 파괴소", page_icon="🧪", layout="centered")

# --- 유틸리티 및 전역 상태 ---
@st.cache_resource
def get_global_state():
    return {
        "active_users": [], 
        "quiz_version": time.time(), 
        "instant_feedback": True, 
        "allow_change": False      
    }

global_state = get_global_state()

def get_quiz_list():
    files = [f for f in os.listdir(QUIZ_DIR) if f.endswith(".txt")]
    # 최신 파일이 먼저 오도록 정렬 (옵션)
    files.sort(key=lambda x: os.path.getmtime(os.path.join(QUIZ_DIR, x)), reverse=True)
    return [f.replace(".txt", "") for f in files]

def load_quiz_content(quiz_title):
    path = os.path.join(QUIZ_DIR, f"{quiz_title}.txt")
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    return ""

def delete_quiz(quiz_title):
    quiz_path = os.path.join(QUIZ_DIR, f"{quiz_title}.txt")
    result_path = os.path.join(RESULTS_DIR, f"results_{quiz_title}.csv")
    if os.path.exists(quiz_path): os.remove(quiz_path)
    if os.path.exists(result_path): os.remove(result_path)

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

def get_weak_points():
    if os.path.exists(WRONG_DATA_FILE):
        df = pd.read_csv(WRONG_DATA_FILE)
        return ", ".join([f"{k}({c}회)" for k, c in Counter(df['키워드']).most_common(3)])
    return "데이터 없음"

# --- 세션 관리 ---
if 'user_id' not in st.session_state: st.session_state.user_id = ""
if 'start_time' not in st.session_state: st.session_state.start_time = None
if 'quiz_finished' not in st.session_state: st.session_state.quiz_finished = False
if 'user_answers' not in st.session_state: st.session_state.user_answers = {}
if 'current_quiz_title' not in st.session_state: st.session_state.current_quiz_title = ""

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
        
        weak_points = get_weak_points()
        st.caption(f"📊 취약: {weak_points}")
        full_prompt = f"문서 바탕으로 5문제 출제. 친구들이 자주 틀린 주제({weak_points}) 참고.\n[Q]문제 [O]①.. [A]정답 [K]키워드"
        st.code(full_prompt, language="text")
        
        global_state['instant_feedback'] = st.toggle("정답 즉시 확인", value=global_state['instant_feedback'])
        global_state['allow_change'] = st.toggle("답안 수정 허용", value=global_state['allow_change'])
        
        with st.expander("🆕 새 퀴즈 만들기", expanded=False):
            new_title = st.text_input("퀴즈 제목 (예: 1주차_지옥불)")
            admin_text = st.text_area("결과물 붙여넣기", height=150)
            if st.button("🚀 신규 배포", use_container_width=True):
                if new_title and admin_text:
                    with open(os.path.join(QUIZ_DIR, f"{new_title}.txt"), "w", encoding="utf-8") as f:
                        f.write(admin_text)
                    st.success(f"'{new_title}' 배포 완료!")
                    # 새 퀴즈를 바로 선택 상태로 만들기
                    st.session_state.current_quiz_title = new_title
                    st.rerun()
        
        with st.expander("🗑️ 퀴즈 관리/삭제", expanded=False):
            for q_t in get_quiz_list():
                col1, col2 = st.columns([3, 1])
                col1.write(q_t)
                if col2.button("삭제", key=f"del_{q_t}"):
                    delete_quiz(q_t)
                    if st.session_state.current_quiz_title == q_t:
                        st.session_state.current_quiz_title = ""
                    st.rerun()

# --- 메인 영역 ---
quiz_list = get_quiz_list()

if not quiz_list:
    st.info("현재 등록된 퀴즈가 없습니다. 관리자가 먼저 문제를 배포해주세요.")
else:
    st.subheader("🎯 도전할 퀴즈를 선택해라")
    
    # 기본 선택값 설정 (아무것도 선택 안 되어있으면 맨 첫 번째 퀴즈로)
    if not st.session_state.current_quiz_title or st.session_state.current_quiz_title not in quiz_list:
        st.session_state.current_quiz_title = quiz_list[0]

    # 모든 퀴즈를 2열(가로 2칸) 버튼으로 나열
    cols = st.columns(2)
    for i, q_title in enumerate(quiz_list):
        # 현재 선택된 퀴즈는 불꽃 마크로 강조
        is_active = (q_title == st.session_state.current_quiz_title)
        btn_label = f"🔥 {q_title}" if is_active else q_title
        
        if cols[i % 2].button(btn_label, use_container_width=True, key=f"sel_{q_title}"):
            if st.session_state.current_quiz_title != q_title:
                st.session_state.current_quiz_title = q_title
                st.session_state.quiz_finished = False
                st.session_state.start_time = None
                st.session_state.user_id = ""
                st.session_state.user_answers = {}
                st.rerun()

    selected_quiz = st.session_state.current_quiz_title

    # 순위표 상시 확인
    current_results_path = os.path.join(RESULTS_DIR, f"results_{selected_quiz}.csv")
    with st.expander(f"📊 '{selected_quiz}' 실시간 순위표", expanded=False):
        if st.button("🔄 순위 갱신"): st.rerun()
        if os.path.exists(current_results_path):
            df = pd.read_csv(current_results_path)
            st.dataframe(df.sort_values(by=['점수', '소요시간(초)'], ascending=[False, True]), use_container_width=True)
        else:
            st.caption("아직 완료된 기록이 없습니다.")

    # 퀴즈 풀기 로직
    current_quiz_data = robust_parse(load_quiz_content(selected_quiz))
    
    if not st.session_state.user_id:
        st.divider()
        st.subheader(f"📍 {selected_quiz} 입장")
        u_id = st.text_input("이름(또는 별명)을 적어라")
        if st.button("참여 및 퀴즈 시작 🚀", use_container_width=True):
            if u_id:
                st.session_state.user_id = u_id
                st.session_state.start_time = time.time()
                st.rerun()
    
    elif st.session_state.start_time and not st.session_state.quiz_finished:
        st.subheader(f"🔥 {st.session_state.user_id}의 서바이벌")
        
        for i, item in enumerate(current_quiz_data):
            st.markdown(f"**Q{i+1}. {item['q']}**")
            
            is_answered = f"ans_{i}" in st.session_state.user_answers
            disabled = is_answered and not global_state['allow_change']
            
            ans = st.radio(f"답안{i}", item['o'], key=f"ans_{i}", index=None, 
                           label_visibility="collapsed", disabled=disabled)
            
            if ans:
                st.session_state.user_answers[f"ans_{i}"] = ans
                if global_state['instant_feedback']:
                    if ans == item['o'][item['a']]:
                        st.success("⭕ 정답!")
                    else:
                        st.error(f"❌ 오답! (정답: {item['o'][item['a']]})")
            st.divider()
            
        if st.button("🏁 모든 문제 제출 및 심판받기", use_container_width=True):
            if len(st.session_state.user_answers) < len(current_quiz_data):
                st.warning("모든 문제를 풀어야 제출할 수 있다!")
            else:
                duration = time.time() - st.session_state.start_time
                wrong_ks = [q['k'] for i, q in enumerate(current_quiz_data) 
                            if st.session_state.user_answers.get(f"ans_{i}") != q['o'][q['a']]]
                score = ((len(current_quiz_data)-len(wrong_ks))/len(current_quiz_data))*100
                
                new_res = pd.DataFrame([[st.session_state.user_id, score, round(duration, 2), time.strftime('%H:%M:%S')]], 
                                       columns=['아이디', '점수', '소요시간(초)', '완료시간'])
                new_res.to_csv(current_results_path, mode='a', header=not os.path.exists(current_results_path), index=False, encoding='utf-8-sig')
                
                if wrong_ks:
                    wrong_df = pd.DataFrame([{"아이디": st.session_state.user_id, "키워드": k, "일시": time.strftime('%Y-%m-%d %H:%M:%S')} for k in wrong_ks])
                    wrong_df.to_csv(WRONG_DATA_FILE, mode='a', header=not os.path.exists(WRONG_DATA_FILE), index=False, encoding='utf-8-sig')
                
                st.session_state.quiz_finished = True
                st.rerun()

    if st.session_state.quiz_finished:
        st.balloons()
        st.success("제출 완료! 위 순위표에서 살아남았는지 확인해라.")
        if st.button("다시 처음으로 돌아가기"):
            st.session_state.quiz_finished = False
            st.session_state.start_time = None
            st.session_state.user_id = ""
            st.session_state.user_answers = {}
            st.rerun()
