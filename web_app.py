"""Same-origin responsive quiz API. Run ONE worker: attempts/sessions live in memory."""
from __future__ import annotations

import hashlib
import hmac
import json
import math
import mimetypes
from functools import wraps
from datetime import datetime
from pathlib import Path
import secrets
import re
from threading import RLock
import time

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field

from prompts import EXTERNAL_PROMPT_TEMPLATE, VIEW_OPTIONS, DEFAULT_CATEGORY
from quiz_core import check_subjective_answer, validate_quiz_text, natural_sort_key
from web_config import WebConfig, load_config
from web_storage import SheetsStorage, StorageError


class Input(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)


class UserInput(Input):
    user: str = Field(min_length=1, max_length=80)


class AttemptInput(UserInput):
    quiz_id: str = Field(min_length=1, max_length=128)


class SubmitInput(Input):
    answers: list[str] = Field(max_length=300)
    allow_unanswered: bool = Field(default=False, strict=True)


class QuizInput(Input):
    title: str = Field(min_length=1, max_length=150)
    category: str = Field(min_length=1, max_length=100)
    content: str = Field(min_length=1, max_length=200000)


class LoginInput(Input):
    password: str = Field(max_length=1024)


class AnswerInput(UserInput):
    answer: str = Field(min_length=1, max_length=4000)


class ChatInput(UserInput):
    message: str = Field(min_length=1, max_length=2000)


class SettingsInput(Input):
    settings: dict[str, str | int | float | bool]


class BackupInput(Input):
    name: str = Field(min_length=1, max_length=150)


class RestoreInput(BackupInput):
    confirmation: str = Field(max_length=150)


PUBLIC_DEFAULTS = {'default_view': VIEW_OPTIONS[0], 'default_category': DEFAULT_CATEGORY,
                   'custom_categories': '', 'season_start': '2000-01-01', 'top_achievers_count': 3}


def setting_value(key, value):
    if key == 'top_achievers_count':
        if isinstance(value, bool) or not re.fullmatch(r'\d+(?:\.0+)?', str(value)):
            raise ValueError('우수 성취자 수는 1~1000 사이의 정수로 입력해 주세요.')
        result = int(float(value))
        if not 1 <= result <= 1000:
            raise ValueError('우수 성취자 수는 1~1000 사이의 정수로 입력해 주세요.')
        return result
    if not isinstance(value, str):
        raise ValueError('화면 설정과 날짜는 문자로 입력해 주세요.')
    value = value.strip()
    if key == 'season_start':
        if not re.fullmatch(r'\d{4}-\d{2}-\d{2}(?:[ T]\d{2}:\d{2}:\d{2})?', value):
            raise ValueError('시즌 시작일은 YYYY-MM-DD 형식의 날짜로 입력해 주세요.')
        try:
            parsed = datetime.fromisoformat(value)
        except ValueError:
            raise ValueError('시즌 시작일에 실제 존재하는 날짜를 입력해 주세요.') from None
        return parsed.strftime('%Y-%m-%d' if len(value) == 10 else '%Y-%m-%d %H:%M:%S')
    if key == 'default_view':
        if value not in VIEW_OPTIONS:
            raise ValueError('기본 화면은 제공된 메뉴 중에서 선택해 주세요.')
        return value
    if key == 'default_category':
        if len(value) > 100:
            raise ValueError('기본 분류는 100자 이내로 입력해 주세요.')
        return value
    if key == 'custom_categories':
        parts = list(dict.fromkeys(part.strip() for part in value.split(',') if part.strip()))
        if len(value) > 5000 or len(parts) > 50 or any(len(part) > 100 for part in parts):
            raise ValueError('분류는 각각 100자 이내, 최대 50개까지 입력해 주세요.')
        return ', '.join(parts)
    raise ValueError('지원하지 않는 설정 항목입니다.')


def public_settings(values):
    result = dict(PUBLIC_DEFAULTS)
    for key in result:
        if key in values:
            try:
                result[key] = setting_value(key, values[key])
            except (ValueError, OverflowError):
                pass
    return result


def quiz_id(title):
    return hashlib.sha256(str(title).encode()).hexdigest()[:24]


def wrong_id(user, title, question):
    return hashlib.sha256(json.dumps([user, title, question], ensure_ascii=False).encode()).hexdigest()[:32]


def number(value, default=0):
    try:
        value = float(value)
        return int(round(value)) if math.isfinite(value) else default
    except (ValueError, TypeError):
        return default


