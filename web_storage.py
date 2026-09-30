"""Google Sheets storage for the standalone web application."""

from copy import deepcopy
from datetime import datetime, timedelta, timezone
from functools import wraps
import json
import re
import threading
import time
import uuid
from urllib.parse import urlsplit


class StorageError(RuntimeError):
    """A safe, user-visible storage failure; never include credentials."""


class StorageValidationError(ValueError):
    """Only validation messages authored here may cross the API boundary."""


SCHEMAS = {
    'Quizzes': ['Category', 'Title', 'Content', 'CreatedAt'],
    'Results': ['QuizTitle', 'User', 'Score', 'Duration', 'Time'],
    'WrongAnswers': ['QuizTitle', 'User', 'QuestionText', 'Status', 'CreatedAt'],
    'WrongAnswers_Logs': ['Time', 'User', 'Category', 'Quiz Title', 'Passage', 'Question', 'Options', 'Answer', 'Explanation'],
    'Chats': ['User', 'Message', 'Time'],
    'Settings': ['Key', 'Value'],
}
BACKUP_PREFIX = '스마트평가센터_백업_'
BACKUP_PREFIXES = (BACKUP_PREFIX, '퀴즈_백업_')


def _now():
    return datetime.now(timezone(timedelta(hours=9))).strftime('%Y-%m-%d %H:%M:%S')


def _operation(*, write=False):
    def decorate(fn):
        @wraps(fn)
        def run(self, *args, **kwargs):
            # This lock also covers cache fills: a read started before a write
            # cannot put its older snapshot back after the write finishes.
            with self._lock:
                try:
                    return fn(self, *args, **kwargs)
                except (StorageError, StorageValidationError):
                    raise
                except Exception as exc:
                    raise StorageError('Google Sheets 작업에 실패했습니다. 연결 설정과 접근 권한을 확인해 주세요.') from exc
                finally:
                    if write:
                        # Failed requests may already have committed remotely.
                        self._cache.clear()
        return run
    return decorate


