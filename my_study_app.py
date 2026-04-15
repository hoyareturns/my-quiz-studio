import streamlit as st
import re
import time
import pandas as pd
import gspread
import json
import qrcode
from io import BytesIO
from collections import Counter

# --- 0. 페이지 설정 및 디자인 ---
st.set_page_config(page_title="우정 파괴소", page_icon="🧪", layout="centered")

st.markdown("""
<style>
/* 📖 국어/영어 지문 전용 상자 스타일 */
.passage-container {
    background-color: #fdfdfd;
    border: 1px solid #e1e4e8;
    border-left: 5px solid #4A90E2;
    padding: 20px;
    border-radius: 8px;
    font-size: 15px;
    line-height: 1.8;
    color: #2c3e50;
    margin-bottom: 15px;
    white-space: pre-wrap; 
}
/* 문제 번호 헤더 */
.question-header {
    font-size: 18px;
    font-weight: 800;
    color: #ff4b4b;
    margin-top: 30px;
}
/* 모바일 2열 레이아웃 강제 */
@media (max-width: 768px) {
    [data-testid="stTabs"] [data-testid="column"] {
        flex: 1 1 calc(50% - 10px) !important;
        min-width: calc(45%) !important;
    }
}
</style>
""", unsafe_allow_html=True)

# --- 1. 구글 시트 연동 설정 ---
@st.cache_resource
def get_gspread_client():
    try:
        credentials = json.loads(st.secrets["GCP_JSON"], strict=False)
        gc = gspread.service_account_from_dict(credentials)
        return gc.open_by_key(st.secrets["SHEET_ID"])
    except Exception as e:
        st.error(f"구글 시트 인증 오류: {e}")
        return None

def get_worksheet(sheet_name, columns=None):
    try:
        sh = get_gspread_client()
        if not sh:
            return None
        try:
            ws = sh.worksheet(sheet_name)
        except gspread.exceptions.WorksheetNotFound:
            if columns:
                ws = sh.add_worksheet(title=sheet_name, rows="100", cols=len(columns))
                ws.append_row(columns)
                return ws
            return None
        return ws
    except Exception:
        return None

# --- 2. 데이터 처리 및 정밀 파싱 로직 ---
@st.cache_data(ttl=15, show_spinner=False)
def get_all_quizzes():
    ws = get_worksheet("Quizzes", ["Category", "Title", "Content", "CreatedAt"])
    if ws:
        data = ws.get_all_records()
        return sorted(data, key=lambda x: str(x.get('CreatedAt', '')), reverse=True)
    return []

@st.cache_data(ttl=15, show_spinner=False)
def get_all_results():
    ws = get_worksheet("Results", ["QuizTitle", "User", "Score", "Duration", "Time"])
    if ws:
        return ws.get_all_records()
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

def robust_parse(text):
    # [버그 수정] AI의 불필요한 인사말을 제거하고 [Q]부터 시작하도록 파싱
    first_q_pos = text.find("[Q")
    if first_q_pos != -1:
        text = text[first_q_pos:]

    chunks = re.split(r"\[Q\d*\]", text)
    parsed = []
    ans_map = {'①':0, '②':1, '③':2, '④':3, '⑤':4, '1':0, '2':1, '3':2, '4':3, '5':4}
    
    for chunk in chunks:
        if not chunk.strip():
            continue
        # 필수 태그가 없는 잘못된 덩어리 무시
        if "[O]" not in chunk or "[A]" not in chunk:
            continue
            
        try:
            parts = re.split(r"(\[O\]|\[A\]|\[K\])", chunk)
            q_raw = parts[0].strip()
            o_raw, a_raw, k_raw = "", "1", "미분류"
            
            for i in range(len(parts)):
                tag = parts[i].strip()
                if tag == "[O]":
                    o_raw = parts[i+1].strip()
                elif tag == "[A]":
                    a_raw = parts[i+1].strip()
                elif tag == "[K]":
                    k_raw = parts[i+1].strip()
            
            opts = re.findall(r'[①-⑤]\s*([^①-⑤\n\r]+)', o_raw)
            if not opts:
                opts = [o.strip() for o in o_raw.split(',') if o.strip()]
            
            ans_char = a_raw.strip()[0] if a_raw else "1"
            ans_idx = ans_map.get(ans_char, 0)
            
            parsed.append({
                "q": q_raw, 
                "o": [o.strip() for o in opts], 
                "a": ans_idx, 
                "k": k_raw
            })
        except Exception:
            continue
            
    return parsed