def grade(question, answer):
    if question['o'] == ['주관식']:
        expected = str(question['a'])
        correct = check_subjective_answer(answer, expected)
    else:
        expected = question['o'][question['a']]
        if answer and answer not in question['o']:
            raise HTTPException(422, '객관식 답은 제공된 보기에서 선택해 주세요.')
        correct = answer == expected
    return {'question': question['q'], 'answer': answer or '미응답', 'correct_answer': expected,
            'explanation': question['e'], 'correct': correct}


def create_app(storage=None, config: WebConfig | None = None, clock=time.monotonic):
    # Windows file associations can register .js as text/plain. With nosniff,
    # browsers then refuse every script. Serve deterministic web asset types.
    for suffix, media in {'.js': 'text/javascript', '.css': 'text/css', '.svg': 'image/svg+xml', '.woff2': 'font/woff2'}.items():
        mimetypes.add_type(media, suffix)
    config = config if config is not None else load_config()
    storage = storage if storage is not None else SheetsStorage(config)
    api = FastAPI(title='스마트 평가 센터', docs_url=None, redoc_url=None, openapi_url=None)
    lock = RLock()
    dataset_lock = RLock()
    sessions, attempts, login_limits = {}, {}, {}
    # Expose injected dependencies for integration fixtures, never as HTTP data.
    api.state.storage = storage
    cookie_name = 'smart_admin'

    def dataset_transaction(fn):
        @wraps(fn)
        def serialized(*args, **kwargs):
            # A restore must finish before another attempt can read or write.
            with dataset_lock:
                return fn(*args, **kwargs)
        return serialized

    def prune():
        now = clock()
        for key in [key for key, expiry in sessions.items() if expiry <= now]:
            sessions.pop(key, None)
        for key in [key for key, attempt in attempts.items() if attempt['expires'] <= now]:
            attempts.pop(key, None)
        for key in [key for key, times in login_limits.items() if not times or times[-1] <= now - 300]:
            login_limits.pop(key, None)

    def is_admin(request):
        with lock:
            token = request.cookies.get(cookie_name, '')
            return sessions.get(token, 0) > clock()

    def require_admin(request):
        if not is_admin(request):
            raise HTTPException(401, '관리자 로그인이 필요합니다.')

    def find_quiz(identifier):
        matches = [row for row in storage.quizzes() if quiz_id(row.get('Title', '')) == identifier]
        if not matches:
            raise HTTPException(404, '퀴즈를 찾을 수 없습니다.')
        if len(matches) != 1:
            raise HTTPException(409, '같은 제목의 퀴즈가 여러 개입니다. 시트에서 제목을 구분해 주세요.')
        return matches[0]

    def parsed_quiz(row):
        questions, errors = validate_quiz_text(row.get('Content', ''))
        if errors or not questions or len(questions) > 300:
            raise HTTPException(422, '문제 형식에 오류가 있습니다. 관리자가 내용을 수정한 후 다시 시작해 주세요.')
        return questions

    def normalized_results():
        return [{'quiz': str(r.get('QuizTitle', '')), 'user': str(r.get('User', '')),
                 'score': number(r.get('Score')), 'duration': number(r.get('Duration')),
                 'date': str(r.get('Time', ''))} for r in storage.results()]

    def find_wrong(identifier, user):
        for row in storage.wrongs():
            if str(row.get('User')) == user and row.get('Status') == '오답':
                title, text = str(row.get('QuizTitle', '')), str(row.get('QuestionText', ''))
                if wrong_id(user, title, text) == identifier:
                    return row
        raise HTTPException(404, '오답 기록을 찾을 수 없습니다.')

    def wrong_question(row, quizzes):
        matches = [q for q in quizzes if str(q.get('Title')) == str(row.get('QuizTitle'))]
        if len(matches) != 1:
            return None
        questions, errors = validate_quiz_text(matches[0].get('Content', ''))
        if errors:
            return None
        matches = [q for q in questions if q['q'] == str(row.get('QuestionText'))]
        return matches[0] if len(matches) == 1 else None

    @api.middleware('http')
    async def protect_origin(request: Request, call_next):
        if request.method in {'POST', 'PUT', 'PATCH', 'DELETE'}:
            origin = request.headers.get('origin', '')
            expected = f'{request.url.scheme}://{request.url.netloc}'
            if origin.rstrip('/') != expected or request.headers.get('sec-fetch-site') == 'cross-site':
                return JSONResponse({'detail': '다른 사이트에서 보낸 요청은 허용되지 않습니다. 이 페이지에서 다시 시도해 주세요.'}, status_code=403)
            if 'application/json' not in request.headers.get('content-type', '') and request.method != 'DELETE':
                return JSONResponse({'detail': '올바른 요청 형식으로 다시 시도해 주세요.'}, status_code=415)
            length = request.headers.get('content-length')
            if length and (not length.isdecimal() or int(length) > 1048576):
                return JSONResponse({'detail': '전송할 내용이 너무 큽니다.'}, status_code=413)
        response = await call_next(request)
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'DENY'
        response.headers['Referrer-Policy'] = 'same-origin'
        if request.url.path.startswith('/api/'):
            response.headers['Cache-Control'] = 'no-store'
        return response

    @api.exception_handler(RequestValidationError)
    async def invalid_request(request, exc):
        return JSONResponse({'detail': '입력 항목과 길이를 확인해 주세요. 필수 항목은 비워 둘 수 없습니다.'}, status_code=422)

    @api.exception_handler(StorageError)
    async def unavailable(request, exc):
        return JSONResponse({'detail': str(exc)}, status_code=503)

    @api.exception_handler(ValueError)
    async def invalid_operation(request, exc):
        return JSONResponse({'detail': '입력 내용을 확인해 주세요. 같은 이름의 항목이나 잘못된 데이터가 있을 수 있습니다.'}, status_code=422)

    @api.exception_handler(Exception)
    async def unexpected(request, exc):
        return JSONResponse({'detail': '요청을 처리하지 못했습니다. 잠시 후 다시 시도해 주세요.'}, status_code=500)

    @api.get('/api/bootstrap')
    def bootstrap(request: Request):
        try:
            if config.error:
                raise StorageError(config.error)
            rows = storage.quizzes()
            quizzes = []
            titles = [str(row.get('Title', '')) for row in rows]
            for row in rows:
                title = str(row.get('Title', ''))
                questions, errors = validate_quiz_text(row.get('Content', ''))
                quizzes.append({'id': quiz_id(title), 'title': title, 'category': str(row.get('Category', '공통')),
                                'count': len(questions), 'valid': bool(title and questions and not errors and len(questions) <= 300 and titles.count(title) == 1)})
            return {'quizzes': quizzes, 'admin': is_admin(request), 'connected': True, 'message': '', 'records_private': True,
                    'settings': public_settings(storage.settings())}
        except StorageError as exc:
            return {'quizzes': [], 'admin': is_admin(request), 'connected': False, 'message': str(exc), 'records_private': True,
                    'settings': dict(PUBLIC_DEFAULTS)}

    @api.post('/api/attempts')
    @dataset_transaction
    def start_attempt(body: AttemptInput):
        row = find_quiz(body.quiz_id)
        questions = parsed_quiz(row)
        with lock:
            prune()
            if len(attempts) >= 2000:
                raise HTTPException(503, '진행 중인 평가가 많습니다. 잠시 후 다시 시도해 주세요.')
            identifier = secrets.token_urlsafe(24)
            started = clock()
            attempts[identifier] = {'title': str(row['Title']), 'category': str(row.get('Category', '')),
                                    'user': body.user, 'questions': questions, 'started': started,
                                    'expires': started + config.attempt_seconds, 'result': None, 'lock': RLock()}
        return {'attempt_id': identifier, 'title': row['Title'], 'questions': [{key: q[key] for key in ('p', 'q', 'o')} for q in questions],
                'started_at': time.time()}

    @api.post('/api/attempts/{identifier}/submit')
    @dataset_transaction
    def submit(identifier: str, body: SubmitInput):
        with lock:
            attempt = attempts.get(identifier)
            if attempt is None or attempt['expires'] <= clock():
                attempts.pop(identifier, None)
                raise HTTPException(410, '평가 세션이 만료되었습니다. 평가를 다시 시작해 주세요.')
        with attempt['lock']:
            if attempt['result'] is None:
                answers = [value.strip() for value in body.answers]
                if (len(answers) != len(attempt['questions']) or any(len(answer) > 4000 for answer in answers)
                        or (not body.allow_unanswered and any(not answer for answer in answers))):
                    raise HTTPException(422, '모든 문제에 답을 입력한 후 제출해 주세요.')
                review = [grade(question, answer) for question, answer in zip(attempt['questions'], answers)]
                correct = sum(item['correct'] for item in review)
                attempt['result'] = {'score': round(correct / len(review) * 100), 'duration': max(0, round(clock() - attempt['started'])),
                                     'correct': correct, 'total': len(review), 'review': review, 'saved': False, 'message': ''}
            result = attempt['result']
            if not result['saved']:
                try:
                    storage.save_attempt(identifier, attempt['title'], attempt['category'], attempt['user'], result['score'], result['duration'], attempt['questions'], result['review'])
                    result.update(saved=True, message='채점 결과와 오답을 저장했습니다.')
                except StorageError:
                    result.update(saved=False, message='채점은 완료했지만 저장하지 못했습니다. 이 화면에서 저장을 다시 시도해 주세요.')
            return dict(result)

    @api.get('/api/author/template')
    def template():
        return {'template': EXTERNAL_PROMPT_TEMPLATE}

    @api.post('/api/preview')
    def preview(body: QuizInput):
        questions, errors = validate_quiz_text(body.content)
        if len(questions) > 300:
            errors.append('퀴즈는 한 번에 300문제까지 등록할 수 있습니다.')
        return {'questions': questions, 'errors': errors, 'valid': bool(questions and not errors)}

    @api.post('/api/quizzes')
    def create_quiz(body: QuizInput, request: Request):
        require_admin(request)
        parsed_quiz({'Content': body.content})
        if any(str(row.get('Title')) == body.title for row in storage.quizzes()):
            raise HTTPException(409, '같은 제목의 퀴즈가 있습니다. 다른 제목을 입력해 주세요.')
        storage.save_quiz(body.title, body.category, body.content)
        return {'message': '퀴즈를 등록했습니다.'}

    @api.get('/api/quizzes/{identifier}/edit')
    def edit_quiz(identifier: str, request: Request):
        require_admin(request)
        row = find_quiz(identifier)
        return {'title': row['Title'], 'category': row.get('Category', ''), 'content': row.get('Content', '')}

    @api.patch('/api/quizzes/{identifier}')
    def update_quiz(identifier: str, body: QuizInput, request: Request):
        require_admin(request)
        row = find_quiz(identifier)
        if body.title != str(row['Title']):
            raise HTTPException(422, '기존 기록 연결을 위해 퀴즈 제목은 변경할 수 없습니다.')
        parsed_quiz({'Content': body.content})
        if storage.update_quiz(body.title, body.category, body.content) is False:
            raise HTTPException(404, '퀴즈가 변경되거나 삭제되었습니다. 목록을 새로고침해 주세요.')
        return {'message': '퀴즈를 수정했습니다.'}

    @api.delete('/api/quizzes/{identifier}')
    def delete_quiz(identifier: str, request: Request):
        require_admin(request)
        row = find_quiz(identifier)
        if storage.delete_quiz(str(row['Title'])) is False:
            raise HTTPException(404, '퀴즈가 이미 삭제되었습니다. 목록을 새로고침해 주세요.')
        return {'message': '퀴즈를 삭제했습니다. 기존 결과와 오답 기록은 유지됩니다.'}

    @api.post('/api/admin/login')
    def login(body: LoginInput, request: Request, response: Response):
        if not config.admin_password:
            raise HTTPException(503, '관리자 비밀번호 설정이 필요합니다. ADMIN_PASSWORD를 등록해 주세요.')
        identity = request.client.host if request.client else 'unknown'
        with lock:
            prune()
            failures = [stamp for stamp in login_limits.get(identity, []) if stamp > clock() - 300]
            if len(failures) >= 5:
                raise HTTPException(429, '로그인 시도가 너무 많습니다. 5분 후 다시 시도해 주세요.')
            if not hmac.compare_digest(body.password.encode(), config.admin_password.encode()):
                if len(login_limits) >= 10000 and identity not in login_limits:
                    raise HTTPException(429, '로그인 시도가 많습니다. 잠시 후 다시 시도해 주세요.')
                login_limits[identity] = failures + [clock()]
                raise HTTPException(401, '비밀번호가 일치하지 않습니다.')
            login_limits.pop(identity, None)
            sessions.pop(request.cookies.get(cookie_name, ''), None)
            if len(sessions) >= 1000:
                raise HTTPException(503, '관리자 세션이 많습니다. 잠시 후 다시 시도해 주세요.')
            token = secrets.token_urlsafe(32)
            sessions[token] = clock() + config.session_seconds
        response.set_cookie(cookie_name, token, httponly=True, secure=config.secure_cookie or request.url.scheme == 'https',
                            samesite='strict', max_age=config.session_seconds, path='/')
        return {'message': '관리자로 로그인했습니다.'}

    @api.post('/api/admin/logout')
    def logout(request: Request, response: Response):
        with lock:
            sessions.pop(request.cookies.get(cookie_name, ''), None)
        response.delete_cookie(cookie_name, path='/', httponly=True, samesite='strict')
        return {'message': '로그아웃했습니다.'}

    @api.get('/api/results')
    def results(request: Request, user: str = ''):
        require_admin(request)
        user = user.strip()
        records = normalized_results()
        if user:
            records = [row for row in records if row['user'] == user]
        return {'records': sorted(records, key=lambda row: row['date'], reverse=True)}

    @api.get('/api/leaderboard')
    def leaderboard(request: Request):
        require_admin(request)
        # Keep each learner's best attempt for each quiz.
        settings = public_settings(storage.settings())
        season_start = settings['season_start']
        top_count = settings['top_achievers_count']
        best = {}
        for row in normalized_results():
            try:
                record_date = setting_value('season_start', row['date'])
            except ValueError:
                continue
            if datetime.fromisoformat(record_date) < datetime.fromisoformat(season_start):
                continue
            key = row['quiz'], row['user']
            if key not in best or (-row['score'], row['duration']) < (-best[key]['score'], best[key]['duration']):
                best[key] = row
        counts, records = {}, []
        for row in sorted(best.values(), key=lambda row: (-row['score'], row['duration'], row['quiz'], row['user'])):
            count = counts.get(row['quiz'], 0)
            if count < top_count:
                records.append(row)
                counts[row['quiz']] = count + 1
        return {'records': records, 'season_start': season_start, 'top_count': top_count}

    @api.get('/api/participation')
    def participation(request: Request, category: str = '', exclude_guest: bool = True,
                      hide_empty: bool = True, only_participants: bool = True):
        require_admin(request)
        quiz_rows = storage.quizzes()
        categories = sorted({str(q.get('Category') or '미분류') for q in quiz_rows}, key=natural_sort_key)
        quizzes = sorted({str(q.get('Title', '')).strip() for q in quiz_rows
                          if not category or str(q.get('Category') or '미분류') == category}, key=natural_sort_key)
        users = {}
        admin = is_admin(request)
        # Preserve registration-only names without turning missing/non-numeric
        # scores into submitted zero-point attempts. Real zero scores do count.
        for record in storage.results():
            user = str(record.get('User', '')).strip()
            title = str(record.get('QuizTitle', '')).strip()
            if not user or 'test' in user.lower() or (exclude_guest and 'guest' in user.lower()):
                continue
            row = users.setdefault(user, {'user': user, 'completed': [], 'scores': {}})
            try:
                score = float(record.get('Score'))
            except (TypeError, ValueError):
                continue
            if title not in quizzes or not math.isfinite(score) or not 0 <= score <= 100:
                continue
            if title not in row['completed']:
                row['completed'].append(title)
            if admin:
                row['scores'][title] = max(row['scores'].get(title, 0), round(score))
        if hide_empty:
            completed = {title for row in users.values() for title in row['completed']}
            quizzes = [title for title in quizzes if title in completed]
        rows = [row for row in users.values() if not only_participants or row['completed']]
        return {'quizzes': quizzes, 'categories': categories,
                'rows': sorted(rows, key=lambda row: natural_sort_key(row['user']))}

    @api.get('/api/wrongs')
    def wrongs(request: Request, user: str = ''):
        require_admin(request)
        if not user.strip():
            raise HTTPException(422, '학습자 이름을 입력해 주세요.')
        quizzes = storage.quizzes()
        items, seen = [], set()
        for row in storage.wrongs():
            if str(row.get('User')) != user.strip() or row.get('Status') != '오답':
                continue
            title, text = str(row.get('QuizTitle', '')), str(row.get('QuestionText', ''))
            identifier = wrong_id(user.strip(), title, text)
            if identifier in seen:
                continue
            seen.add(identifier)
            question = wrong_question(row, quizzes)
            items.append({'id': identifier, 'quiz': title, 'question': text,
                          'options': question['o'] if question else [], 'passage': question['p'] if question else '', 'orphan': question is None})
        return {'items': items}

    @api.post('/api/wrongs/{identifier}/answer')
    def answer_wrong(identifier: str, body: AnswerInput, request: Request):
        require_admin(request)
        row = find_wrong(identifier, body.user)
        question = wrong_question(row, storage.quizzes())
        if question is None:
            raise HTTPException(422, '원본 문제가 없거나 변경되어 다시 풀 수 없습니다. 보관 처리해 주세요.')
        result = grade(question, body.answer)
        if result['correct']:
            if storage.set_wrong_status(body.user, str(row['QuizTitle']), str(row['QuestionText']), '정복') is False:
                raise HTTPException(409, '오답 기록이 변경되었습니다. 목록을 새로고침해 주세요.')
        return {key: result[key] for key in ('correct', 'correct_answer', 'explanation')} | {'message': '정답입니다. 오답 정복을 기록했습니다.' if result['correct'] else '아쉽습니다. 해설을 읽고 다시 도전해 보세요.'}

    @api.post('/api/wrongs/{identifier}/archive')
    def archive_wrong(identifier: str, body: UserInput, request: Request):
        require_admin(request)
        row = find_wrong(identifier, body.user)
        if wrong_question(row, storage.quizzes()) is not None:
            raise HTTPException(422, '원본 문제가 있는 오답은 다시 풀어 정복해 주세요.')
        if storage.set_wrong_status(body.user, str(row['QuizTitle']), str(row['QuestionText']), '보관') is False:
            raise HTTPException(409, '오답 기록이 변경되었습니다. 목록을 새로고침해 주세요.')
        return {'message': '원본이 없는 오답을 보관했습니다.'}

    @api.get('/api/chat')
    def chats(request: Request):
        require_admin(request)
        return {'messages': [{'user': str(row.get('User', '')), 'message': str(row.get('Message', '')), 'time': str(row.get('Time', ''))} for row in storage.chats()][-50:]}

    @api.post('/api/chat')
    def chat(body: ChatInput, request: Request):
        require_admin(request)
        storage.save_chat(body.user, body.message)
        return {'message': '메시지를 등록했습니다.'}

    @api.get('/api/admin/settings')
    def get_settings(request: Request):
        require_admin(request)
        return {'settings': public_settings(storage.settings())}

    @api.put('/api/admin/settings')
    def put_settings(body: SettingsInput, request: Request):
        require_admin(request)
        if set(body.settings) - PUBLIC_DEFAULTS.keys():
            raise HTTPException(422, '지원하는 화면·시즌 설정만 변경할 수 있습니다.')
        try:
            validated = {key: setting_value(key, value) for key, value in body.settings.items()}
        except (ValueError, OverflowError) as exc:
            raise HTTPException(422, str(exc) if isinstance(exc, ValueError) else '설정값의 범위를 확인해 주세요.') from None
        storage.save_settings(validated)
        return {'message': '설정을 저장했습니다.'}

    @api.get('/api/admin/backups')
    def backups(request: Request):
        require_admin(request)
        return {'files': storage.backups()}

    @api.post('/api/admin/backups')
    def backup(body: BackupInput, request: Request):
        require_admin(request)
        storage.create_backup(body.name)
        return {'message': '백업을 만들었습니다.'}

    @api.post('/api/admin/restore')
    @dataset_transaction
    def restore(body: RestoreInput, request: Request):
        require_admin(request)
        if body.confirmation != body.name:
            raise HTTPException(422, '복구할 백업 이름을 정확히 입력해 주세요.')
        if body.name not in storage.backups():
            raise HTTPException(404, '백업을 찾을 수 없습니다.')
        storage.restore_backup(body.name)
        # A restore changes the dataset; pending pre-restore attempts must not reinsert old records.
        with lock:
            attempts.clear()
        return {'message': '백업을 복구했습니다. 진행 중이던 평가는 다시 시작해 주세요.'}

    static = Path(__file__).parent / 'static'
    @api.get('/')
    def index():
        if not (static / 'index.html').is_file():
            raise HTTPException(503, '화면 파일을 준비 중입니다. 잠시 후 다시 시도해 주세요.')
        return FileResponse(static / 'index.html')
    api.mount('/static', StaticFiles(directory=static, check_dir=False), name='static')
    return api


class LazyApplication:
    """Keep imports/test discovery free of real configuration and credentials."""
    def __init__(self):
        self.instance = None
        self.lock = RLock()

    async def __call__(self, scope, receive, send):
        if self.instance is None:
            with self.lock:
                if self.instance is None:
                    self.instance = create_app()
        await self.instance(scope, receive, send)


app = LazyApplication()
