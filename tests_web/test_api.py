"""API contract tests: explicit fake storage/config, never production credentials."""
import copy
import importlib.util
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

from fastapi.testclient import TestClient

CONTENT = '[Q1] 합은?\n[O] ① 하나 ② 둘\n[A] ②\n[E] 더하기\n[Q2] 수도는?\n[O] 주관식\n[A] 서울 | Seoul\n[E] 수도'


class FakeStorage:
    def __init__(self):
        self.quiz_rows = [{'Title': '시험', 'Category': '공통', 'Content': CONTENT}]
        self.result_rows = []
        self.wrong_rows = []
        self.chat_rows = []
        self.config = {'default_category': '공통'}
        self.backup_names = ['스마트평가센터_백업_연습']
        self.attempts = {}
        self.fail_save = False
        self.disconnected = False

    def check(self):
        if self.disconnected:
            from web_storage import StorageError
            raise StorageError('연결할 수 없습니다.')

    def quizzes(self): self.check(); return copy.deepcopy(self.quiz_rows)
    def results(self): self.check(); return copy.deepcopy(self.result_rows)
    def wrongs(self): self.check(); return copy.deepcopy(self.wrong_rows)
    def chats(self): self.check(); return copy.deepcopy(self.chat_rows)
    def settings(self): self.check(); return self.config.copy()
    def backups(self): self.check(); return self.backup_names[:]

    def save_attempt(self, attempt_id, title, category, user, score, duration, questions, review):
        self.check()
        if self.fail_save:
            from web_storage import StorageError
            raise StorageError('저장 실패')
        self.attempts[attempt_id] = (score, copy.deepcopy(review))

    def save_quiz(self, title, category, content):
        self.quiz_rows.append({'Title': title, 'Category': category, 'Content': content})
    def update_quiz(self, title, category, content):
        row = next(row for row in self.quiz_rows if row['Title'] == title)
        row.update(Category=category, Content=content)
    def delete_quiz(self, title): self.quiz_rows = [r for r in self.quiz_rows if r['Title'] != title]
    def set_wrong_status(self, user, title, question, status):
        row = next(r for r in self.wrong_rows if r['User'] == user and r['QuizTitle'] == title and r['QuestionText'] == question)
        row['Status'] = status
    def save_chat(self, user, message): self.chat_rows.append({'User': user, 'Message': message, 'Time': '오늘'})
    def save_settings(self, settings): self.config.update(settings)
    def create_backup(self, name): self.backup_names.append(name)
    def restore_backup(self, name): self.restored = name


class ApiTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(importlib.util.find_spec('web_app'), 'FastAPI backend is not implemented')
        from web_app import create_app
        from web_config import WebConfig
        self.now = 1000.0
        self.store = FakeStorage()
        self.app = create_app(self.store, WebConfig(admin_password='test-only', session_seconds=10, attempt_seconds=100), clock=lambda: self.now)
        self.client = TestClient(self.app, headers={'Origin': 'http://testserver'})
        self.quiz_id = self.client.get('/api/bootstrap').json()['quizzes'][0]['id']

    def login(self):
        return self.client.post('/api/admin/login', json={'password': 'test-only'})

    def attempt(self):
        return self.client.post('/api/attempts', json={'quiz_id': self.quiz_id, 'user': '학생'})

    def test_attempt_hides_keys_and_server_grades_option_text(self):
        attempt = self.attempt().json()
        self.assertEqual(set(attempt['questions'][0]), {'p', 'q', 'o'})
        self.now += 21
        result = self.client.post(f"/api/attempts/{attempt['attempt_id']}/submit", json={'answers': ['둘', 'Seoul']}).json()
        self.assertEqual((result['score'], result['correct'], result['duration']), (100, 2, 21))
        self.assertTrue(result['saved'])

    def test_windows_file_associations_cannot_disable_frontend_scripts(self):
        import mimetypes
        from web_app import create_app
        from web_config import WebConfig
        mimetypes.add_type('text/plain', '.js')
        client = TestClient(create_app(FakeStorage(), WebConfig()))
        response = client.get('/static/app.js')
        self.assertEqual(response.status_code, 200)
        self.assertIn('javascript', response.headers['content-type'])
        self.assertEqual(response.headers['x-content-type-options'], 'nosniff')

    def test_missing_and_forged_answers_cannot_be_submitted(self):
        aid = self.attempt().json()['attempt_id']
        for answers in [['둘'], ['둘', ' '], ['outside-options', '서울']]:
            response = self.client.post(f'/api/attempts/{aid}/submit', json={'answers': answers})
            self.assertEqual(response.status_code, 422)
        self.assertEqual(self.store.attempts, {})

    def test_failed_save_retains_original_grade_for_idempotent_retry(self):
        aid = self.attempt().json()['attempt_id']
        self.store.fail_save = True
        first = self.client.post(f'/api/attempts/{aid}/submit', json={'answers': ['하나', '서울']}).json()
        self.assertFalse(first['saved'])
        self.store.fail_save = False
        self.now += 30
        second = self.client.post(f'/api/attempts/{aid}/submit', json={'answers': ['둘', '서울']}).json()
        self.assertTrue(second['saved'])
        self.assertEqual((second['score'], second['duration'], second['review']), (first['score'], first['duration'], first['review']))
        self.client.post(f'/api/attempts/{aid}/submit', json={'answers': ['둘', '서울']})
        self.assertEqual(len(self.store.attempts), 1)

    def test_explicit_blank_submission_grades_blanks_wrong_and_retry_is_stable(self):
        aid = self.attempt().json()['attempt_id']
        self.store.fail_save = True
        first = self.client.post(f'/api/attempts/{aid}/submit', json={
            'answers': ['', '서울'], 'allow_unanswered': True})
        self.assertEqual(first.status_code, 200)
        result = first.json()
        self.assertEqual((result['score'], result['correct'], result['total']), (50, 1, 2))
        self.assertFalse(result['review'][0]['correct'])
        self.assertEqual(result['review'][0]['answer'], '미응답')
        self.assertEqual(result['review'][0]['correct_answer'], '둘')
        self.store.fail_save = False
        retry = self.client.post(f'/api/attempts/{aid}/submit', json={'answers': ['', '서울']}).json()
        self.assertTrue(retry['saved'])
        self.assertEqual(retry['review'], result['review'])

    def test_blank_opt_in_does_not_allow_wrong_answer_count_or_forged_options(self):
        for answers in [[], ['서울'], ['forged', ''], ['', '']]:
            aid = self.attempt().json()['attempt_id']
            response = self.client.post(f'/api/attempts/{aid}/submit', json={
                'answers': answers, 'allow_unanswered': True})
            self.assertEqual(response.status_code, 200 if answers == ['', ''] else 422)
            if response.status_code == 200:
                self.assertEqual(response.json()['score'], 0)

    def test_participation_filters_restore_legacy_rules_and_keep_real_zero_scores(self):
        self.login()
        self.store.quiz_rows += [
            {'Title': '미풀이', 'Category': '공통', 'Content': CONTENT},
            {'Title': '수학시험', 'Category': '수학', 'Content': CONTENT}]
        self.store.result_rows = [
            {'QuizTitle':'등록','User':'등록만','Score':0},
            {'QuizTitle':'시험','User':'빈점수','Score':''},
            {'QuizTitle':'시험','User':'문자점수','Score':'등록'},
            {'QuizTitle':'시험','User':'영점참여','Score':0},
            {'QuizTitle':'시험','User':'학생','Score':90},
            {'QuizTitle':'수학시험','User':'수학학생','Score':80},
            {'QuizTitle':'미풀이','User':'Guest01','Score':100},
            {'QuizTitle':'미풀이','User':'myTESTaccount','Score':100}]
        data = self.client.get('/api/participation', params={'category':'공통'}).json()
        self.assertEqual(data['quizzes'], ['시험'])
        self.assertEqual({r['user'] for r in data['rows']}, {'영점참여','학생'})
        self.assertIn('수학', data['categories'])
        all_data = self.client.get('/api/participation', params={
            'category':'공통','only_participants':'false','hide_empty':'false','exclude_guest':'false'}).json()
        self.assertEqual(set(all_data['quizzes']), {'시험','미풀이'})
        rows = {r['user']:r for r in all_data['rows']}
        self.assertNotIn('myTESTaccount', rows)
        self.assertIn('Guest01', rows)
        self.assertEqual(rows['등록만']['completed'], [])
        self.assertEqual(rows['빈점수']['completed'], [])
        self.assertEqual(rows['문자점수']['completed'], [])
        self.assertEqual(rows['수학학생']['completed'], [])
        self.assertEqual(rows['영점참여']['completed'], ['시험'])
        self.assertEqual(rows['영점참여']['scores']['시험'], 0)
        self.login()
        admin = self.client.get('/api/participation', params={'category':'공통'}).json()
        self.assertEqual(next(r for r in admin['rows'] if r['user']=='영점참여')['scores']['시험'], 0)

    def test_invalid_quiz_cannot_start(self):
        self.store.quiz_rows[0]['Content'] += '\n[Q3] broken'
        self.assertFalse(self.client.get('/api/bootstrap').json()['quizzes'][0]['valid'])
        self.assertEqual(self.attempt().status_code, 422)

    def test_expired_attempt_rejects_submission(self):
        aid = self.attempt().json()['attempt_id']
        self.now += 101
        self.assertEqual(self.client.post(f'/api/attempts/{aid}/submit', json={'answers': ['둘', '서울']}).status_code, 410)

    def test_admin_cookie_expires_and_protects_keys(self):
        self.assertEqual(self.client.get(f'/api/quizzes/{self.quiz_id}/edit').status_code, 401)
        response = self.login()
        self.assertIn('HttpOnly', response.headers['set-cookie'])
        self.assertIn('SameSite=strict', response.headers['set-cookie'])
        self.assertTrue(self.client.get('/api/bootstrap').json()['admin'])
        self.assertEqual(self.client.get(f'/api/quizzes/{self.quiz_id}/edit').json()['content'], CONTENT)
        self.now += 11
        self.assertEqual(self.client.get('/api/admin/settings').status_code, 401)

    def test_cross_origin_writes_blocked_even_when_logged_in(self):
        self.login()
        self.assertEqual(self.client.delete(f'/api/quizzes/{self.quiz_id}', headers={'Origin': 'https://evil.example'}).status_code, 403)
        self.assertEqual(len(self.store.quiz_rows), 1)

    def test_no_default_admin_password_and_login_is_rate_limited(self):
        from web_app import create_app
        from web_config import WebConfig
        client = TestClient(create_app(FakeStorage(), WebConfig()), headers={'Origin': 'http://testserver'})
        self.assertEqual(client.post('/api/admin/login', json={'password': ''}).status_code, 503)
        for _ in range(5):
            self.assertEqual(self.client.post('/api/admin/login', json={'password': 'bad'}).status_code, 401)
        self.assertEqual(self.login().status_code, 429)

    def test_preview_authoring_duplicate_and_immutable_title(self):
        payload = {'title': '새 시험', 'category': '공통', 'content': CONTENT}
        self.assertEqual(self.client.get('/api/author/template').status_code, 401)
        self.assertEqual(self.client.post('/api/preview', json=payload).status_code, 401)
        self.assertEqual(self.client.post('/api/quizzes', json=payload).status_code, 401)
        self.login()
        self.assertEqual(self.client.get('/api/author/template').status_code, 200)
        self.assertTrue(self.client.post('/api/preview', json=payload).json()['valid'])
        self.assertEqual(self.client.post('/api/quizzes', json=payload).status_code, 200)
        self.assertEqual(self.client.post('/api/quizzes', json=payload).status_code, 409)
        self.assertEqual(self.client.patch(f'/api/quizzes/{self.quiz_id}', json=payload).status_code, 422)
        payload['title'] = '시험'
        self.assertEqual(self.client.patch(f'/api/quizzes/{self.quiz_id}', json=payload).status_code, 200)
        self.assertEqual(self.client.delete(f'/api/quizzes/{self.quiz_id}').status_code, 200)

    def test_disconnected_is_explicit_and_does_not_leak_errors(self):
        self.login()
        self.store.disconnected = True
        self.assertFalse(self.client.get('/api/bootstrap').json()['connected'])
        response = self.client.get('/api/results?user=학생')
        self.assertEqual(response.status_code, 503)
        self.assertIsInstance(response.json()['detail'], str)

    def test_learning_sections_are_public_but_management_stays_private(self):
        self.store.result_rows = [
            {'QuizTitle':'시험','User':'학생','Score':'50','Duration':'11','Time':'2026-09-30'},
            {'QuizTitle':'시험','User':'다른학생','Score':'100','Duration':'9','Time':'2026-09-30'}]
        self.store.wrong_rows = [{'QuizTitle':'시험','User':'학생','QuestionText':'합은?','Status':'오답'}]
        self.store.chat_rows = [{'User':'학생','Message':'공개 대화','Time':'오늘'}]
        for path in ['/api/results?user=학생','/api/leaderboard','/api/wrongs?user=학생','/api/chat']:
            with self.subTest(path=path):
                self.assertEqual(self.client.get(path).status_code, 200)
        self.assertEqual(len(self.client.get('/api/results?user=학생').json()['records']), 1)
        self.assertEqual(self.client.get('/api/leaderboard').json()['records'][0]['user'], '다른학생')
        self.assertEqual(self.client.get('/api/participation').status_code, 401)
        wrong = self.client.get('/api/wrongs?user=학생').json()['items'][0]
        self.assertEqual(self.client.post(f"/api/wrongs/{wrong['id']}/answer",json={'user':'학생','answer':'둘'}).status_code, 200)
        self.assertEqual(self.client.post('/api/chat',json={'user':'학생','message':'공개 질문'}).status_code, 200)
        for path in ['/api/admin/settings','/api/admin/backups','/api/author/template','/api/participation']:
            self.assertEqual(self.client.get(path).status_code, 401)
        attempt = self.attempt().json()
        submitted = self.client.post(f"/api/attempts/{attempt['attempt_id']}/submit",json={'answers':['둘','서울']})
        self.assertEqual(submitted.json()['score'], 100)
        self.login()
        self.assertEqual(self.client.get('/api/participation').json()['rows'][0]['scores']['시험'], 100)
        self.assertEqual(self.client.get('/api/admin/settings').status_code, 200)
        self.now += 11
        self.assertEqual(self.client.get('/api/admin/settings').status_code, 401)
        self.assertEqual(self.client.get('/api/participation').status_code, 401)

    def test_https_public_origin_and_admin_cookie(self):
        client = TestClient(self.app, base_url='https://training.example', headers={'Origin':'https://training.example'})
        response = client.post('/api/admin/login', json={'password':'test-only'})
        self.assertEqual(response.status_code, 200)
        self.assertIn('Secure', response.headers['set-cookie'])
        self.assertEqual(client.get('/api/participation').status_code, 200)
        client.post('/api/admin/logout', json={})
        self.assertEqual(client.get('/api/admin/settings').status_code, 401)

    def test_wrong_regrade_and_orphan_archive_preserve_identity(self):
        self.login()
        self.store.wrong_rows = [
            {'QuizTitle': '시험', 'User': '학생', 'QuestionText': '합은?', 'Status': '오답'},
            {'QuizTitle': '삭제됨', 'User': '학생', 'QuestionText': '사라짐', 'Status': '오답'}]
        items = self.client.get('/api/wrongs?user=학생').json()['items']
        active, orphan = items
        self.assertFalse(active['orphan'])
        self.assertTrue(orphan['orphan'])
        self.assertNotIn('correct_answer', active)
        self.assertEqual(self.client.post(f"/api/wrongs/{active['id']}/archive", json={'user': '학생'}).status_code, 422)
        self.assertEqual(self.client.post(f"/api/wrongs/{active['id']}/answer", json={'user': '다른학생', 'answer': '둘'}).status_code, 404)
        graded = self.client.post(f"/api/wrongs/{active['id']}/answer", json={'user': '학생', 'answer': '둘'}).json()
        self.assertTrue(graded['correct'])
        self.assertEqual(self.store.wrong_rows[0]['Status'], '정복')
        self.assertEqual(self.client.post(f"/api/wrongs/{orphan['id']}/archive", json={'user': '학생'}).status_code, 200)
        self.assertNotEqual(self.store.wrong_rows[1]['Status'], '오답')

    def test_chat_settings_and_confirmed_restore(self):
        self.login()
        self.assertEqual(self.client.post('/api/chat', json={'user': '학생', 'message': '안녕하세요'}).status_code, 200)
        self.assertEqual(self.client.get('/api/chat').json()['messages'][0]['message'], '안녕하세요')
        self.login()
        self.assertEqual(self.client.put('/api/admin/settings', json={'settings': {'default_category': '새 소식'}}).status_code, 200)
        self.assertEqual(self.client.get('/api/admin/settings').json()['settings']['default_category'], '새 소식')
        name = self.client.get('/api/admin/backups').json()['files'][0]
        self.assertEqual(self.client.post('/api/admin/restore', json={'name': name, 'confirmation': 'wrong'}).status_code, 422)
        self.assertFalse(hasattr(self.store, 'restored'))
        self.assertEqual(self.client.post('/api/admin/restore', json={'name': name, 'confirmation': name}).status_code, 200)
        self.assertEqual(self.store.restored, name)

    def test_settings_never_return_private_configuration(self):
        self.store.config.update(ADMIN_PASSWORD='private', GCP_JSON='private', SHEET_ID='private', GS_BACKUP_URL='private')
        self.login()
        response = self.client.get('/api/admin/settings')
        self.assertNotIn('private', response.text)

    def test_restore_invalidates_pre_restore_attempts(self):
        aid = self.attempt().json()['attempt_id']
        self.login()
        name = self.store.backup_names[0]
        self.client.post('/api/admin/restore', json={'name': name, 'confirmation': name})
        self.assertEqual(self.client.post(f'/api/attempts/{aid}/submit', json={'answers': ['둘', '서울']}).status_code, 410)

    def test_storage_validation_error_is_korean_and_sanitized(self):
        self.login()
        with patch.object(self.store, 'create_backup', side_effect=ValueError('sensitive exception')):
            response = self.client.post('/api/admin/backups', json={'name': 'duplicate'})
        self.assertEqual(response.status_code, 422)
        self.assertNotIn('sensitive', response.text)

    def test_concurrent_removed_quiz_is_not_reported_as_deleted(self):
        self.login()
        with patch.object(self.store, 'delete_quiz', return_value=False):
            response = self.client.delete(f'/api/quizzes/{self.quiz_id}')
        self.assertEqual(response.status_code, 404)

    def test_bootstrap_exposes_only_sanitized_public_settings(self):
        self.store.config.update(default_view='개인 기록', default_category=' 수학 ', custom_categories='수학, 영어,수학',
                                 season_start='bad date', top_achievers_count='-9', private_token='never-return')
        settings = self.client.get('/api/bootstrap').json().get('settings', {})
        self.assertEqual(settings, {'default_view': '개인 기록', 'default_category': '수학',
                                    'custom_categories': '수학, 영어', 'season_start': '2000-01-01',
                                    'top_achievers_count': 3})
        self.assertNotIn('never-return', self.client.get('/api/bootstrap').text)

    def test_leaderboard_applies_season_and_per_quiz_limit_after_best_attempt(self):
        self.login()
        self.store.config.update(season_start='2026-09-01', top_achievers_count=2)
        self.store.result_rows = [
            {'QuizTitle': '시험', 'User': 'old', 'Score': 100, 'Duration': 1, 'Time': '2026-08-31'},
            {'QuizTitle': '시험', 'User': 'one', 'Score': 80, 'Duration': 5, 'Time': '2026-09-02'},
            {'QuizTitle': '시험', 'User': 'one', 'Score': 100, 'Duration': 6, 'Time': '2026-09-03'},
            {'QuizTitle': '시험', 'User': 'two', 'Score': 90, 'Duration': 5, 'Time': '2026-09-04'},
            {'QuizTitle': '시험', 'User': 'three', 'Score': 85, 'Duration': 1, 'Time': '2026-09-05'},
            {'QuizTitle': '다른시험', 'User': 'three', 'Score': 70, 'Duration': 8, 'Time': '2026-09-06'},
        ]
        response = self.client.get('/api/leaderboard').json()
        self.assertEqual([r['user'] for r in response['records']], ['one', 'two', 'three'])
        self.assertEqual((response.get('season_start'), response.get('top_count')), ('2026-09-01', 2))

    def test_admin_rejects_invalid_settings_before_any_partial_write(self):
        self.login()
        initial = self.store.config.copy()
        for settings in [
            {'season_start': '2026-02-30'}, {'top_achievers_count': 0}, {'top_achievers_count': 1001},
            {'top_achievers_count': 2.5}, {'top_achievers_count': True}, {'unrelated_key': 'value'},
            {'default_view': 'missing-page'}, {'default_category': '수학', 'season_start': 'wrong'},
        ]:
            with self.subTest(settings=settings):
                self.assertEqual(self.client.put('/api/admin/settings', json={'settings': settings}).status_code, 422)
                self.assertEqual(self.store.config, initial)
        self.assertEqual(self.client.put('/api/admin/settings', json={'settings': {'season_start': '2026-09-01 12:30:00', 'top_achievers_count': '4'}}).status_code, 200)
        self.assertEqual(self.client.get('/api/admin/settings').json()['settings']['top_achievers_count'], 4)

    def test_season_boundary_includes_midnight_date_only_records(self):
        self.login()
        self.store.config['season_start'] = '2026-09-01 00:00:00'
        self.store.result_rows = [{'QuizTitle': '시험', 'User': '학생', 'Score': 100, 'Duration': 1, 'Time': '2026-09-01'}]
        self.assertEqual(len(self.client.get('/api/leaderboard').json()['records']), 1)