class SheetsStorage:
    def __init__(self, config, *, client=None, ttl=30):
        self.config = config
        self._client = client
        self._book = None
        self._lock = threading.RLock()
        self._cache = {}
        self._ttl = ttl

    def _connect(self):
        if not self.config.sheet_id:
            raise StorageError('Google Sheets 연결 설정을 확인해 주세요.')
        if self._client is None:
            if not self.config.gcp_json:
                raise StorageError('Google Sheets 연결 설정을 확인해 주세요.')
            try:
                import gspread
                credentials = self.config.gcp_json
                if isinstance(credentials, str):
                    credentials = json.loads(credentials, strict=False)
                self._client = gspread.service_account_from_dict(credentials)
                self._client.set_timeout(15)
            except Exception as exc:
                self._client = None
                raise StorageError('Google Sheets 연결 설정을 확인해 주세요.') from exc
        if self._book is None:
            try:
                self._book = self._client.open_by_key(self.config.sheet_id)
            except Exception as exc:
                raise StorageError('Google Sheets에 연결하지 못했습니다. 연결 설정과 접근 권한을 확인해 주세요.') from exc
        return self._book

    def _worksheet(self, title, *, create=False):
        book = self._connect()
        try:
            return book.worksheet(title)
        except Exception as exc:
            if type(exc).__name__ != 'WorksheetNotFound':
                raise
            if not create:
                return None
            ws = book.add_worksheet(title=title, rows=1000, cols=max(20, len(SCHEMAS[title])))
            ws.append_row(SCHEMAS[title], value_input_option='RAW')
            return ws

    def _cached(self, key, factory):
        entry = self._cache.get(key)
        if entry is None or time.monotonic() >= entry[0]:
            value = factory()
            entry = (time.monotonic() + self._ttl, deepcopy(value))
            self._cache[key] = entry
        return deepcopy(entry[1])

    @staticmethod
    def _records(ws):
        if ws is None:
            return []
        values = ws.get_all_values(value_render_option='UNFORMATTED_VALUE')
        if not values:
            return []
        headers = values[0]
        nonempty = [h for h in headers if h != '']
        if len(set(nonempty)) != len(nonempty):
            raise StorageError('시트에 중복된 열 이름이 있습니다. 데이터 구조를 확인해 주세요.')
        return [{key: row[i] if i < len(row) else '' for i, key in enumerate(headers) if key != ''}
                for row in values[1:]]

    def _read(self, title):
        return self._cached(title, lambda: self._records(self._worksheet(title)))

    @_operation()
    def quizzes(self):
        return sorted(self._read('Quizzes'), key=lambda r: str(r.get('CreatedAt', '')), reverse=True)

    @_operation()
    def results(self):
        records = self._read('Results')
        for record in records:
            for key in ('Score', 'Duration'):
                try:
                    record[key] = int(round(float(record[key])))
                except (KeyError, TypeError, ValueError, OverflowError):
                    pass
        return records

    @_operation()
    def wrongs(self):
        return self._read('WrongAnswers')

    @_operation()
    def chats(self):
        return self._read('Chats')[-50:]

    @_operation()
    def settings(self):
        return {str(r['Key']): r.get('Value', '') for r in self._read('Settings') if r.get('Key') != ''}

    @staticmethod
    def _column(index):
        result = ''
        while index:
            index, remainder = divmod(index - 1, 26)
            result = chr(65 + remainder) + result
        return result

    def _headers(self, ws, required):
        values = ws.get_all_values(value_render_option='UNFORMATTED_VALUE')
        headers = list(values[0]) if values else []
        nonempty = [h for h in headers if h != '']
        if len(set(nonempty)) != len(nonempty):
            raise StorageError('시트에 중복된 열 이름이 있습니다.')
        amended = headers + [key for key in required if key not in headers]
        if amended != headers:
            if ws.col_count < len(amended):
                ws.resize(cols=len(amended))
            ws.update(values=[amended], range_name='A1', value_input_option='RAW')
        return amended

    def _append(self, title, records, attempt_id=None):
        if not records:
            return
        ws = self._worksheet(title, create=True)
        required = SCHEMAS[title] + (['AttemptID'] if attempt_id else [])
        headers = self._headers(ws, required)
        if attempt_id:
            existing = [r for r in self._records(ws) if str(r.get('AttemptID', '')) == attempt_id]
            if existing:
                if len(existing) != len(records):
                    raise StorageError('일부 응시 기록만 확인되었습니다. 관리자에게 응시 기록 확인을 요청해 주세요.')
                return
        rows = []
        for record in records:
            data = dict(record)
            if attempt_id:
                data['AttemptID'] = attempt_id
            rows.append([data.get(key, '') for key in headers])
        ws.append_rows(rows, value_input_option='RAW')

    def _patch_row(self, ws, index, changes):
        headers = self._headers(ws, list(changes))
        # Update only owned cells; unknown columns and formula cells survive.
        for key, value in changes.items():
            cell = f'{self._column(headers.index(key) + 1)}{index}'
            ws.update(values=[[value]], range_name=cell, value_input_option='RAW')

    @staticmethod
    def _validate_quiz(title, category, content):
        from quiz_core import validate_quiz_text
        questions, errors = validate_quiz_text(content)
        if not title.strip() or not category.strip() or errors or not questions:
            raise StorageValidationError('제목·분류·문제 형식을 확인해 주세요.')

    @_operation(write=True)
    def save_quiz(self, title, category, content):
        title, category = title.strip(), category.strip()
        self._validate_quiz(title, category, content)
        if any(str(r.get('Title')) == title for r in self._records(self._worksheet('Quizzes'))):
            raise StorageValidationError('같은 제목의 퀴즈가 있습니다. 다른 제목을 입력해 주세요.')
        self._append('Quizzes', [{'Category': category, 'Title': title, 'Content': content, 'CreatedAt': _now()}])
        return True

    @_operation(write=True)
    def update_quiz(self, title, category, content):
        self._validate_quiz(title, category, content)
        ws = self._worksheet('Quizzes')
        for index, row in enumerate(self._records(ws), 2):
            if str(row.get('Title')) == title:
                self._patch_row(ws, index, {'Category': category.strip(), 'Content': content})
                return True
        return False

    @_operation(write=True)
    def delete_quiz(self, title):
        ws = self._worksheet('Quizzes')
        for index, row in enumerate(self._records(ws), 2):
            if str(row.get('Title')) == title:
                ws.delete_rows(index)
                return True
        return False

    @_operation(write=True)
    def save_attempt(self, attempt_id, title, category, user, score, duration, questions, review):
        if not attempt_id or len(questions) != len(review):
            raise StorageValidationError('응시 기록을 확인해 주세요.')
        now = _now()
        self._append('Results', [{'QuizTitle': title, 'User': user, 'Score': int(round(score)),
                                'Duration': int(round(duration)), 'Time': now}], attempt_id)
        wrongs, logs = [], []
        for question, item in zip(questions, review):
            if item['correct']:
                continue
            wrongs.append({'QuizTitle': title, 'User': user, 'QuestionText': question.get('q', item['question']),
                           'Status': '오답', 'CreatedAt': now})
            logs.append({'Time': now, 'User': user, 'Category': category, 'Quiz Title': title,
                         'Passage': question.get('p', ''), 'Question': question.get('q', item['question']),
                         'Options': ', '.join(map(str, question.get('o', []))),
                         'Answer': str(item['correct_answer']), 'Explanation': item.get('explanation', '')})
        self._append('WrongAnswers', wrongs, attempt_id)
        self._append('WrongAnswers_Logs', logs, attempt_id)
        return True

    @_operation(write=True)
    def set_wrong_status(self, user, title, question, status):
        if status not in ('정복', '보관', '오답'):
            raise StorageValidationError('오답 상태를 확인해 주세요.')
        ws = self._worksheet('WrongAnswers')
        matches = []
        for index, row in enumerate(self._records(ws), 2):
            if (str(row.get('User')) == str(user) and str(row.get('QuizTitle')) == str(title)
                    and str(row.get('QuestionText')) == str(question) and row.get('Status') == '오답'):
                matches.append(index)
        if not matches:
            return False
        headers = self._headers(ws, ['Status'])
        column = self._column(headers.index('Status') + 1)
        ws.batch_update([{'range': f'{column}{index}', 'values': [[status]]} for index in matches],
                        value_input_option='RAW')
        return True

    @_operation(write=True)
    def save_chat(self, user, message):
        self._append('Chats', [{'User': user, 'Message': message, 'Time': _now()}])
        return True

    @_operation(write=True)
    def save_settings(self, settings):
        ws = self._worksheet('Settings', create=True)
        existing = self._records(ws)
        for key, value in settings.items():
            matches = [i for i, r in enumerate(existing, 2) if str(r.get('Key')) == str(key)]
            if len(matches) > 1:
                raise StorageError('설정 키가 중복되어 저장할 수 없습니다.')
            if matches:
                self._patch_row(ws, matches[0], {'Value': value})
            else:
                self._append('Settings', [{'Key': key, 'Value': value}])
        return True

    def _backup_files(self):
        self._connect()
        return [f for f in self._client.list_spreadsheet_files()
                if f['id'] != self.config.sheet_id and f['name'].startswith(BACKUP_PREFIXES)]

    @_operation()
    def backups(self):
        return self._cached('backups', lambda: sorted([f['name'] for f in self._backup_files()], reverse=True))

    @_operation(write=True)
    def create_backup(self, name):
        name = str(name).strip()
        if not name or len(name) > 200:
            raise StorageValidationError('백업 이름을 확인해 주세요.')
        full_name = name if name.startswith(BACKUP_PREFIX) else BACKUP_PREFIX + name
        if any(f['name'] == full_name for f in self._backup_files()):
            raise StorageValidationError('같은 이름의 백업이 있습니다. 다른 이름을 입력해 주세요.')
        backup_url = str(getattr(self.config, 'backup_url', '') or '').strip()
        if backup_url:
            parsed = urlsplit(backup_url)
            if (parsed.scheme != 'https' or parsed.netloc != 'script.google.com'
                    or not re.fullmatch(r'/macros/s/[A-Za-z0-9_-]+/(?:exec|dev)', parsed.path)
                    or parsed.fragment):
                raise StorageError('Google Apps Script 백업 연결 주소를 확인해 주세요.')
            import requests
            response = requests.get(backup_url, params={'name': full_name}, timeout=15)
            response.raise_for_status()
        else:
            self._client.copy(self.config.sheet_id, title=full_name, copy_permissions=False)
        # A successful HTTP response (including a script's text response) is not
        # evidence that an accessible safety copy exists. Bypass the TTL cache.
        created = [f for f in self._backup_files() if f['name'] == full_name]
        if len(created) != 1:
            raise StorageError('생성된 백업 파일을 하나로 확인하지 못했습니다. 백업 목록과 접근 권한을 확인해 주세요.')
        return full_name

    @staticmethod
    def _snapshot(book):
        # Preserve legacy data-only restore semantics. RAW writes must receive
        # evaluated values; otherwise formulas become visible literal strings.
        # The durable Drive copy also retains original formulas and formatting.
        return {ws.title: ws.get_all_values(value_render_option='UNFORMATTED_VALUE') for ws in book.worksheets()}

    @staticmethod
    def _validate_snapshot(snapshot):
        if not snapshot or 'Quizzes' not in snapshot:
            raise StorageError('복구할 백업에 Quizzes 시트가 없습니다.')
        for title, rows in snapshot.items():
            if not isinstance(rows, list) or any(not isinstance(row, list) for row in rows):
                raise StorageError('백업 데이터 형식이 올바르지 않습니다.')
            if title in SCHEMAS:
                if not rows or not set(SCHEMAS[title]).issubset(rows[0]):
                    raise StorageError(f'백업의 {title} 시트에 필수 열이 없습니다.')
                nonempty = [key for key in rows[0] if key != '']
                if len(nonempty) != len(set(nonempty)):
                    raise StorageError('백업에 중복된 열 이름이 있습니다.')
            if any(any(not isinstance(cell, (str, int, float, bool)) for cell in row) for row in rows):
                raise StorageError('백업 셀 데이터 형식이 올바르지 않습니다.')

    def _replace_snapshot(self, book, snapshot, *, best_effort=False, remove_extra=False):
        errors = []
        for title, values in snapshot.items():
            try:
                ws = next((item for item in book.worksheets() if item.title == title), None)
                if ws is None:
                    ws = book.add_worksheet(title=title, rows=max(1000, len(values)),
                                            cols=max(20, max(map(len, values), default=0)))
                elif len(values) > ws.row_count or max(map(len, values), default=0) > ws.col_count:
                    ws.resize(rows=max(ws.row_count, len(values)), cols=max(ws.col_count, max(map(len, values), default=0)))
                ws.clear()
                if values:
                    ws.update(values=values, range_name='A1', value_input_option='RAW')
            except Exception:
                errors.append(title)
                if not best_effort:
                    raise
        for ws in book.worksheets():
            if remove_extra and ws.title not in snapshot:
                try:
                    book.del_worksheet(ws)
                except Exception:
                    errors.append(ws.title)
                    if not best_effort:
                        raise
        return errors

    @_operation(write=True)
    def restore_backup(self, name):
        if not str(name).startswith(BACKUP_PREFIXES):
            raise StorageValidationError('이 앱에서 만든 백업만 복구할 수 있습니다.')
        matches = [f for f in self._backup_files() if f['name'] == name]
        if len(matches) != 1:
            raise StorageValidationError('백업이 없거나 같은 이름의 백업이 여러 개입니다. 이름을 확인해 주세요.')
        backup = self._client.open_by_key(matches[0]['id'])
        incoming = self._snapshot(backup)
        self._validate_snapshot(incoming)
        main = self._connect()
        previous = self._snapshot(main)
        snapshot_name = self.create_backup('복구전_' + datetime.now().strftime('%Y%m%d_%H%M%S') + '_' + uuid.uuid4().hex[:8])
        try:
            self._replace_snapshot(main, incoming)
        except Exception as exc:
            try:
                failures = self._replace_snapshot(main, previous, best_effort=True, remove_extra=True)
            except Exception:
                failures = ['시트 목록']
            if failures:
                raise StorageError(f'복구 실패 후 일부 시트를 되돌리지 못했습니다 ({", ".join(failures)}). 복구 전 백업: {snapshot_name}') from exc
            raise StorageError(f'복구에 실패하여 이전 데이터로 되돌렸습니다. 복구 전 백업: {snapshot_name}') from exc
        return True
