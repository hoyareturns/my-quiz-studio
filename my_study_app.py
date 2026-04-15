import streamlit as st
import re
import time
import pandas as pd
import gspread
import json
import qrcode
from io import BytesIO
from collections import Counter

# --- 1. 구글 시트 연동 설정 ---
def get_gspread_client():
    # strict=False 를 추가하여 보이지 않는 줄바꿈 에러를 무시하도록 처리합니다.
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

# --- 2. 기본 설정 및 경로 ---
APP_URL = "https://hoya-quiz-studio.streamlit.app"
ADMIN_PASSWORD = "1234"

st.set_page_config(page_title="우정 파괴소", page_icon="🧪", layout="centered")

# --- 3. 데이터 처리 로직 ---
def get_all_quizzes():
    ws = get_worksheet("Quizzes", ["Category", "Title", "Content", "CreatedAt"])
    if ws:
        data = ws.get_all_records()
        return sorted(data, key=lambda x: str(x.get('CreatedAt', '')), reverse=True)
    return []

def save_result_to_gsheet(quiz_title, user_id, score, duration, wrong_keywords):
    res_ws = get_worksheet("Results", ["QuizTitle", "User", "Score", "Duration", "Time"])
    if res_ws:
        res_ws.append_row([quiz_title, user_id, score, round(duration, 2), time.strftime('%Y-%m-%d %H:%M:%S')])
    
    if wrong_keywords:
        wrong_ws = get_worksheet("WrongAnswers", ["User", "Keyword", "Time"])
        if wrong_ws:
            for k in wrong_keywords:
                wrong_ws.append_row([user_id, k, time.strftime('%Y-%m-%d %H:%M:%S')])

def get_weak_points_from_gsheet():
    ws = get_worksheet("WrongAnswers", ["User", "Keyword", "Time"])
    if ws:
        data = ws.get_all_records()
        if data:
            counts = Counter([d.get('Keyword', '') for d in data if d.get('Keyword', '')])
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

# --- 4. 세션 및 전역 상태 관리 ---
if 'user_id' not in st.session_state: st.session_state.user_id = ""
if 'start_time' not in st.session_state: st.session_state.start_time = None
if 'quiz_finished' not in st.session_state: st.session_state.quiz_finished = False
if 'user_answers' not in st.session_state: st.session_state.user_answers = {}
if 'selected_quiz_title' not in st.session_state: st.session_state.selected_quiz_title = ""

@st.cache_resource
def get_admin_settings():
    return {"instant_feedback": True, "allow_change": False}

admin_settings = get_admin_settings()

# --- 5. UI 레이아웃 (사이드바) ---
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
        
        # 프롬프트 복사 영역
        full_prompt = f"""이 문서의 내용을 바탕으로 친구들과 풀 퀴즈 5문제를 만들어줘. 
특히 친구들이 자주 틀린 주제({weak_points})가 있다면 더 심도 있게 다뤄줘.
반드시 아래 형식을 엄격하게 지켜서 다른 설명 없이 텍스트만 출력해줘.

[Q] 문제 내용
[O] ①보기1 ②보기2 ③보기3 ④보기4 ⑤보기5
[A] 정답 기호(예: ②)
[K] 해당 문제의 핵심 키워드(오답 분석용)"""
        st.code(full_prompt, language="text")
        
        # 룰 제어 영역
        st.divider()
        admin_settings['instant_feedback'] = st.toggle("정답 즉시 확인", value=admin_settings['instant_feedback'])
        admin_settings['allow_change'] = st.toggle("답안 수정 허용", value=admin_settings['allow_change'])
        
        # 신규 문제 배포 영역
        with st.expander("🆕 새 퀴즈 만들기", expanded=False):
            new_category = st.text_input("카테고리 (예: 배관기초)")
            new_title = st.text_input("퀴즈 제목 (예: 1주차 지옥불)")
            admin_text = st.text_area("NotebookLM 결과물 붙여넣기", height=150)
            
            if st.button("🚀 신규 배포", use_container_width=True):
                if new_category and new_title and admin_text:
                    ws = get_worksheet("Quizzes", ["Category", "Title", "Content", "CreatedAt"])
                    ws.append_row([new_category, new_title, admin_text, time.strftime('%Y-%m-%d %H:%M:%S')])
                    st.success(f"[{new_category}] '{new_title}' 배포 완료!"); st.rerun()
                else:
                    st.error("카테고리, 제목, 내용을 모두 입력해야 합니다!")

# --- 6. 메인 영역 (퀴즈 탭 분류 및 진행) ---
quiz_data_list = get_all_quizzes()

if not quiz_data_list:
    st.info("현재 등록된 퀴즈가 없습니다. 관리자가 먼저 문제를 배포해주세요.")
