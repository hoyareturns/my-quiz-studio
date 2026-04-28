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

# database.py 하단에 아래 내용을 추가해 주세요.

def save_wrong_answers(quiz_title, user_name, wrong_questions):
    """틀린 문제들을 WrongAnswers 시트에 저장합니다."""
    ws = get_worksheet("WrongAnswers", ["QuizTitle", "User", "QuestionText", "Status", "CreatedAt"])
    if ws:
        for q_text in wrong_questions:
            # 상태는 '오답'으로 저장
            ws.append_row([quiz_title, user_name, q_text, "오답", get_kst_time()])
        get_wrong_answers_by_user.clear()

@st.cache_data(ttl=5)
def get_wrong_answers_by_user(user_name):
    """특정 유저의 오답 목록 중 아직 정복하지 않은 것만 가져옵니다."""
    ws = get_worksheet("WrongAnswers")
    if not ws: return []
    all_rows = ws.get_all_records()
    # '오답' 상태인 데이터만 필터링
    return [r for r in all_rows if str(r.get('User')) == str(user_name) and r.get('Status') == "오답"]

def update_wrong_answer_status(user_name, quiz_title, question_text, new_status):
    """문제를 맞혔을 때 상태를 '정복'으로 업데이트합니다."""
    ws = get_worksheet("WrongAnswers")
    if not ws: return False
    try:
        all_data = ws.get_all_records()
        for i, row in enumerate(all_data):
            if (str(row.get('User')) == str(user_name) and 
                str(row.get('QuizTitle')) == str(quiz_title) and 
                str(row.get('QuestionText')) == str(question_text) and
                row.get('Status') == "오답"):
                # 시트 인덱스는 헤더 포함 1-based 이므로 i + 2
                ws.update_cell(i + 2, 4, new_status)
                get_wrong_answers_by_user.clear()
                return True
    except: pass
    return False

def get_all_users_with_wrongs():
    """오답 기록이 남아있는 유저 목록만 가져옵니다."""
    ws = get_worksheet("WrongAnswers")
    if not ws: return []
    data = ws.get_all_records()
    users = {str(r.get('User')) for r in data if r.get('Status') == "오답"}
    return sorted(list(users))

def reset_all_data():
    """모든 시트의 데이터를 1번 줄 제외하고 삭제"""
    sheet_names = ["Quizzes", "Results", "WrongAnswers"]
    
    try:
        for name in sheet_names:
            ws = get_worksheet(name)
            if ws:
                # 데이터가 있는지 확인 (헤더 제외 2행부터 데이터가 있는지)
                all_values = ws.get_all_values()
                if len(all_values) > 1:
                    # 2행부터 마지막 행까지 한 번에 삭제
                    ws.delete_rows(2, len(all_values))
        return True, "모든 데이터가 초기화되었습니다."
    except Exception as e:
        return False, f"초기화 중 오류 발생: {str(e)}"
    
def save_wrong_answers_detailed(quiz_title, category, player_name, wrong_items, kst_time_func):
    """신규 시트(WrongAnswers_Logs)에 오답의 모든 디테일을 기록"""
    ws = get_worksheet("WrongAnswers_Logs")
    if ws:
        rows = []
        for it in wrong_items:
            # 보기 리스트를 문자열로 변환
            options_str = ", ".join(it.get('o', [])) if isinstance(it.get('o'), list) else str(it.get('o'))
            
            rows.append([
                kst_time_func(),     # Time
                player_name,         # User
                category,            # Category
                quiz_title,          # Quiz Title
                it.get('p', ''),     # Passage (지문)
                it.get('q', ''),     # Question (질문)
                options_str,         # Options (보기)
                str(it.get('a', '')),# Answer (정답)
                it.get('e', '')      # Explanation (해설)
            ])
        
        if rows:
            ws.append_rows(rows)

@st.cache_data(ttl=60)
def get_unique_players():
    """Results 시트에서 중복 없는 유저 목록을 가져옵니다."""
    ws = get_worksheet("Results") # 시트 탭 이름이 'Results'인지 확인하세요
    if ws:
        try:
            records = ws.get_all_records()
            # 헤더 명칭을 'Name'에서 'User'로 변경
            names = list(set(str(r.get('User', '')).strip() for r in records if r.get('User')))
            return names
        except Exception as e:
            return []
    return []