import streamlit as st
import gspread
import json
from datetime import datetime, timedelta, timezone
from collections import Counter
import re
import pandas as pd
from utils import get_secret

# 1. 기존 드라이브 전체 관리용 (새로 추가)
@st.cache_resource
def get_gspread_drive_client():
    """드라이브의 파일을 이름으로 검색/열기 위한 순수 드라이브 클라이언트"""
    creds = json.loads(get_secret("GCP_JSON") or "{}", strict=False)
    # gspread.service_account()는 드라이브 전체를 관리하는 객체를 반환합니다.
    return gspread.service_account_from_dict(creds)


@st.cache_data(ttl=60, show_spinner=False)
def get_backup_file_list():
    try:
        drive_client = get_gspread_drive_client()
        # 구글 계정(서비스 계정)이 접근할 수 있는 모든 스프레드시트 목록을 가져옵니다.
        all_files = drive_client.list_spreadsheet_files()
        
        # [핵심 로직]
        # 메인 운영 파일인 '우정 파괴소 데이터베이스'를 제외한 모든 파일을 가져옵니다.
        # (혹시 모를 띄어쓰기 차이를 대비해 두 가지 경우를 모두 제외합니다)
        file_names = [
            f['name'] for f in all_files 
            if f['name'] != "우정 파괴소 데이터베이스" and f['name'] != "우정파괴소 데이터베이스"
        ]
        
        # 리스트를 내림차순 정렬 (최신 날짜/시간이 포함된 파일이 맨 위로 올라옵니다)
        file_names.sort(reverse=True)
        
        return file_names
    except Exception as e:
        raise RuntimeError("백업 목록을 불러오지 못했습니다. 연결 설정을 확인해 주세요.") from e
    
# 3. 복구 함수 수정
def restore_database_from_backup(backup_filename):
    try:
        drive_client = get_gspread_drive_client()
        # 1. 원본(메인) 파일과 백업 파일을 엽니다.
        main_sheet = get_gspread_client()
        backup_sheet = drive_client.open(backup_filename)
        
        # 2. 백업 파일의 모든 시트를 순회하며 운영 파일에 복사합니다.
        for backup_ws in backup_sheet.worksheets():
            ws_title = backup_ws.title
            
            # 운영 파일에 해당 시트가 있는지 확인
            try:
                main_ws = main_sheet.worksheet(ws_title)
            except:
                # 없으면 생성
                main_ws = main_sheet.add_worksheet(title=ws_title, rows=1000, cols=20)
            
            # [핵심] 
            # 1. 데이터를 초기화하고 
            # 2. 서식까지 포함하여 통째로 업데이트
            main_ws.clear()
            data = backup_ws.get_all_values(value_render_option='UNFORMATTED_VALUE')
            main_ws.update(data, value_input_option='RAW')
            
        clear_data_cache()
        get_worksheet_cached.clear()
        return True
    except Exception as e:
        st.error('복구에 실패했습니다. 연결 상태와 시트 접근 권한을 확인해 주세요.')
        return False

def get_kst_time():
    return datetime.now(timezone(timedelta(hours=9))).strftime('%Y-%m-%d %H:%M:%S')

@st.cache_resource(ttl=60, show_spinner=False)
def get_gspread_client():
    try:
        raw, sheet_id = get_secret("GCP_JSON"), get_secret("SHEET_ID")
        if not raw or not sheet_id:
            return None
        creds = json.loads(raw, strict=False)
        return gspread.service_account_from_dict(creds).open_by_key(sheet_id)
    except: return None

@st.cache_resource(ttl=300, show_spinner=False)
def get_worksheet_cached(sheet_name):
    sh = get_gspread_client()
    if sh is None:
        raise RuntimeError("Google Sheets 연결 설정을 확인해 주세요.")
    return sh.worksheet(sheet_name)


def get_worksheet(sheet_name, columns=None):
    try:
        return get_worksheet_cached(sheet_name)
    except gspread.exceptions.WorksheetNotFound:
        if not columns:
            return None
        sh = get_gspread_client()
        ws = sh.add_worksheet(title=sheet_name, rows=1000, cols=len(columns))
        ws.append_row(list(columns), value_input_option="RAW")
        get_worksheet_cached.clear()
        return ws
    except RuntimeError:
        return None


