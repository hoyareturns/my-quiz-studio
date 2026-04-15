import streamlit as st
import re
import time
import pandas as pd
import gspread
import json
import qrcode
from io import BytesIO
from collections import Counter

# --- 0. 페이지 설정 및 디자인 (다크모드 지원 CSS 패치) ---
st.set_page_config(page_title="우정 파괴소", page_icon="🧪", layout="centered")

st.markdown("""
<style>
/* 지문/수식 렌더링용 마크다운 개조 (다크/라이트 모드 자동 대응) */
[data-testid="stMain"] blockquote {
    background-color: var(--secondary-background-color) !important; 
    border: 1px solid var(--border-color) !important;
    border-left: 5px solid var(--primary-color) !important; 
    padding: 20px !important;
    border-radius: 8px !important; 
    font-size: 15px !important; 
    line-height: 1.8 !important;
    color: var(--text-color) !important; 
    margin-bottom: 15px !important; 
    font-style: normal !important;
}
[data-testid="stMain"] blockquote p { margin-bottom: 0 !important; }
.question-header { font-size: 18px; font-weight: 800; color: #ff4b4b; margin-top: 30px; margin-bottom: 10px; }
/* 채팅창 스타일 (다크/라이트 모드 자동 대응) */
.chat-msg { padding: 10px; border-radius: 10px; margin-bottom: 10px; background-color: var(--secondary-background-color); color: var(--text-color); }
.chat-user { font-weight: bold; color: var(--primary-color); font-size: 14px; }
.chat-time { font-size: 11px; color: var(--text-color); opacity: 0.6; float: right; }
@media (max-width: 768px) { [data-testid="stTabs"] [data-testid="column"] { flex: 1 1 calc(50% - 10px) !important; min-width: calc(45%) !important; } }
</style>
""", unsafe_allow_html=True)

# --- 1. 구글 시트 연동 ---
@st.cache_resource
def get_gspread_client():
    try:
        creds = json.loads(st.secrets["GCP_JSON"], strict=False)
        return gspread.service_account_from_dict(creds).open_by_key(st.secrets["SHEET_ID"])
    except: return None

def get_worksheet(sheet_name, columns=None):
    try:
        sh = get_gspread_client()
        if not sh: return None
        try: return sh.worksheet(sheet_name)
        except gspread.exceptions.WorksheetNotFound:
            if columns:
                ws = sh.add_worksheet(title=sheet_name, rows="100", cols=len(columns))
                ws.append_row(columns); return ws
            return None
    except: return None

# --- 2. 데이터 처리 ---
@st.cache_data(ttl=10, show_spinner=False)
def get_all_quizzes():
    ws = get_worksheet("Quizzes", ["Category", "Title", "Content", "CreatedAt"])
    return sorted(ws.get_all_records(), key=lambda x: str(x.get('CreatedAt', '')), reverse=True) if ws else []

@st.cache_data(ttl=10, show_spinner=False)
def get_all_results():
    ws = get_worksheet("Results", ["QuizTitle", "User", "Score", "Duration", "Time"])
    return ws.get_all_records() if ws else []

@st.cache_data(ttl=10, show_spinner=False)
def get_settings():
    ws = get_worksheet("Settings", ["Key", "Value"])
    if ws: return {str(r['Key']): str(r['Value']) for r in ws.get_all_records()}
    return {}

def save_setting(key, value):
    ws = get_worksheet("Settings")
    if ws:
        cell = ws.find(key, in_column=1)
        if cell: ws.update_cell(cell.row, 2, str(value))
        else: ws.append_row([key, str(value)])
    get_settings.clear()

@st.cache_data(ttl=5, show_spinner=False)
def get_chats():
    ws = get_worksheet("Chat", ["Time", "User", "Message"])
    return ws.get_all_records()[-50:] if ws else []

def save_chat(user, message):
    ws = get_worksheet("Chat")
    if ws: ws.append_row([time.strftime('%Y-%m-%d %H:%M:%S'), user, message])
    get_chats.clear()

@st.cache_data(ttl=30, show_spinner=False)
def get_weak_points_from_gsheet():
    ws = get_worksheet("WrongAnswers", ["User", "Keyword", "Time"])
    if ws:
        data = ws.get_all_records()
        counts = Counter([d.get('Keyword', '') for d in data if d.get('Keyword', '')])
        return ", ".join([f"{k}({c}회)" for k, c in counts.most_common(3)])
    return "데이터 없음"

