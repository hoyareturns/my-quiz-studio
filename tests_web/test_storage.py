import copy
import re
import unittest
from unittest.mock import patch
from types import SimpleNamespace

import web_storage


class WorksheetNotFound(Exception):
    pass


class Worksheet:
    def __init__(self, title, data=()):
        self.title, self.data = title, copy.deepcopy(list(data))
        self.col_count, self.row_count = 26, 1000
        self.fail_append_after_commit = False
        self.fail_update = 0
        self.unformatted_values = None

    def get_all_values(self, **kwargs):
        if kwargs.get('value_render_option') == 'UNFORMATTED_VALUE' and self.unformatted_values is not None:
            return copy.deepcopy(self.unformatted_values)
        return copy.deepcopy(self.data)

    def append_rows(self, values, value_input_option):
        assert value_input_option == 'RAW'
        self.data.extend(copy.deepcopy(values))
        if self.fail_append_after_commit:
            self.fail_append_after_commit = False
            raise TimeoutError('committed but response lost')

    def append_row(self, values, value_input_option):
        self.append_rows([values], value_input_option)

    def batch_update(self, data, value_input_option):
        for item in data:
            self.update(item['values'], item['range'], value_input_option)

    def update(self, values, range_name='A1', value_input_option=None):
        assert value_input_option == 'RAW'
        if self.fail_update:
            self.fail_update -= 1
            raise TimeoutError('unavailable')
        match = re.match(r'([A-Z]+)(\d+)', range_name)
        col = 0
        for char in match[1]:
            col = col * 26 + ord(char) - 64
        row = int(match[2]) - 1
        for i, cells in enumerate(values):
            while len(self.data) <= row + i:
                self.data.append([])
            target = self.data[row + i]
            target.extend([''] * max(0, col - 1 + len(cells) - len(target)))
            target[col - 1:col - 1 + len(cells)] = copy.deepcopy(cells)

    def resize(self, rows=None, cols=None):
        self.row_count = rows or self.row_count
        self.col_count = cols or self.col_count

    def clear(self):
        self.data = []

    def delete_rows(self, start, end=None):
        del self.data[start - 1:end or start]


class Book:
    def __init__(self, ident, title, sheets=()):
        self.id, self.title = ident, title
        self.sheets = {ws.title: ws for ws in sheets}

    def worksheet(self, title):
        if title not in self.sheets:
            raise WorksheetNotFound(title)
        return self.sheets[title]

    def worksheets(self):
        return list(self.sheets.values())

    def add_worksheet(self, title, rows, cols):
        self.sheets[title] = Worksheet(title)
        return self.sheets[title]

    def del_worksheet(self, ws):
        del self.sheets[ws.title]


class Client:
    def __init__(self, *books):
        self.books = {b.id: b for b in books}
        self.copies = []

    def open_by_key(self, key):
        return self.books[key]

    def list_spreadsheet_files(self):
        return [{'id': b.id, 'name': b.title} for b in self.books.values()]

    def copy(self, file_id, title, copy_permissions=False):
        source = self.books[file_id]
        book = Book('copy-' + str(len(self.copies)), title, copy.deepcopy(source.worksheets()))
        self.books[book.id] = book
        self.copies.append(book)
        return book


