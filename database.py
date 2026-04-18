import streamlit as st
import gspread
import json
from datetime import datetime, timedelta
from collections import Counter
import re

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
        # [핵심 로직] 채팅 작성 즉시 캐시 강제 삭제 (새로고침 불필요)
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

def save_result(title, user, score, duration, wrongs):
    res_ws = get_worksheet("Results")
    if res_ws: 
        res_ws.append_row([title, user, score, round(duration, 2), get_kst_time()])
    if wrongs:
        wr_ws = get_worksheet("WrongAnswers")
        if wr_ws: 
            [wr_ws.append_row([user, k, get_kst_time()]) for k in wrongs]
    
    # [핵심 로직] 성적 저장 즉시 캐시 강제 삭제
    get_all_results.clear()

# database.py 하단에 추가
@st.cache_data(ttl=10)
def get_wrong_answers_by_user(user_name):
    """특정 유저의 오답 목록을 가져옵니다."""
    ws = get_worksheet("WrongAnswers", ["QuizTitle", "User", "QuestionText", "Status", "CreatedAt"])
    if ws:
        all_data = ws.get_all_records()
        # 미정복(오답) 상태인 데이터만 필터링
        return [r for r in all_data if r['User'] == user_name and r['Status'] == "오답"]
    return []

def save_wrong_answers(quiz_title, user_name, wrong_questions):
    """틀린 문제들을 WrongAnswers 시트에 저장합니다."""
    ws = get_worksheet("WrongAnswers", ["QuizTitle", "User", "QuestionText", "Status", "CreatedAt"])
    if ws:
        for q_text in wrong_questions:
            # 중복 기록 방지 (이미 오답으로 등록된 동일 문제는 패스)
            ws.append_row([quiz_title, user_name, q_text, "오답", get_kst_time()])

def update_wrong_answer_status(user_name, quiz_title, q_text, new_status):
    """문제를 맞혔을 때 상태를 업데이트합니다."""
    ws = get_worksheet("WrongAnswers")
    if ws:
        try:
            # 유저, 퀴즈제목, 문제내용이 일치하는 행 찾기
            cells = ws.findall(user_name)
            for cell in cells:
                row_data = ws.row_values(cell.row)
                if row_data[0] == quiz_title and row_data[2] == q_text:
                    ws.update_cell(cell.row, 4, new_status) # Status 열 업데이트
                    break
        except:
            pass

def get_all_users_with_wrongs():
    """오답 기록이 있는 유저 목록만 가져옵니다."""
    ws = get_worksheet("WrongAnswers")
    if ws:
        data = ws.get_all_records()
        users = {r['User'] for r in data if r['Status'] == "오답"}
        return sorted(list(users))
    return []