def robust_parse(text):
    first_q_pos = text.find("[Q")
    if first_q_pos != -1: text = text[first_q_pos:]
    parsed, ans_map = [], {'①':0, '②':1, '③':2, '④':3, '⑤':4, '1':0, '2':1, '3':2, '4':3, '5':4}
    for chunk in re.split(r"\[Q\d*\]", text):
        if not chunk.strip() or "[O]" not in chunk or "[A]" not in chunk: continue
        try:
            parts = re.split(r"(\[O\]|\[A\]|\[K\])", chunk)
            q_raw, o_raw, a_raw, k_raw = parts[0].strip(), "", "1", "미분류"
            for i in range(len(parts)):
                t = parts[i].strip()
                if t == "[O]": o_raw = parts[i+1].strip()
                elif t == "[A]": a_raw = parts[i+1].strip()
                elif t == "[K]": k_raw = parts[i+1].strip()
            opts = re.findall(r'[①-⑤]\s*([^①-⑤\n\r]+)', o_raw)
            if not opts: opts = [o.strip() for o in o_raw.split(',') if o.strip()]
            parsed.append({"q": q_raw, "o": [o.strip() for o in opts], "a": ans_map.get(a_raw.strip()[0] if a_raw else "1", 0), "k": k_raw})
        except: continue
    return parsed

# --- 3. 퀴즈 관리 (수정 기능 추가) ---
def update_quiz_in_gsheet(old_title, new_cat, new_tit):
    ws = get_worksheet("Quizzes")
    if ws:
        try:
            cell = ws.find(old_title, in_column=2) # Title은 2번째 열
            if cell:
                ws.update_cell(cell.row, 1, new_cat)
                ws.update_cell(cell.row, 2, new_tit)
                get_all_quizzes.clear(); return True
        except: pass
    return False

def delete_quiz(title):
    ws = get_worksheet("Quizzes")
    if ws:
        try:
            cell = ws.find(title, in_column=2)
            if cell: ws.delete_rows(cell.row); get_all_quizzes.clear(); return True
        except: pass
    return False

def save_result(title, user, score, duration, wrongs):
    res_ws = get_worksheet("Results")
    if res_ws: res_ws.append_row([title, user, score, round(duration, 2), time.strftime('%Y-%m-%d %H:%M:%S')])
    if wrongs:
        wr_ws = get_worksheet("WrongAnswers")
        if wr_ws: [wr_ws.append_row([user, k, time.strftime('%Y-%m-%d %H:%M:%S')]) for k in wrongs]
    get_all_results.clear(); get_weak_points_from_gsheet.clear()

# --- 4. 초기화 및 자동 이름 부여 ---
APP_URL = "https://hoya-quiz-studio.streamlit.app"
ADMIN_PASSWORD = "1234"
app_settings = get_settings()

if 'player_name' not in st.session_state or not st.session_state.player_name:
    max_num = 0
    for r in get_all_results():
        m = re.match(r"우정파괴자(\d+)", str(r.get('User', '')))
        if m: max_num = max(max_num, int(m.group(1)))
    st.session_state.player_name = f"우정파괴자{max_num + 1}"

for k in ['selected_quiz', 'user_answers', 'quiz_finished', 'start_time', 'review_data']:
    if k not in st.session_state: st.session_state[k] = "" if k == 'selected_quiz' else {} if k == 'user_answers' else False if k == 'quiz_finished' else None

@st.cache_resource
def get_active_users(): return set()
active_users = get_active_users()