# --- 3. 데이터 저장 및 관리 기능 ---
def delete_quiz_from_gsheet(quiz_title):
    ws = get_worksheet("Quizzes")
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
    # 1. 점수 및 결과 저장
    res_ws = get_worksheet("Results", ["QuizTitle", "User", "Score", "Duration", "Time"])
    if res_ws:
        res_ws.append_row([
            quiz_title, 
            user_id, 
            score, 
            round(duration, 2), 
            time.strftime('%Y-%m-%d %H:%M:%S')
        ])
        
    # 2. [기능 복구] 오답 키워드 저장 로직
    if wrong_keywords:
        wrong_ws = get_worksheet("WrongAnswers", ["User", "Keyword", "Time"])
        if wrong_ws:
            for keyword in wrong_keywords:
                wrong_ws.append_row([
                    user_id, 
                    keyword, 
                    time.strftime('%Y-%m-%d %H:%M:%S')
                ])
                
    get_all_results.clear()
    get_weak_points_from_gsheet.clear()

# --- 4. 세션 초기화 및 상태 관리 ---
APP_URL = "https://hoya-quiz-studio.streamlit.app"
ADMIN_PASSWORD = "1234"

if 'player_name' not in st.session_state:
    st.session_state.player_name = ""
if 'selected_quiz_title' not in st.session_state:
    st.session_state.selected_quiz_title = ""
if 'user_answers' not in st.session_state:
    st.session_state.user_answers = {}
if 'quiz_finished' not in st.session_state:
    st.session_state.quiz_finished = False
if 'start_time' not in st.session_state:
    st.session_state.start_time = None
if 'review_data' not in st.session_state:
    st.session_state.review_data = []

@st.cache_resource
def get_admin_settings():
    return {
        "feedback_mode": "⚡ 실시간 팩폭 (즉시 확인)", 
        "allow_change": False, 
        "default_category": ""
    }
admin_settings = get_admin_settings()

@st.cache_resource
def get_active_users():
    return set()
active_users = get_active_users()

# --- 5. 사이드바 구성 ---
with st.sidebar:
    st.markdown(
        f"<div style='text-align:right;'><span style='font-size: 14px; color: #4CAF50;'>🟢 풀이중: {len(active_users)}명</span></div>", 
        unsafe_allow_html=True
    )
    
    st.subheader("⚙️ 관리자 설정")
    pw_input = st.text_input("비밀번호", type="password", placeholder="Password", label_visibility="collapsed")
    
    if pw_input == ADMIN_PASSWORD:
        st.success("관리자 인증 완료")
        
        # 취약 주제 분석 결과 가져오기
        weak_points_data = get_weak_points_from_gsheet()
        
        # 🪄 AI 출제 프롬프트 가이드 (안전한 Raw String 사용)
        st.info("🪄 **AI 출제 프롬프트 가이드**")
        prompt_text = f"""국어/사회 문제 10개를 출제해줘. 자주 틀리는 주제({weak_points_data})를 반영해줘.
인사말이나 부가 설명 없이 곧바로 [Q1]부터 출력해줘.
지문이 있는 경우 반드시 포함하되, 아래 형식을 엄격히 지켜줘.

[Q]
<지문>
여기에 소설이나 시 지문 입력 (줄바꿈 가능)
</지문>
문제 내용(발문) 입력

[O] ①보기1 ②보기2 ③보기3 ④보기4 ⑤보기5
[A] 정답 기호(예: ②)
[K] 핵심 키워드"""
        
        st.code(prompt_text, language="text")
        st.caption(f"📊 최근 취약 주제 분석: {weak_points_data}")
        st.divider()

        # 채점 방식 및 초기 화면 설정
        admin_settings['default_category'] = st.text_input("📌 처음 열릴 카테고리", value=admin_settings.get('default_category', ''))
        
        mode_options = ["⚡ 실시간 팩폭 (즉시 확인)", "🏁 최후의 심판 (마지막에 한 번에)"]
        selected_mode = st.selectbox(
            "채점 방식", 
            mode_options, 
            index=mode_options.index(admin_settings['feedback_mode'])
        )
        admin_settings['feedback_mode'] = selected_mode
        admin_settings['allow_change'] = (selected_mode != mode_options[0])

        # 퀴즈 배포 메뉴
        with st.expander("🆕 새 퀴즈 만들기", expanded=False):
            new_cat = st.text_input("카테고리")
            new_title = st.text_input("퀴즈 제목")
            new_content = st.text_area("AI 결과물 붙여넣기", height=150)
            
            if st.button("🚀 신규 배포", use_container_width=True):
                if new_cat and new_title and new_content:
                    ws_quiz = get_worksheet("Quizzes", ["Category", "Title", "Content", "CreatedAt"])
                    if ws_quiz:
                        ws_quiz.append_row([
                            new_cat, 
                            new_title, 
                            new_content, 
                            time.strftime('%Y-%m-%d %H:%M:%S')
                        ])
                        get_all_quizzes.clear()
                        st.success("성공적으로 배포되었습니다!")
                        st.rerun()

        # 퀴즈 삭제 메뉴
        with st.expander("🗑️ 퀴즈 삭제", expanded=False):
            all_quizzes = get_all_quizzes()
            for idx, q_item in enumerate(all_quizzes):
                col1, col2 = st.columns([3, 1])
                col1.caption(f"{q_item.get('Category')} - {q_item.get('Title')}")
                if col2.button("X", key=f"del_btn_{idx}"):
                    if delete_quiz_from_gsheet(q_item.get('Title')):
                        st.rerun()
    
    st.divider()
    # QR 코드 생성
    qr = qrcode.QRCode(version=1, box_size=3, border=2)
    qr.add_data(APP_URL)
    qr.make(fit=True)
    buf = BytesIO()
    qr.make_image(fill_color="black", back_color="white").save(buf)
    st.image(buf.getvalue(), width=100)

