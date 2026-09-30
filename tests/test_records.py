import unittest
from unittest.mock import patch
from streamlit.testing.v1 import AppTest


class RecordFlowTests(unittest.TestCase):
    def test_participation_accepts_extra_columns_and_uses_named_fields(self):
        def screen():
            import streamlit as st
            from participation_page import show_participation_status
            st.session_state.is_admin = True
            show_participation_status(
                [{'AttemptID':'attempt', 'User':'learner', 'Duration':10, 'Time':'2026-09-30', 'Score':75, 'QuizTitle':'quiz'}],
                [{'Title':'quiz','Category':'category'}])
        with patch('participation_page.get_unique_players', return_value=['learner']):
            app = AppTest.from_function(screen).run()
        self.assertEqual(len(app.exception), 0)
        self.assertEqual(str(app.dataframe[0].value.loc['learner', 'quiz']), '75')

    def test_edited_question_remains_visible_with_explicit_resolution(self):
        def screen():
            from wrong_answer_logic import show_wrong_answer_conquest
            from utils import robust_parse
            show_wrong_answer_conquest('learner', [{'Title':'quiz','Content':'[Q1] Changed\n[O] \u2460 A \u2461 B\n[A] \u2460'}], robust_parse)
        record = {'QuizTitle':'quiz', 'User':'learner', 'QuestionText':'Original question', 'Status':'오답', 'CreatedAt':'2026-09-30'}
        with patch('wrong_answer_logic.get_all_users_with_wrongs', return_value=['learner']), patch('wrong_answer_logic.get_wrong_answers_by_user', return_value=[record]):
            app = AppTest.from_function(screen).run()
        self.assertEqual(len(app.exception), 0)
        self.assertTrue(any('Original question' in m.value for m in app.markdown))
        self.assertTrue(any('정리' in b.label for b in app.button))

    def test_personal_records_do_not_default_to_someone_else(self):
        def screen():
            from personal_record_logic import show_personal_records
            show_personal_records('new learner', [{'User':'another learner','Score':90,'QuizTitle':'quiz','Duration':10,'Time':'2026-09-30'}])
        app = AppTest.from_function(screen).run()
        self.assertEqual(len(app.exception), 0)
        self.assertEqual(len(app.table) + len(app.dataframe), 0)
        self.assertTrue(any('기록' in item.value for item in app.info))
