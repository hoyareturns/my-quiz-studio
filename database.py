import streamlit as st
import gspread
import json
from datetime import datetime, timedelta

def get_kst_time():
    return (datetime.utcnow() + timedelta(hours=9)).strftime('%Y-%m-%d %H:%M:%S')

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

@st.cache_data(ttl=10)
def get_all_quizzes():
    ws = get_worksheet("Quizzes", ["Category", "Title", "Content", "CreatedAt"])
    if ws:
        return sorted(ws.get_all_records(), key=lambda x: x.get('CreatedAt', ''), reverse=True)
    return []

@st.cache_data(ttl=10)
def get_settings():
    ws = get_worksheet("Settings", ["Key", "Value"])
    if ws:
        return {r['Key']: r['Value'] for r in ws.get_all_records()}
    return {}

def save_setting(key, value):
    ws = get_worksheet("Settings")
    if ws:
        cell = ws.find(key, in_column=1)
        if cell: ws.update_cell(cell.row, 2, value)
        else: ws.append_row([key, value])
        get_settings.clear()

@st.cache_data(ttl=10)
def get_chats():
    ws = get_worksheet("Chats", ["User", "Message", "Time"])
    if ws: return ws.get_all_records()[-50:]
    return []

def save_chat(user, msg):
    ws = get_worksheet("Chats")
    if ws:
        ws.append_row([user, msg, get_kst_time()])
        get_chats.clear()

@st.cache_data(ttl=10)
def get_all_results():
    ws = get_worksheet("Results", ["QuizTitle", "User", "Score", "Duration", "Time"])
    if ws: return ws.get_all_records()
    return []

def save_quiz(title, cat, content):
    ws = get_worksheet("Quizzes")
    if ws:
        ws.append_row([cat, title, content, get_kst_time()])
        get_all_quizzes.clear()

def update_quiz(old_title, new_cat, new_tit):
    ws = get_worksheet("Quizzes")
    if ws:
        cell = ws.find(old_title, in_column=2)
        if cell:
            ws.update_cell(cell.row, 1, new_cat)
            ws.update_cell(cell.row, 2, new_tit)
            get_all_quizzes.clear()
            return True
    return False

def delete_quiz(title):
    ws = get_worksheet("Quizzes")
    if ws:
        cell = ws.find(title, in_column=2)
        if cell: 
            ws.delete_rows(cell.row)
            get_all_quizzes.clear()
            return True
    return False

def save_result(title, user, score, duration, wrongs_content):
    res_ws = get_worksheet("Results")
    if res_ws: 
        res_ws.append_row([title, user, score, round(duration, 2), get_kst_time()])
    
    if wrongs_content:
        wr_ws = get_worksheet("WrongAnswers", ["User", "QuizTitle", "QuestionText", "Status", "Time"])
        if wr_ws: 
            for q_text in wrongs_content:
                wr_ws.append_row([user, title, q_text, "최초틀림", get_kst_time()])
    
    get_all_results.clear()
    get_wrong_answers_by_user.clear()

@st.cache_data(ttl=5)
def get_wrong_answers_by_user(user):
    """특정 유저의 오답 목록 중 '맞춤'이 아닌 데이터만 가져오기"""
    ws = get_worksheet("WrongAnswers")
    if not ws: return []
    all_rows = ws.get_all_records()
    return [r for r in all_rows if str(r.get('User')) == str(user) and r.get('Status') != "맞춤"]

def update_wrong_answer_status(user, quiz_title, question_text, new_status):
    """오답의 상태를 업데이트 (맞춤/다시틀림)"""
    ws = get_worksheet("WrongAnswers")
    if not ws: return False
    try:
        all_data = ws.get_all_records()
        for i, row in enumerate(all_data):
            if (str(row.get('User')) == str(user) and 
                str(row.get('QuizTitle')) == str(quiz_title) and 
                str(row.get('QuestionText')) == str(question_text) and
                str(row.get('Status')) != "맞춤"):
                # i+2 (헤더행 제외 및 1-based index)
                ws.update_cell(i + 2, 4, new_status)
                get_wrong_answers_by_user.clear()
                return True
    except: pass
    return False

def get_all_users_from_results():
    """드롭다운을 위한 전체 유저 아이디 가져오기"""
    ws = get_worksheet("Results")
    if not ws: return []
    data = ws.get_all_records()
    return sorted(list(set(str(r.get('User')) for r in data if r.get('User'))))