class StorageTests(unittest.TestCase):
    def setUp(self):
        self.assertTrue(hasattr(web_storage, 'SheetsStorage'), 'SheetsStorage is not implemented')
        self.main = Book('main', 'production', [Worksheet('Quizzes', [
            ['Category', 'Title', 'Content', 'CreatedAt', 'Extra'],
            ['old', 'first', '[Q1] 문항\n[O] 주관식\n[A] 답', '2026-01-01', 'keep'],
        ])])
        self.client = Client(self.main)
        self.store = web_storage.SheetsStorage(SimpleNamespace(sheet_id='main', gcp_json='{}'), client=self.client)

    def test_reads_do_not_create_missing_sheets_and_cache_is_not_mutable(self):
        self.assertEqual(self.store.results(), [])
        self.assertEqual(self.store.wrongs(), [])
        self.assertEqual(self.store.chats(), [])
        self.assertEqual(self.store.settings(), {})
        self.assertEqual(list(self.main.sheets), ['Quizzes'])
        self.store.quizzes()[0]['Title'] = 'corrupted'
        self.assertEqual(self.store.quizzes()[0]['Title'], 'first')

    def test_quiz_writes_preserve_unknown_columns_and_invalidate_cached_reads(self):
        self.store.quizzes()
        self.store.update_quiz('first', 'new', '[Q1] 다른 문항\n[O] 주관식\n[A] 답')
        self.assertEqual(self.store.quizzes()[0]['Category'], 'new')
        self.assertEqual(self.store.quizzes()[0]['Extra'], 'keep')
        self.store.save_quiz('=literal', 'cat', '[Q1] 질문\n[O] 주관식\n[A] 답')
        self.assertIn('=literal', [r['Title'] for r in self.store.quizzes()])
        with self.assertRaises(ValueError):
            self.store.save_quiz('first', 'cat', '[Q1] 질문\n[O] 주관식\n[A] 답')
        self.assertTrue(self.store.delete_quiz('first'))
        self.assertEqual(len(self.store.quizzes()), 1)

    def test_reordered_columns_receive_correct_data(self):
        self.main.sheets['Chats'] = Worksheet('Chats', [['Extra', 'Message', 'Time', 'User']])
        self.store.save_chat('user', '=SUM(A1)')
        self.assertEqual(self.store.chats()[0]['Message'], '=SUM(A1)')
        self.assertEqual(self.store.chats()[0]['User'], 'user')
        self.assertEqual(self.store.chats()[0]['Extra'], '')

    def test_settings_merge_preserves_other_settings_and_columns(self):
        self.main.sheets['Settings'] = Worksheet('Settings', [['Key', 'Value', 'Extra'], ['a', 'old', 'keep'], ['b', '2', '']])
        self.store.settings()
        self.store.save_settings({'a': '=literal', 'c': '3'})
        self.assertEqual(self.store.settings(), {'a': '=literal', 'b': '2', 'c': '3'})
        self.assertEqual(self.main.sheets['Settings'].data[1][2], 'keep')

    def test_attempt_retry_reconciles_each_sheet_after_committed_timeout(self):
        ws = Worksheet('WrongAnswers', [['QuizTitle', 'User', 'QuestionText', 'Status', 'CreatedAt', 'Extra']])
        ws.fail_append_after_commit = True
        self.main.sheets['WrongAnswers'] = ws
        questions = [{'q': 'question', 'p': 'passage', 'o': ['A', 'B'], 'a': 1, 'e': 'because'}]
        review = [{'question': 'question', 'answer': 'A', 'correct_answer': 'B', 'explanation': 'because', 'correct': False}]
        args = ('attempt-1', 'first', 'cat', 'user', 0, 2.5, questions, review)
        try:
            self.store.save_attempt(*args)
        except web_storage.StorageError:
            pass
        self.store.save_attempt(*args)
        self.assertEqual(len(self.store.results()), 1)
        self.assertEqual(len(self.store.wrongs()), 1)
        logs = self.main.sheets['WrongAnswers_Logs'].data
        self.assertEqual(len(logs), 2)
        self.assertEqual(dict(zip(logs[0], logs[1]))['Answer'], 'B')
        self.assertEqual(self.store.wrongs()[0]['AttemptID'], 'attempt-1')
        self.assertEqual(self.store.wrongs()[0]['Extra'], '')

    def test_wrong_status_matches_user_title_question_and_active_status(self):
        self.main.sheets['WrongAnswers'] = Worksheet('WrongAnswers', [
            ['User', 'Status', 'QuizTitle', 'QuestionText', 'CreatedAt'],
            ['u', '정복', 'first', 'q', ''], ['u', '오답', 'other', 'q', ''],
            ['v', '오답', 'first', 'q', ''], ['u', '오답', 'first', 'q', ''],
        ])
        self.store.wrongs()
        self.assertTrue(self.store.set_wrong_status('u', 'first', 'q', '정복'))
        self.assertEqual([r['Status'] for r in self.store.wrongs()], ['정복', '오답', '오답', '정복'])

    def test_repeated_wrong_question_is_resolved_once_without_reappearing(self):
        for status in ['정복', '보관']:
            with self.subTest(status=status):
                ws = Worksheet('WrongAnswers', [
                    ['User', 'Status', 'QuizTitle', 'QuestionText', 'CreatedAt', 'AttemptID'],
                    ['u', '오답', 'first', 'q', 'one', 'attempt1'],
                    ['v', '오답', 'first', 'q', 'other-user', 'attempt2'],
                    ['u', '오답', 'first', 'q', 'two', 'attempt3'],
                    ['u', '오답', 'other', 'q', 'other-quiz', 'attempt4'],
                    ['u', '정복', 'first', 'q', 'already-solved', 'attempt5'],
                    ['u', '오답', 'first', 'different', 'other-question', 'attempt6'],
                ])
                self.main.sheets['WrongAnswers'] = ws
                self.store.wrongs()
                with patch.object(ws, 'batch_update', wraps=ws.batch_update) as write:
                    self.assertTrue(self.store.set_wrong_status('u', 'first', 'q', status))
                    self.assertEqual([r['Status'] for r in self.store.wrongs()],
                                     [status, '오답', status, '오답', '정복', '오답'])
                    self.assertEqual(write.call_count, 1)
                self.assertEqual([r['AttemptID'] for r in self.store.wrongs()],
                                 ['attempt1', 'attempt2', 'attempt3', 'attempt4', 'attempt5', 'attempt6'])
                self.assertFalse(self.store.set_wrong_status('u', 'first', 'q', status))

    def test_disconnected_reads_fail_instead_of_claiming_empty(self):
        store = web_storage.SheetsStorage(SimpleNamespace(sheet_id='', gcp_json=''))
        with self.assertRaises(web_storage.StorageError):
            store.quizzes()

    def test_expired_cache_observes_external_changes(self):
        with patch('web_storage.time.monotonic', return_value=100):
            self.assertEqual(self.store.quizzes()[0]['Category'], 'old')
        self.main.sheets['Quizzes'].data[1][0] = 'external'
        with patch('web_storage.time.monotonic', return_value=110):
            self.assertEqual(self.store.quizzes()[0]['Category'], 'old')
        with patch('web_storage.time.monotonic', return_value=131):
            self.assertEqual(self.store.quizzes()[0]['Category'], 'external')

    def test_failed_committed_write_invalidates_cache(self):
        self.main.sheets['Chats'] = Worksheet('Chats', [['User', 'Message', 'Time']])
        self.assertEqual(self.store.chats(), [])
        self.main.sheets['Chats'].fail_append_after_commit = True
        with self.assertRaises(web_storage.StorageError):
            self.store.save_chat('u', 'committed')
        self.assertEqual(self.store.chats()[0]['Message'], 'committed')

    def test_backups_are_scoped_by_prefix_and_exclude_main_id(self):
        self.main.title = '스마트평가센터_백업_main'
        self.client.books['other'] = Book('other', 'unrelated')
        name = self.store.create_backup('safe')
        self.assertEqual(name, '스마트평가센터_백업_safe')
        self.assertEqual(self.store.backups(), [name])
        with self.assertRaises(ValueError):
            self.store.create_backup('safe')
        with self.assertRaises(ValueError):
            self.store.restore_backup('unrelated')

    def test_legacy_backup_prefix_is_listed_and_restorable(self):
        self.main.title = '퀴즈_백업_main'
        legacy = Book('legacy', '퀴즈_백업_2026-01-01', copy.deepcopy(self.main.worksheets()))
        legacy.sheets['Quizzes'].data[1][0] = 'legacy'
        self.client.books['legacy'] = legacy
        self.assertEqual(self.store.backups(), ['퀴즈_백업_2026-01-01'])
        self.store.restore_backup('퀴즈_백업_2026-01-01')
        self.assertEqual(self.store.quizzes()[0]['Category'], 'legacy')

    def test_configured_apps_script_creates_named_verified_backup(self):
        self.store.config.backup_url = 'https://script.google.com/macros/s/fake-deployment/exec'
        self.assertEqual(self.store.backups(), [])

        def request(url, params, timeout):
            self.assertEqual(url, self.store.config.backup_url)
            self.assertEqual(params, {'name': '스마트평가센터_백업_script'})
            self.assertEqual(timeout, 15)
            self.client.books['script'] = Book('script', params['name'], copy.deepcopy(self.main.worksheets()))
            return SimpleNamespace(raise_for_status=lambda: None)

        with patch('requests.get', side_effect=request):
            self.assertEqual(self.store.create_backup('script'), '스마트평가센터_백업_script')
        self.assertEqual(self.client.copies, [])
        self.assertEqual(self.store.backups(), ['스마트평가센터_백업_script'])

    def test_untrusted_backup_url_is_rejected_without_http_request(self):
        bad_urls = ['http://script.google.com/macros/s/fake/exec',
                    'https://script.google.com.evil.example/macros/s/fake/exec',
                    'https://127.0.0.1/macros/s/fake/exec',
                    'https://script.google.com/other',
                    'https://user@script.google.com/macros/s/fake/exec']
        for index, url in enumerate(bad_urls):
            with self.subTest(url=url), patch('requests.get') as request:
                self.store.config.backup_url = url
                with self.assertRaises(web_storage.StorageError):
                    self.store.create_backup(f'unsafe-{index}')
                request.assert_not_called()

    def test_unverified_script_backup_stops_restore_before_changes(self):
        self.store.config.backup_url = 'https://script.google.com/macros/s/fake-deployment/exec'
        source = Book('source', '스마트평가센터_백업_source', copy.deepcopy(self.main.worksheets()))
        source.sheets['Quizzes'].data[1][0] = 'changed'
        self.client.books['source'] = source
        original = copy.deepcopy(self.main.sheets['Quizzes'].data)
        with patch('requests.get', return_value=SimpleNamespace(raise_for_status=lambda: None)):
            with self.assertRaises(web_storage.StorageError):
                self.store.restore_backup(source.title)
        self.assertEqual(self.main.sheets['Quizzes'].data, original)

    def test_apps_script_errors_do_not_expose_url_or_response_details(self):
        self.store.config.backup_url = 'https://script.google.com/macros/s/fake-deployment/exec'
        with patch('requests.get', side_effect=RuntimeError('private URL and response body')):
            with self.assertRaises(web_storage.StorageError) as error:
                self.store.create_backup('script')
        self.assertNotIn('private', str(error.exception))

    def test_ambiguous_new_backup_is_not_reported_as_success(self):
        self.store.config.backup_url = 'https://script.google.com/macros/s/fake-deployment/exec'

        def request(url, params, timeout):
            for key in ['script1', 'script2']:
                self.client.books[key] = Book(key, params['name'])
            return SimpleNamespace(raise_for_status=lambda: None)

        with patch('requests.get', side_effect=request):
            with self.assertRaises(web_storage.StorageError):
                self.store.create_backup('ambiguous')

    def test_restore_validates_before_any_destructive_action(self):
        invalid = Book('bad', '스마트평가센터_백업_bad', [Worksheet('Quizzes', [['bad'], ['value']])])
        self.client.books['bad'] = invalid
        before = copy.deepcopy(self.main.sheets['Quizzes'].data)
        with self.assertRaises(web_storage.StorageError):
            self.store.restore_backup(invalid.title)
        self.assertEqual(self.main.sheets['Quizzes'].data, before)
        self.assertEqual(self.client.copies, [])

    def test_restore_refuses_ambiguous_names(self):
        for key in ['b1', 'b2']:
            self.client.books[key] = Book(key, '스마트평가센터_백업_dup')
        with self.assertRaises(ValueError):
            self.store.restore_backup('스마트평가센터_백업_dup')

    def test_restore_takes_durable_snapshot_and_rolls_back_failed_updates(self):
        source = Book('backup', '스마트평가센터_백업_source', [Worksheet('Quizzes', [
            ['Category', 'Title', 'Content', 'CreatedAt'], ['restored', 'title', 'text', 'date'],
        ]), Worksheet('Chats', [['User', 'Message', 'Time'], ['u', 'msg', 'now']])])
        self.client.books['backup'] = source
        before = copy.deepcopy(self.main.sheets['Quizzes'].data)
        self.main.sheets['Quizzes'].fail_update = 1
        with self.assertRaisesRegex(web_storage.StorageError, '백업|복구'):
            self.store.restore_backup(source.title)
        self.assertEqual(self.main.sheets['Quizzes'].data, before)
        self.assertGreaterEqual(len(self.client.copies), 1)
        self.assertEqual(self.client.copies[0].sheets['Quizzes'].data, before)
        self.store.restore_backup(source.title)
        self.assertEqual(self.store.quizzes()[0]['Category'], 'restored')
        self.assertEqual(self.store.chats()[0]['Message'], 'msg')

    def test_partial_rollback_reports_snapshot_name_and_restores_other_sheets(self):
        self.main.sheets['Chats'] = Worksheet('Chats', [['User', 'Message', 'Time'], ['u', 'original', 'then']])
        source = Book('backup', '스마트평가센터_백업_source', [Worksheet('Quizzes', [
            ['Category', 'Title', 'Content', 'CreatedAt'], ['new', 'title', 'text', 'date'],
        ])])
        self.client.books['backup'] = source
        self.main.sheets['Quizzes'].fail_update = 2
        with self.assertRaisesRegex(web_storage.StorageError, '일부.*스마트평가센터_백업_복구전_'):
            self.store.restore_backup(source.title)
        self.assertEqual(self.store.chats()[0]['Message'], 'original')
        self.assertEqual(self.client.copies[0].sheets['Quizzes'].data[1][1], 'first')

    def test_restore_preserves_live_only_tabs_and_restores_evaluated_values(self):
        self.main.sheets['Unrelated'] = Worksheet('Unrelated', [['private'], ['keep']])
        source_ws = Worksheet('Quizzes', [
            ['Category', 'Title', 'Content', 'CreatedAt', 'Calculation'],
            ['restored', 'title', 'text', 'date', '=1+1'],
        ])
        source_ws.unformatted_values = copy.deepcopy(source_ws.data)
        source_ws.unformatted_values[1][4] = 2
        self.client.books['backup'] = Book('backup', '스마트평가센터_백업_values', [source_ws])
        self.store.restore_backup('스마트평가센터_백업_values')
        self.assertEqual(self.store.quizzes()[0]['Calculation'], 2)
        self.assertEqual(self.main.sheets['Unrelated'].data, [['private'], ['keep']])

    def test_dependency_value_error_is_sanitized(self):
        with patch.object(self.main, 'worksheet', side_effect=ValueError('secret credential detail')):
            with self.assertRaises(web_storage.StorageError) as error:
                self.store.quizzes()
        self.assertNotIn('secret', str(error.exception))


if __name__ == '__main__':
    unittest.main()