class ConfigTests(unittest.TestCase):
    def test_importing_application_does_not_read_real_configuration(self):
        import web_app
        with patch('web_config.load_config', side_effect=AssertionError('must not read credentials while importing')):
            importlib.reload(web_app)

    def test_environment_overrides_neutral_and_legacy_fallback(self):
        self.assertIsNotNone(importlib.util.find_spec('web_config'), 'Neutral config is not implemented')
        from web_config import load_config
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / '.streamlit').mkdir()
            (root / '.streamlit' / 'secrets.toml').write_text('ADMIN_PASSWORD="legacy"\nSHEET_ID="old"', encoding='utf-8')
            self.assertEqual(load_config(root, {}).admin_password, 'legacy')
            (root / 'secrets.toml').write_text('ADMIN_PASSWORD="neutral"\nSHEET_ID="new"\nGS_BACKUP_URL="https://script.google.com/macros/s/test/exec"', encoding='utf-8')
            config = load_config(root, {'ADMIN_PASSWORD': 'environment'})
            self.assertEqual((config.admin_password, config.sheet_id), ('environment', 'new'))
            self.assertEqual(config.backup_url, 'https://script.google.com/macros/s/test/exec')
            self.assertNotIn('environment', repr(config))
            self.assertNotIn('script.google.com', repr(config))


if __name__ == '__main__':
    unittest.main()
