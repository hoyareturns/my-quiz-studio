import unittest
from contextlib import ExitStack
from unittest.mock import patch
from streamlit.testing.v1 import AppTest
import database

CONTENT = '[Q1] 2 + 2는?\n[O] ① 3 ② 4\n[A] ②\n[E] 덧셈입니다.'
QUIZZES = [{'Category': '공통 역량', 'Title': '기초 확인', 'Content': CONTENT, 'CreatedAt': '2026-09-30'}]


def button(app, label):
    return next(b for b in app.button if b.label == label)


class AppFlowTests(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        for name, value in [('get_gspread_client', None), ('get_settings', {}),
                            ('get_all_quizzes', QUIZZES), ('get_all_results', []),
                            ('get_unique_players', []), ('get_all_wrong_answers', []),
                            ('get_chats', [])]:
            self.stack.enter_context(patch.object(database, name, return_value=value))
        self.app = AppTest.from_file('my_study_app.py', default_timeout=10)
        self.app.secrets['ADMIN_PASSWORD'] = 'test-only-password'

    def test_quiz_can_be_completed_without_ai_or_network(self):
        app = self.app.run()
        self.assertEqual(len(app.exception), 0)
        app.text_input(key='player_name').set_value('테스트 학습자').run()
        button(app, '기초 확인').click().run()
        button(app, '풀이 시작').click().run()
        radios = [r for r in app.radio if r.label.startswith('1번')]
        self.assertEqual(len(radios), 1)
        radios[0].set_value('4')
        with patch('quiz_page.save_result', return_value=True) as save:
            button(app, '답안 제출').click().run()
            self.assertEqual(len(app.exception), 0)
            self.assertTrue(any('100' in m.value for m in app.metric))
            app.run()
            self.assertEqual(save.call_count, 1)

    def test_author_can_copy_request_and_preview_before_login(self):
        app = self.app.run()
        self.assertEqual(len(app.exception), 0)
        app.radio(key='main_menu').set_value('문제 등록').run()
        self.assertTrue(any('복사' in m.value for m in app.markdown))
        self.assertGreater(len(app.code), 0)
        app.text_input(key='draft_title').set_value('새 평가')
        app.text_area(key='draft_content').set_value(CONTENT)
        button(app, '문제 미리보기').click().run()
        self.assertEqual(len(app.exception), 0)
        self.assertTrue(any('1문제' in s.value for s in app.success))
        self.assertTrue(button(app, '퀴즈 등록').disabled)

    def test_invalid_paste_blocks_registration(self):
        app = self.app.run()
        self.assertEqual(len(app.exception), 0)
        app.radio(key='main_menu').set_value('문제 등록').run()
        app.text_input(key='draft_title').set_value('형식 확인')
        app.text_area(key='draft_content').set_value(CONTENT + '\n[Q2] 보기 없는 문제')
        button(app, '문제 미리보기').click().run()
        self.assertGreater(len(app.error), 0)
        self.assertTrue(button(app, '퀴즈 등록').disabled)

    def test_successful_registration_clears_draft_and_shows_success(self):
        app = self.app.run()
        app.session_state['is_admin'] = True
        app.radio(key='main_menu').set_value('문제 등록').run()
        app.text_input(key='draft_title').set_value('새 평가')
        app.text_area(key='draft_content').set_value(CONTENT)
        button(app, '문제 미리보기').click().run()
        with patch('author_page.save_quiz', return_value=True) as save:
            button(app, '퀴즈 등록').click().run()
            self.assertEqual(save.call_count, 1)
            self.assertEqual(app.text_area(key='draft_content').value, '')
            self.assertTrue(any('등록했습니다' in s.value for s in app.success))

    def test_draft_survives_menu_switch(self):
        app = self.app.run()
        app.radio(key='main_menu').set_value('문제 등록').run()
        app.text_input(key='draft_title').set_value('작업 중').run()
        app.text_area(key='draft_content').set_value(CONTENT).run()
        app.radio(key='main_menu').set_value('역량 점검').run()
        app.radio(key='main_menu').set_value('문제 등록').run()
        self.assertEqual(app.text_input(key='draft_title').value, '작업 중')
        self.assertEqual(app.text_area(key='draft_content').value, CONTENT)

    def test_registration_failure_retains_draft(self):
        app = self.app.run()
        app.session_state['is_admin'] = True
        app.radio(key='main_menu').set_value('문제 등록').run()
        app.text_input(key='draft_title').set_value('네트워크 오류 시 보존')
        app.text_area(key='draft_content').set_value(CONTENT)
        button(app, '문제 미리보기').click().run()
        with patch('author_page.save_quiz', side_effect=TimeoutError):
            button(app, '퀴즈 등록').click().run()
        self.assertEqual(app.text_area(key='draft_content').value, CONTENT)
        self.assertEqual(len(app.error), 1)

    def test_unanswered_quiz_is_not_saved(self):
        app = self.app.run()
        app.text_input(key='player_name').set_value('학습자').run()
        button(app, '기초 확인').click().run()
        button(app, '풀이 시작').click().run()
        with patch('quiz_page.save_result') as save:
            button(app, '답안 제출').click().run()
        self.assertEqual(save.call_count, 0)
        self.assertTrue(any('답하지 않은' in w.value for w in app.warning))

    def test_each_menu_has_an_empty_state_without_crashing(self):
        app = self.app.run()
        app.text_input(key='player_name').set_value('학습자').run()
        for name in ['오답 정복', '개인 기록', '우수 성취자', '참여현황', '토론방', '관리']:
            with self.subTest(menu=name):
                app.radio(key='main_menu').set_value(name).run()
                self.assertEqual(len(app.exception), 0)
                self.assertEqual(len(app.error), 0)


class UnconfiguredAppTests(unittest.TestCase):
    def test_missing_secrets_shows_friendly_guidance_without_error_panels(self):
        database.get_gspread_client.clear()
        database.clear_data_cache()
        with patch.object(database, 'get_secret', return_value=None):
            app = AppTest.from_file('my_study_app.py').run()
        self.assertEqual(len(app.exception), 0)
        self.assertEqual(len(app.error), 0)
        self.assertTrue(any('연결 설정' in item.value for item in app.info))


if __name__ == '__main__':
    unittest.main()