# --- 5. 사이드바 (관리자 설정) ---
with st.sidebar:
    st.markdown(f"<div style='text-align:right;'><span style='font-size: 14px; color: #4CAF50;'>🟢 접속중: {len(active_users)}명</span></div>", unsafe_allow_html=True)
    st.subheader("⚙️ 관리자 설정")
    
    pw_input = st.text_input("비밀번호", type="password", placeholder="Password", label_visibility="collapsed")
    if pw_input == ADMIN_PASSWORD:
        st.success("관리자 인증 완료")
        wp_data = get_weak_points_from_gsheet()
        
        st.info("🪄 **AI 출제 프롬프트 가이드**")
        prompt_text = f"""과목에 맞는 문제 10개를 출제해줘. 자주 틀리는 주제({wp_data})를 반영해줘.
인사말 없이 [Q1]부터 출력해.
★중요: 그림, 표, 그래프 등 텍스트로 표현할 수 없는 자료는 지문에 절대 포함하지 마.

[Q]
<지문> (수식은 $ 기호 사용) </지문>
문제 내용

[O] ①보기1 ②보기2 ③보기3 ④보기4 ⑤보기5
[A] 정답 기호(예: ②)
[K] 핵심 키워드"""
        st.code(prompt_text, language="text")
        st.caption(f"📊 취약 주제: {wp_data}")
        st.divider()

        # 커스텀 카테고리(그룹) 리스트 생성 로직
        all_q = get_all_quizzes()
        custom_cats_str = app_settings.get("custom_categories", "")
        custom_cats = [c.strip() for c in custom_cats_str.split(",") if c.strip()]
        quiz_cats = [q.get('Category', '미분류') or '미분류' for q in all_q]
        
        all_categories = list(dict.fromkeys(custom_cats + quiz_cats))
        if not all_categories: all_categories = ["미분류"]

        # 처음 열릴 카테고리 및 화면 설정
        current_def_cat = app_settings.get('default_category', all_categories[0])
        if current_def_cat not in all_categories: all_categories.insert(0, current_def_cat)
        sel_cat = st.selectbox("📌 처음 열릴 카테고리", all_categories, index=all_categories.index(current_def_cat))
        if sel_cat != current_def_cat: save_setting("default_category", sel_cat); st.rerun()

        view_opts = ["🎯 퀴즈 선택", "💬 우정파괴창"]
        current_view = app_settings.get('default_view', view_opts[0])
        sel_view = st.selectbox("앱 시작 시 기본 화면", view_opts, index=view_opts.index(current_view))
        if sel_view != current_view: save_setting("default_view", sel_view); st.rerun()

        mode_opts = ["⚡ 실시간 팩폭 (즉시 확인)", "🏁 최후의 심판 (마지막에 한 번에)"]
        current_mode = app_settings.get('feedback_mode', mode_opts[0])
        sel_mode = st.selectbox("채점 방식", mode_opts, index=mode_opts.index(current_mode))
        if sel_mode != current_mode: save_setting("feedback_mode", sel_mode); st.rerun()

        # [신규] 그룹(카테고리) 추가 전용
        with st.expander("➕ 새 그룹(카테고리) 생성", expanded=False):
            new_group = st.text_input("새 그룹 이름")
            if st.button("그룹 추가", use_container_width=True):
                if new_group and new_group not in custom_cats:
                    custom_cats.append(new_group)
                    save_setting("custom_categories", ",".join(custom_cats))
                    st.rerun()

        with st.expander("🆕 새 퀴즈 배포", expanded=False):
            nc = st.text_input("카테고리 (자동 분류됨)"); nt = st.text_input("퀴즈 제목"); nx = st.text_area("결과물 붙여넣기", height=150)
            if st.button("🚀 신규 배포", use_container_width=True):
                if nc and nt and nx:
                    ws_q = get_worksheet("Quizzes")
                    if ws_q: ws_q.append_row([nc, nt, nx, time.strftime('%Y-%m-%d %H:%M:%S')]); get_all_quizzes.clear(); st.rerun()

        # [수정/개선] 퀴즈 이름 및 그룹 변경 로직 통합
        with st.expander("✏️ 퀴즈 관리 (수정 및 삭제)", expanded=False):
            if all_q:
                q_titles = [q['Title'] for q in all_q]
                sel_edit_q = st.selectbox("관리할 퀴즈 선택", q_titles)
                if sel_edit_q:
                    curr_q = next((q for q in all_q if q['Title'] == sel_edit_q), None)
                    edit_cat = st.text_input("카테고리 (그룹) 변경", value=curr_q['Category'])
                    edit_tit = st.text_input("퀴즈 제목 변경", value=curr_q['Title'])
                    col1, col2 = st.columns(2)
                    if col1.button("💾 정보 수정", use_container_width=True):
                        if update_quiz_in_gsheet(sel_edit_q, edit_cat, edit_tit): st.rerun()
                    if col2.button("🗑️ 삭제", use_container_width=True):
                        if delete_quiz(sel_edit_q): st.rerun()
    st.divider()
    qr = qrcode.QRCode(version=1, box_size=3, border=2); qr.add_data(APP_URL); qr.make(fit=True)
    buf = BytesIO(); qr.make_image(fill_color="black", back_color="white").save(buf); st.image(buf.getvalue(), width=100)