# --- 6. 메인 퀴즈 영역 ---
st.title("🧪 우정 파괴소")
st.session_state.player_name = st.text_input("👤 참가자 이름", value=st.session_state.player_name)
st.divider()

quiz_data_list = get_all_quizzes()

if quiz_data_list:
    st.subheader("🎯 퀴즈 선택")
    
    # 카테고리 탭 분류
    categories = []
    for q in quiz_data_list:
        cat_name = q.get('Category', '미분류') or '미분류'
        if cat_name not in categories:
            categories.append(cat_name)
            
    pref_cat = admin_settings.get('default_category', '').strip()
    if pref_cat in categories:
        categories.remove(pref_cat)
        categories.insert(0, pref_cat)
    
    tabs = st.tabs(categories)
    
    for i, category in enumerate(categories):
        with tabs[i]:
            category_quizzes = [q for q in quiz_data_list if (q.get('Category') or '미분류') == category]
            cols = st.columns(2)
            
            for j, quiz_item in enumerate(category_quizzes):
                q_title = quiz_item.get('Title')
                btn_label = f"🔥 {q_title}" if q_title == st.session_state.selected_quiz_title else q_title
                
                if cols[j % 2].button(btn_label, use_container_width=True, key=f"btn_{category}_{j}"):
                    st.session_state.selected_quiz_title = q_title
                    st.session_state.quiz_finished = False
                    st.session_state.start_time = None
                    st.session_state.user_answers = {}
                    st.rerun()

    # 퀴즈 풀이 로직
    if st.session_state.selected_quiz_title:
        current_quiz_data = next((q for q in quiz_data_list if q['Title'] == st.session_state.selected_quiz_title), None)
        
        if current_quiz_data:
            # 📊 실시간 순위표
            with st.expander("📊 실시간 랭킹 보드", expanded=False):
                if st.button("🔄 순위 갱신"):
                    get_all_results.clear()
                    st.rerun()
                    
                all_results = get_all_results()
                quiz_results = [r for r in all_results if r.get('QuizTitle') == current_quiz_data['Title']]
                
                if quiz_results:
                    df = pd.DataFrame(quiz_results).sort_values(by=['Score', 'Duration'], ascending=[False, True])
                    st.dataframe(df, use_container_width=True)
                else:
                    st.caption("아직 기록이 없습니다.")

            # 퀴즈 시작 대기 화면
            if st.session_state.start_time is None and not st.session_state.quiz_finished:
                if st.button(f"🚀 '{current_quiz_data['Title']}' 시작하기", use_container_width=True):
                    if st.session_state.player_name:
                        st.session_state.start_time = time.time()
                        active_users.add(st.session_state.player_name)
                        st.rerun()
                    else:
                        st.warning("위쪽 입력칸에 이름을 먼저 적어주세요!")
            
            # 실제 퀴즈 푸는 화면
            elif st.session_state.start_time and not st.session_state.quiz_finished:
                parsed_questions = robust_parse(current_quiz_data['Content'])
                
                for idx, item in enumerate(parsed_questions):
                    st.markdown(f'<p class="question-header">문제 {idx+1}.</p>', unsafe_allow_html=True)
                    
                    # 지문 인식 및 박스 스타일 적용
                    display_q = item['q']
                    if "<지문>" in display_q and "</지문>" in display_q:
                        display_q = display_q.replace("<지문>", '<div class="passage-container">')
                        display_q = display_q.replace("</지문>", '</div>')
                        st.markdown(display_q, unsafe_allow_html=True)
                    else:
                        st.markdown(f'<div class="passage-container">{display_q}</div>', unsafe_allow_html=True)
                    
                    # 보기 선택
                    is_answered = f"ans_{idx}" in st.session_state.user_answers
                    # 실시간 모드일 때만 비활성화 처리
                    is_disabled = is_answered if admin_settings['feedback_mode'] == "⚡ 실시간 팩폭 (즉시 확인)" else False
                    
                    selected_ans = st.radio(
                        f"문항_{idx}_보기", 
                        item['o'], 
                        index=None, 
                        key=f"radio_{idx}", 
                        disabled=is_disabled, 
                        label_visibility="collapsed"
                    )
                    
                    # 답안 채점
                    if selected_ans:
                        st.session_state.user_answers[f"ans_{idx}"] = selected_ans
                        
                        if admin_settings['feedback_mode'] == "⚡ 실시간 팩폭 (즉시 확인)":
                            if selected_ans == item['o'][item['a']]:
                                st.success("⭕ 정답입니다!")
                            else:
                                st.error(f"❌ 오답입니다! (정답: {item['o'][item['a']]})")
                    st.divider()

                # 답안 제출 및 결과 저장
                if st.button("🏁 모든 답안 제출하기", use_container_width=True):
                    if len(st.session_state.user_answers) >= len(parsed_questions):
                        elapsed_time = time.time() - st.session_state.start_time
                        
                        wrong_keywords = []
                        review_data = []
                        
                        for k_idx, q_item in enumerate(parsed_questions):
                            user_ans = st.session_state.user_answers.get(f"ans_{k_idx}")
                            correct_ans = q_item['o'][q_item['a']]
                            is_correct = (user_ans == correct_ans)
                            
                            if not is_correct:
                                wrong_keywords.append(q_item['k'])
                                
                            review_data.append({
                                "question": q_item['q'], 
                                "user_answer": user_ans, 
                                "correct_answer": correct_ans, 
                                "is_correct": is_correct
                            })
                            
                        final_score = ((len(parsed_questions) - len(wrong_keywords)) / len(parsed_questions)) * 100
                        
                        # 구글 시트에 점수 및 오답 데이터 기록
                        save_result_to_gsheet(
                            current_quiz_data['Title'], 
                            st.session_state.player_name, 
                            final_score, 
                            elapsed_time, 
                            wrong_keywords
                        )
                        
                        st.session_state.quiz_finished = True
                        st.session_state.last_score = final_score
                        st.session_state.review_data = review_data
                        active_users.discard(st.session_state.player_name)
                        st.rerun()
                    else:
                        st.warning("아직 풀지 않은 문제가 남아있습니다!")

        # 퀴즈 종료 후 피드백 화면
        if st.session_state.quiz_finished:
            st.balloons()
            
            # 최후의 심판 모드일 경우 오답 노트 공개
            if admin_settings['feedback_mode'] == "🏁 최후의 심판 (마지막에 한 번에)":
                with st.expander("📝 내 답안지 전체 채점 결과", expanded=True):
                    for i, rev in enumerate(st.session_state.review_data):
                        st.markdown(f"**Q{i+1}.** {'⭕ 정답' if rev['is_correct'] else '❌ 오답'}")
                        if not rev['is_correct']:
                            st.write(f"내 답: {rev['user_answer']} / 실제 정답: **{rev['correct_answer']}**")
                            
            st.success(f"🎉 수고하셨습니다! {st.session_state.player_name}님의 최종 점수는 {int(st.session_state.last_score)}점입니다.")
            st.button("다른 퀴즈 하러 가기", on_click=lambda: st.rerun())