else:
    st.subheader("🎯 카테고리 및 퀴즈 선택")
    
    # 카테고리 탭 생성
    categories = []
    for q in quiz_data_list:
        cat = q.get('Category', '미분류')
        if not cat: cat = '미분류'
        if cat not in categories: categories.append(cat)
            
    tabs = st.tabs(categories)
    
    for i, cat in enumerate(categories):
        with tabs[i]:
            cat_quizzes = [q for q in quiz_data_list if q.get('Category', '미분류') == cat or (not q.get('Category') and cat == '미분류')]
            cols = st.columns(2)
            for j, q in enumerate(cat_quizzes):
                q_title = q['Title']
                is_active = (q_title == st.session_state.selected_quiz_title)
                btn_label = f"🔥 {q_title}" if is_active else q_title
                
                if cols[j % 2].button(btn_label, use_container_width=True, key=f"btn_{cat}_{q_title}"):
                    st.session_state.selected_quiz_title = q_title
                    st.session_state.quiz_finished = False
                    st.session_state.start_time = None
                    st.session_state.user_id = ""
                    st.session_state.user_answers = {}
                    st.rerun()

    # 선택된 퀴즈 표시 및 풀이 로직
    if st.session_state.selected_quiz_title:
        selected_quiz_data = next((q for q in quiz_data_list if q['Title'] == st.session_state.selected_quiz_title), None)
        
        if selected_quiz_data:
            quiz_title = selected_quiz_data['Title']
            quiz_category = selected_quiz_data.get('Category', '미분류')
            quiz_content = robust_parse(selected_quiz_data['Content'])

            # 실시간 순위표
            with st.expander(f"📊 [{quiz_category}] '{quiz_title}' 실시간 순위", expanded=False):
                if st.button("🔄 갱신"): st.rerun()
                res_ws = get_worksheet("Results", ["QuizTitle", "User", "Score", "Duration", "Time"])
                if res_ws:
                    all_res = res_ws.get_all_records()
                    quiz_res = [r for r in all_res if r.get('QuizTitle') == quiz_title]
                    if quiz_res:
                        st.dataframe(pd.DataFrame(quiz_res).sort_values(by=['Score', 'Duration'], ascending=[False, True]), use_container_width=True)
                    else:
                        st.caption("아직 기록이 없습니다. 최초의 희생자가 되어보세요!")

            # 퀴즈 풀기 진행
            if not st.session_state.user_id:
                st.divider()
                u_id = st.text_input(f"[{quiz_title}] 참여할 이름을 입력하세요")
                if st.button("참여 및 바로 시작 🚀", use_container_width=True):
                    if u_id:
                        st.session_state.user_id = u_id
                        st.session_state.start_time = time.time(); st.rerun()
            
            elif st.session_state.start_time and not st.session_state.quiz_finished:
                st.subheader(f"🔥 {st.session_state.user_id}의 도전")
                for idx, item in enumerate(quiz_content):
                    st.markdown(f"**Q{idx+1}. {item['q']}**")
                    
                    is_answered = f"ans_{idx}" in st.session_state.user_answers
                    disabled = is_answered and not admin_settings['allow_change']
                    
                    ans = st.radio(f"답안{idx}", item['o'], key=f"ans_{idx}", index=None, label_visibility="collapsed", disabled=disabled)
                    
                    if ans:
                        st.session_state.user_answers[f"ans_{idx}"] = ans
                        if admin_settings['instant_feedback']:
                            if ans == item['o'][item['a']]:
                                st.success("⭕ 정답!")
                            else:
                                st.error(f"❌ 오답! (정답: {item['o'][item['a']]})")
                    st.divider()
                
                if st.button("🏁 제출하기", use_container_width=True):
                    if len(st.session_state.user_answers) < len(quiz_content):
                        st.warning("모든 문제를 풀어야 제출할 수 있습니다!")
                    else:
                        duration = time.time() - st.session_state.start_time
                        wrong_ks = [q['k'] for k_i, q in enumerate(quiz_content) if st.session_state.user_answers.get(f"ans_{k_i}") != q['o'][q['a']]]
                        score = ((len(quiz_content)-len(wrong_ks))/len(quiz_content))*100
                        save_result_to_gsheet(quiz_title, st.session_state.user_id, score, duration, wrong_ks)
                        st.session_state.quiz_finished = True; st.rerun()

            if st.session_state.quiz_finished:
                st.balloons()
                st.success("제출 완료! 상단 순위표를 확인하세요.")
                if st.button("다른 퀴즈 하러 가기"):
                    st.session_state.quiz_finished = False; st.session_state.start_time = None
                    st.session_state.user_id = ""; st.session_state.user_answers = {}; st.rerun()