def require_worksheet(sheet_name, columns=None):
    ws = get_worksheet(sheet_name, columns)
    if ws is None:
        raise RuntimeError("저장할 시트에 연결하지 못했습니다. 연결 설정을 확인해 주세요.")
    return ws


def append_attempt_once(ws, rows, attempt_id):
    """Reconcile a timed-out append before repeating it; retain legacy columns."""
    headers = ws.row_values(1)
    if "AttemptID" not in headers:
        column = len(headers) + 1
        if ws.col_count < column:
            ws.add_cols(column - ws.col_count)
        ws.update_cell(1, column, "AttemptID")
    else:
        column = headers.index("AttemptID") + 1
    if attempt_id in ws.col_values(column)[1:]:
        return
    payload = []
    for row in rows:
        values = list(row) + [""] * max(0, column - len(row))
        values[column - 1] = attempt_id
        payload.append(values)
    ws.append_rows(payload, value_input_option="RAW")


@st.cache_data(ttl=60, show_spinner=False)
def get_all_quizzes():
    ws = get_worksheet("Quizzes", ["Category", "Title", "Content", "CreatedAt"])
    if ws:
        return sorted(ws.get_all_records(), key=lambda x: x.get('CreatedAt', ''), reverse=True)
    return []

@st.cache_data(ttl=60, show_spinner=False)
def get_settings():
    ws = get_worksheet("Settings", ["Key", "Value"])
    if ws:
        return {r['Key']: r['Value'] for r in ws.get_all_records()}
    return {}

def save_setting(key, value):
    ws = get_worksheet("Settings")
    if ws:
        try:
            cell = ws.find(key, in_column=1)
            if cell: 
                ws.update_cell(cell.row, 2, value)
            else: 
                ws.append_row([key, value])
            get_settings.clear()
            # --- [수정 포인트] 성공 시 두 개의 값을 리턴합니다 ---
            return True, "설정이 성공적으로 저장되었습니다."
        except Exception as e:
            # --- [수정 포인트] 에러 발생 시에도 두 개의 값을 리턴합니다 ---
            return False, f"저장 중 오류 발생: {str(e)}"
    return False, "워크시트를 찾을 수 없습니다."

@st.cache_data(ttl=15, show_spinner=False)
def get_chats():
    ws = get_worksheet("Chats", ["User", "Message", "Time"])
    if ws: return ws.get_all_records()[-50:]
    return []

def save_chat(user, msg):
    ws = require_worksheet("Chats", ["User", "Message", "Time"])
    if ws:
        ws.append_row([user, msg, get_kst_time()])
        # [핵심 로직] 채팅 작성 즉시 캐시 강제 삭제 (새로고침 불필요)
        get_chats.clear()

@st.cache_data(ttl=30, show_spinner=False)
def get_all_results():
    """Results 시트의 모든 데이터를 가져오며, 점수와 시간을 정수로 정리합니다."""
    ws = get_worksheet("Results")
    if ws:
        try:
            records = ws.get_all_records()
            for r in records:
                # 점수(Score) 처리: 소수점이 있다면 반올림 후 정수로 변환
                if 'Score' in r and r['Score'] != "":
                    try:
                        r['Score'] = int(round(float(r['Score'])))
                    except: pass
                
                # 시간(Duration) 처리: 소수점이 있다면 반올림 후 정수로 변환
                if 'Duration' in r and r['Duration'] != "":
                    try:
                        r['Duration'] = int(round(float(r['Duration'])))
                    except: pass
            return records
        except Exception as e:
            return []
    return []

def save_quiz(title, cat, content):
    from utils import validate_quiz_text
    questions, errors = validate_quiz_text(content)
    if not title.strip() or not cat.strip() or errors or not questions:
        raise ValueError("제목·분류·문제 형식을 확인해 주세요.")
    get_all_quizzes.clear()
    if any(str(q.get("Title")) == title.strip() for q in get_all_quizzes()):
        raise ValueError("같은 제목의 퀴즈가 있습니다. 다른 제목을 입력해 주세요.")
    ws = require_worksheet("Quizzes", ["Category", "Title", "Content", "CreatedAt"])
    ws.append_row([cat.strip(), title.strip(), content, get_kst_time()], value_input_option="RAW")
    get_all_quizzes.clear()
    return True