# --- 6. 메인 화면 ---
st.title("🧪 우정 파괴소")
# [수정] 입력창 설명 군더더기 제거
st.session_state.player_name = st.text_input("👤 참가자 이름", value=st.session_state.player_name)
st.divider()

active_users.add(st.session_state.player_name)

view_mode = st.radio("화면 선택", ["🎯 퀴즈 선택", "💬 우정파괴창"], horizontal=True, label_visibility="collapsed", index=["🎯 퀴즈 선택", "💬 우정파괴창"].index(app_settings.get('default_view', "🎯 퀴즈 선택")))

if view_mode == "💬 우정파괴창":
    st.subheader("💬 우정파괴창 (소통 & 자랑)")
    chat_container = st.container(height=400)
    for chat in get_chats():
        chat_container.markdown(f"""
        <div class="chat-msg">
            <span class="chat-user">{chat.get('User', '익명')}</span>
            <span class="chat-time">{chat.get('Time', '')[11:16]}</span>
            <div style="margin-top: 5px;">{chat.get('Message', '')}</div>
        </div>
        """, unsafe_allow_html=True)
        
    with st.form("chat_form", clear_on_submit=True):
        col1, col2 = st.columns([4, 1])
        msg = col1.text_input("메시지 입력", label_visibility="collapsed", placeholder="점수 자랑이나 건의사항을 남겨보세요!")
        if col2.form_submit_button("전송", use_container_width=True) and msg.strip():
            save_chat(st.session_state.player_name, msg.strip()); st.rerun()

