import streamlit as st
import gspread
import json
from datetime import datetime, timedelta
from collections import Counter
import re

def get_kst_time():
    """한국 표준시(KST)를 반환합니다."""
    return (datetime.utcnow() + timedelta(hours=9)).strftime('%Y-%m-%d %H:%M:%S')

@st.cache_resource
def get_gspread_client():
    """구글 시트 API 클라이언트를 인증하고 반환합니다."""
    try:
        creds = json.loads(st.secrets["GCP_JSON"], strict=False)
        return gspread.service_account_from_dict(creds).open_by_key(st.secrets["SHEET_ID"])
    except Exception as e:
        st.error(f"구글 시트 연결 오류: {e}")
        return None

def get_worksheet(sheet_name, columns=None):
    """특정 워크시트를 가져오거나, 없으면 생성합니다."""
    try:
        sh = get_gspread_client()
        if not sh: return None
        try:
            return sh.worksheet(sheet_name)
        except gspread.exceptions.WorksheetNotFound:
            if columns:
                ws = sh.add_worksheet(title=sheet_name, rows="100", cols=len(columns))
                ws.append_row(columns)
                return ws
            return None
    except Exception as e:
        st.error(f"워크시트 접근 오류 ({sheet_name}): {e}")
        return None

# --- [1] 퀴즈(Quizzes) 관리 (IsWork 컬럼 지원) ---

@st.cache_data(ttl=10)
def get_all_quizzes():
    """모든 퀴즈 목록을 가져옵니다. IsWork 컬럼을 포함합니다."""
    ws = get_worksheet("Quizzes", ["Category", "Title", "Content", "CreatedAt", "IsWork"])
    if ws:
        return sorted(ws.get_all_records(), key=lambda x: x.get('CreatedAt', ''), reverse=True)
    return []

def save_quiz(category, title, content, is_work=False):
    """새 퀴즈를 저장합니다. IsWork는 5번째 컬럼에 저장됩니다."""
    ws = get_worksheet("Quizzes")
    if ws:
        work_flag = "O" if is_work else "X"
        ws.append_row([category, title, content, get_kst_time(), work_flag])
        get_all_quizzes.clear()

def update_quiz(old_title, new_cat, new_title, new_content, is_work=False):
    """기존 퀴즈를 수정합니다."""
    ws = get_worksheet("Quizzes")
    if ws:
        records = ws.get_all_records()
        for i, r in enumerate(records):
            if r.get('Title') == old_title:
                row_idx = i + 2
                ws.update_cell(row_idx, 1, new_cat)
                ws.update_cell(row_idx, 2, new_title)
                ws.update_cell(row_idx, 3, new_content)
                ws.update_cell(row_idx, 5, "O" if is_work else "X") # 5번째 IsWork 컬럼
                get_all_quizzes.clear()
                return True
    return False

def delete_quiz(title):
    """퀴즈를 삭제합니다."""
    ws = get_worksheet("Quizzes")
    if ws:
        records = ws.get_all_records()
        for i, r in enumerate(records):
            if r.get('Title') == title:
                ws.delete_rows(i + 2)
                get_all_quizzes.clear()
                return True
    return False

# --- [2] 결과(Results) 관리 ---

def save_result(quiz_title, user_name, score, duration, wrong_list):
    """시험 결과를 시트에 저장합니다."""
    ws = get_worksheet("Results", ["QuizTitle", "User", "Score", "Duration", "Wrongs", "Time"])
    if ws:
        ws.append_row([
            quiz_title, 
            user_name, 
            score, 
            round(duration, 1), 
            ",".join(map(str, wrong_list)), 
            get_kst_time()
        ])
        get_all_results.clear()

@st.cache_data(ttl=10)
def get_all_results():
    """모든 결과 데이터를 가져옵니다."""
    ws = get_worksheet("Results")
    if ws: return ws.get_all_records()
    return []

# --- [3] 채팅(Chats) 관리 ---

def save_chat(user_name, message):
    """채팅 메시지를 저장합니다."""
    ws = get_worksheet("Chats", ["User", "Message", "Time"])
    if ws:
        ws.append_row([user_name, message, get_kst_time()])
        get_chats.clear()

@st.cache_data(ttl=5)
def get_chats():
    """최근 채팅 50개를 가져옵니다."""
    ws = get_worksheet("Chats")
    if ws:
        data = ws.get_all_records()
        return data[-50:]
    return []

# --- [4] 설정(Settings) 관리 ---

def save_setting(key, value):
    """앱 설정을 저장하거나 업데이트합니다."""
    ws = get_worksheet("Settings", ["Key", "Value"])
    if ws:
        records = ws.get_all_records()
        for i, r in enumerate(records):
            if r.get('Key') == key:
                ws.update_cell(i + 2, 2, value)
                get_settings.clear()
                return
        ws.append_row([key, value])
        get_settings.clear()

@st.cache_data(ttl=10)
def get_settings():
    """모든 설정값을 가져옵니다."""
    ws = get_worksheet("Settings")
    if ws:
        return {r.get('Key'): r.get('Value') for r in ws.get_all_records() if r.get('Key')}
    return {}

# --- [5] 오답 정복(WrongAnswers) 관리 ---

def save_wrong_answers(quiz_title, user_name, wrong_questions):
    """틀린 문제 텍스트를 저장합니다."""
    ws = get_worksheet("WrongAnswers", ["QuizTitle", "User", "QuestionText", "Status", "CreatedAt"])
    if ws:
        for q_text in wrong_questions:
            ws.append_row([quiz_title, user_name, q_text, "오답", get_kst_time()])
        get_wrong_answers_by_user.clear()

@st.cache_data(ttl=5)
def get_wrong_answers_by_user(user_name):
    """특정 유저의 아직 '오답' 상태인 데이터만 가져옵니다."""
    ws = get_worksheet("WrongAnswers")
    if not ws: return []
    all_rows = ws.get_all_records()
    return [r for r in all_rows if str(r.get('User')) == str(user_name) and r.get('Status') == "오답"]

def update_wrong_answer_status(user_name, quiz_title, question_text, new_status):
    """문제를 맞혔을 때 상태를 '정복'으로 변경합니다."""
    ws = get_worksheet("WrongAnswers")
    if not ws: return False
    try:
        all_data = ws.get_all_records()
        for i, row in enumerate(all_data):
            if (str(row.get('User')) == str(user_name) and 
                str(row.get('QuizTitle')) == str(quiz_title) and 
                str(row.get('QuestionText')) == str(question_text) and
                row.get('Status') == "오답"):
                ws.update_cell(i + 2, 4, new_status)
                get_wrong_answers_by_user.clear()
                return True
        return False
    except:
        return False

def get_all_users_with_wrongs():
    """오답이 하나라도 있는 유저 목록을 가져옵니다."""
    ws = get_worksheet("WrongAnswers")
    if not ws: return []
    data = ws.get_all_records()
    return sorted(list({str(r.get('User')) for r in data if r.get('Status') == "오답"}))