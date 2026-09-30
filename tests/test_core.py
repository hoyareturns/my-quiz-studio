import importlib
import sys
import types
import unittest
from unittest.mock import patch
import database

import utils

VALID = '[Q1] 2 + 2는?\n[O] ① 3 ② 4\n[A] ②\n[K] 덧셈\n[E] 2와 2를 더하면 4입니다.'


class GradingTests(unittest.TestCase):
    def test_wrong_answer_never_reads_api_credentials(self):
        class NoSecrets:
            def get(self, *args):
                raise AssertionError('Local grading must not access API credentials')
        with patch.object(utils.st, 'secrets', NoSecrets()):
            self.assertFalse(utils.check_subjective_answer('VLOOKP', 'VLOOKUP'))

    def test_fraction_and_formula_are_not_split_into_partial_answers(self):
        self.assertFalse(utils.check_subjective_answer('1', '1/2'))
        self.assertFalse(utils.check_subjective_answer('A1', 'SUM(A1,B1)'))

    def test_explicit_alternatives_and_boolean_aliases(self):
        self.assertTrue(utils.check_subjective_answer('참', 'TRUE'))
        self.assertTrue(utils.check_subjective_answer('서울', 'Seoul | 서울'))
        self.assertTrue(utils.check_subjective_answer(' vLookUp ', 'VLOOKUP'))


class ImportTests(unittest.TestCase):
    def test_valid_legacy_format(self):
        self.assertEqual(utils.robust_parse(VALID)[0]['a'], 1)

    def test_numbered_options_from_chatgpt(self):
        text = '```text\n[Q1] 수도는?\n[O]\n1. 서울\n2. 부산\n[A] 1\n[E] 서울입니다.\n```'
        questions = utils.robust_parse(text)
        self.assertEqual(questions[0]['o'], ['서울', '부산'])
        self.assertEqual(questions[0]['a'], 0)

    def test_invalid_answer_never_selects_last_option(self):
        self.assertEqual(utils.robust_parse(VALID.replace('[A] ②', '[A] 없음')), [])

    def test_preview_reports_partial_import_instead_of_silent_loss(self):
        self.assertTrue(callable(getattr(utils, 'validate_quiz_text', None)), 'Import needs validation before saving')
        questions, errors = utils.validate_quiz_text(VALID + '\n[Q2] 누락된 문제\n[A] 답')
        self.assertEqual(len(questions), 1)
        self.assertEqual(len(errors), 1)


class FakeSheet:
    def __init__(self):
        self.reads = 0
        self.writes = []

    def get_all_records(self):
        self.reads += 1
        return [{'QuizTitle': 'quiz', 'User': 'lee', 'Score': 90, 'Duration': 10, 'Time': '2026-09-30 12:00:00'}]

    def append_rows(self, rows, **kwargs):
        self.writes.append(rows)

    def append_row(self, row, **kwargs):
        self.writes.append([row])


class StorageTests(unittest.TestCase):
    def setUp(self):
        database.get_all_results.clear()
        database.get_unique_players.clear()

    def test_user_list_reuses_results_read(self):
        from streamlit.testing.v1 import AppTest
        def read_both():
            import database
            import streamlit as st
            st.write(database.get_unique_players())
            st.write(database.get_all_results())
        sheet = FakeSheet()
        with patch.object(database, 'get_worksheet', return_value=sheet):
            app = AppTest.from_function(read_both).run()
            self.assertEqual(len(app.exception), 0)
        self.assertEqual(sheet.reads, 1)

    def test_ten_wrong_answers_use_one_write(self):
        sheet = FakeSheet()
        with patch.object(database, 'get_worksheet', return_value=sheet):
            database.save_wrong_answers('quiz', 'lee', [f'q{i}' for i in range(10)])
        self.assertEqual(len(sheet.writes), 1)
        self.assertEqual(len(sheet.writes[0]), 10)
        self.assertEqual(sheet.writes[0][0][:4], ['quiz', 'lee', 'q0', '오답'])

    def test_result_save_does_not_write_incompatible_wrong_answer_rows(self):
        sheet = FakeSheet()
        with patch.object(database, 'get_worksheet', return_value=sheet):
            database.save_result('quiz', 'lee', 90, 10, ['keyword'])
        self.assertEqual(len(sheet.writes), 1)
        self.assertEqual(sheet.writes[0][0][:4], ['quiz', 'lee', 90, 10])

    def test_missing_connection_is_not_reported_as_success(self):
        with patch.object(database, 'get_worksheet', return_value=None):
            with self.assertRaises(RuntimeError):
                database.save_result('quiz', 'lee', 100, 10, [])

    def test_retry_after_committed_timeout_does_not_duplicate_result(self):
        import inspect
        self.assertIn('attempt_id', inspect.signature(database.save_result).parameters)
        class CommittedTimeoutSheet(FakeSheet):
            col_count = 5
            def __init__(self):
                super().__init__()
                self.headers = ['QuizTitle', 'User', 'Score', 'Duration', 'Time']
                self.rows = []
                self.failed = False
            def row_values(self, row):
                return list(self.headers)
            def col_values(self, col):
                return [self.headers[col-1]] + [r[col-1] for r in self.rows]
            def add_cols(self, number):
                self.col_count += number
            def update_cell(self, row, col, value):
                self.headers.append(value)
            def append_rows(self, rows, **kwargs):
                self.rows.extend(rows)
                if not self.failed:
                    self.failed = True
                    raise TimeoutError('Write committed but response was lost')
        sheet = CommittedTimeoutSheet()
        with patch.object(database, 'get_worksheet', return_value=sheet):
            with self.assertRaises(TimeoutError):
                database.save_result('quiz', 'lee', 100, 10, [], attempt_id='stable-attempt')
            database.save_result('quiz', 'lee', 100, 10, [], attempt_id='stable-attempt')
        self.assertEqual(len(sheet.rows), 1)


if __name__ == '__main__':
    unittest.main()