def update_quiz(old_title, new_cat, new_tit, content=None):
    ws = get_worksheet("Quizzes")
    if ws:
        cell = ws.find(old_title, in_column=2)
        if cell:
            if content is not None:
                from utils import validate_quiz_text
                questions, errors = validate_quiz_text(content)
                if errors or not questions:
                    raise ValueError("문제 형식을 확인해 주세요.")
            # Titles identify results and wrong answers in the existing data model.
            if old_title != new_tit:
                raise ValueError("기록 연결을 위해 기존 퀴즈의 제목은 변경할 수 없습니다.")
            values = [[new_cat, new_tit, content]] if content is not None else [[new_cat, new_tit]]
            end = "C" if content is not None else "B"
            ws.update(range_name=f"A{cell.row}:{end}{cell.row}", values=values, value_input_option="RAW")
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

# database.py 하단에 아래 내용을 추가해 주세요.

def save_wrong_answers(quiz_title, user_name, wrong_questions, attempt_id=None):
    if not wrong_questions:
        return True
    ws = require_worksheet("WrongAnswers", ["QuizTitle", "User", "QuestionText", "Status", "CreatedAt"])
    now = get_kst_time()
    rows = [[quiz_title, user_name, q, "오답", now] for q in wrong_questions]
    if attempt_id:
        append_attempt_once(ws, rows, attempt_id)
    else:
        ws.append_rows(rows, value_input_option="RAW")
    get_all_wrong_answers.clear()
    get_wrong_answers_by_user.clear()
    return True


@st.cache_data(ttl=30, show_spinner=False)
def get_all_wrong_answers():
    ws = get_worksheet("WrongAnswers")
    return ws.get_all_records() if ws is not None else []


@st.cache_data(ttl=30, show_spinner=False)
def get_wrong_answers_by_user(user_name):
    return [r for r in get_all_wrong_answers() if str(r.get('User')) == str(user_name) and r.get('Status') == "오답"]


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
                get_all_wrong_answers.clear()
                get_wrong_answers_by_user.clear()
                return True
    except: pass
    return False

def get_all_users_with_wrongs():
    return sorted({str(r.get("User")) for r in get_all_wrong_answers() if r.get("Status") == "오답"})


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
        clear_data_cache()
        return True, "모든 데이터가 초기화되었습니다."
    except Exception as e:
        return False, f"초기화 중 오류 발생: {str(e)}"
    
def save_wrong_answers_detailed(quiz_title, category, player_name, wrong_items, kst_time_func, attempt_id=None):
    """신규 시트(WrongAnswers_Logs)에 오답의 모든 디테일을 기록"""
    ws = require_worksheet("WrongAnswers_Logs", ["Time", "User", "Category", "Quiz Title", "Passage", "Question", "Options", "Answer", "Explanation"])
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
            if attempt_id:
                append_attempt_once(ws, rows, attempt_id)
            else:
                ws.append_rows(rows, value_input_option="RAW")

@st.cache_data(ttl=30, show_spinner=False)
def get_unique_players():
    return sorted({str(r.get("User", "")).strip() for r in get_all_results() if r.get("User")})


def save_result(title, user, score, duration, wrongs=None, attempt_id=None):
    ws = require_worksheet("Results", ["QuizTitle", "User", "Score", "Duration", "Time"])
    row = [title, user, int(round(score)), int(round(duration)), get_kst_time()]
    if attempt_id:
        append_attempt_once(ws, [row], attempt_id)
    else:
        ws.append_row(row, value_input_option="RAW")
    # Wrong answers are saved by save_wrong_answers using the correct schema.
    get_all_results.clear()
    get_unique_players.clear()
    return True


def clear_data_cache():
    for fn in (get_all_quizzes, get_settings, get_chats, get_all_results,
               get_unique_players, get_all_wrong_answers, get_wrong_answers_by_user, get_backup_file_list):
        fn.clear()