elif view_mode == "🎯 퀴즈 선택":
    quiz_data_list = get_all_quizzes()
    
    # 설정에 저장된 그룹(카테고리)과 퀴즈의 카테고리 병합 (빈 탭도 노출하기 위해)
    custom_cats_str = app_settings.get("custom_categories", "")
    custom_cats = [c.strip() for c in custom_cats_str.split(",") if c.strip()]
    quiz_cats = [q.get('Category', '미분류') or '미분류' for q in quiz_data_list]
    categories = list(dict.fromkeys(custom_cats + quiz_cats))
    
    pref_cat = app_settings.get('default_category', '').strip()
    if pref_cat in categories: categories.remove(pref_cat); categories.insert(0, pref_cat)
    
    if not categories: categories = ["미분류"]
    tabs = st.tabs(categories)
    
    for i, category in enumerate(categories):
        with tabs[i]:
            cat_quizzes = sorted([q for q in quiz_data_list if (q.get('Category') or '미분류') == category], key=lambda x: x['Title'])
            if not cat_quizzes:
                st.caption("이 그룹에는 아직 등록된 퀴즈가 없습니다.")
            else:
                cols = st.columns(2)
                for j, q_item in enumerate(cat_quizzes):
                    q_title = q_item.get('Title')
                    btn_label = f"🔥 {q_title}" if q_title == st.session_state.selected_quiz else q_title
                    
                    if cols[j % 2].button(btn_label, use_container_width=True, key=f"btn_{category}_{j}"):
                        st.session_state.selected_quiz = q_title
                        st.session_state.quiz_finished = False
                        st.session_state.start_time = None
                        st.session_state.user_answers = {}
                        st.rerun()

        if st.session_state.selected_quiz:
            st.divider()
            st.subheader(f"📖 {st.session_state.selected_quiz}")
            curr_q_data = next((q for q in quiz_data_list if q['Title'] == st.session_state.selected_quiz), None)
            
            if curr_q_data:
                with st.expander("🏆 이 퀴즈의 실시간 랭킹", expanded=False):
                    if st.button("🔄 랭킹 갱신"): get_all_results.clear(); st.rerun()
                    q_results = [r for r in get_all_results() if r.get('QuizTitle') == curr_q_data['Title']]
                    if q_results: st.dataframe(pd.DataFrame(q_results).sort_values(by=['Score', 'Duration'], ascending=[False, True]), use_container_width=True)
                    else: st.caption("아직 기록이 없습니다. 첫 번째 랭커가 되어보세요!")

                if st.session_state.start_time is None and not st.session_state.quiz_finished:
                    if st.button("🚀 퀴즈 시작하기!", use_container_width=True, type="primary"):
                        st.session_state.start_time = time.time(); st.rerun()
                
                elif st.session_state.start_time and not st.session_state.quiz_finished:
                    parsed_qs = robust_parse(curr_q_data['Content'])
                    for idx, item in enumerate(parsed_qs):
                        st.markdown(f'<p class="question-header">Q{idx+1}.</p>', unsafe_allow_html=True)
                        disp_q = item['q']
                        if "<지문>" in disp_q and "</지문>" in disp_q:
                            parts = disp_q.split("<지문>")
                            st.markdown(parts[0].strip())
                            p_parts = parts[1].split("</지문>")
                            st.markdown("\n".join([f"> {line}" for line in p_parts[0].strip().split('\n')]))
                            if len(p_parts) > 1: st.markdown(p_parts[1].strip())
                        else:
                            st.markdown("\n".join([f"> {line}" for line in disp_q.strip().split('\n')]))
                        
                        is_ans = f"ans_{idx}" in st.session_state.user_answers
                        f_mode = app_settings.get('feedback_mode', "⚡ 실시간 팩폭 (즉시 확인)")
                        sel_ans = st.radio(f"보기_{idx}", item['o'], index=None, key=f"r_{idx}", disabled=is_ans if f_mode.startswith("⚡") else False, label_visibility="collapsed")
                        
                        if sel_ans:
                            st.session_state.user_answers[f"ans_{idx}"] = sel_ans
                            if f_mode.startswith("⚡"):
                                if sel_ans == item['o'][item['a']]: st.success("⭕ 정답!")
                                else: st.error(f"❌ 오답! (정답: {item['o'][item['a']]})")
                        st.divider()

                    if st.button("🏁 답안 제출 (미응답 시 오답 처리)", use_container_width=True):
                        elapsed = time.time() - st.session_state.start_time
                        wrongs, rev_data = [], []
                        for k_idx, q_item in enumerate(parsed_qs):
                            u_ans = st.session_state.user_answers.get(f"ans_{k_idx}")
                            c_ans = q_item['o'][q_item['a']]
                            if u_ans is None:
                                wrongs.append(q_item['k'])
                                rev_data.append({"q": q_item['q'], "u": None, "c": c_ans, "is_c": False, "is_u": True})
                            else:
                                is_c = (u_ans == c_ans)
                                if not is_c: wrongs.append(q_item['k'])
                                rev_data.append({"q": q_item['q'], "u": u_ans, "c": c_ans, "is_c": is_c, "is_u": False})
                            
                        f_score = ((len(parsed_qs) - len(wrongs)) / len(parsed_qs)) * 100
                        save_result(curr_q_data['Title'], st.session_state.player_name, f_score, elapsed, wrongs)
                        st.session_state.quiz_finished = True; st.session_state.last_score = f_score
                        st.session_state.review_data = rev_data; st.rerun()

            if st.session_state.quiz_finished:
                st.balloons()
                if app_settings.get('feedback_mode', "").startswith("🏁"):
                    with st.expander("📝 내 답안지 채점 결과", expanded=True):
                        for i, rev in enumerate(st.session_state.review_data):
                            if rev.get('is_u'):
                                st.markdown(f"**Q{i+1}.** ❌ 미응답"); st.write("⚠️ 정답 미제공")
                            else:
                                st.markdown(f"**Q{i+1}.** {'⭕ 정답' if rev['is_c'] else '❌ 오답'}")
                                if not rev['is_c']: st.write(f"내 답: {rev['u']} / 정답: **{rev['c']}**")
                st.success(f"🎉 종료! {st.session_state.player_name}님 점수: {int(st.session_state.last_score)}점")
                st.button("다른 퀴즈 하기", on_click=lambda: st.rerun())