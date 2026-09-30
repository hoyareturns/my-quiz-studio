import unittest
from quiz_core import check_subjective_answer, validate_quiz_text


class CoreTests(unittest.TestCase):
    def test_fraction_and_formula_are_not_split(self):
        self.assertFalse(check_subjective_answer('1', '1/2'))
        self.assertFalse(check_subjective_answer('A1', 'SUM(A1,B1)'))
        self.assertTrue(check_subjective_answer(' seoul ', '서울 | Seoul'))
        self.assertTrue(check_subjective_answer('참', 'TRUE'))

    def test_malformed_answer_does_not_become_last_option(self):
        questions, errors = validate_quiz_text('[Q1] 질문\n[O] ① 하나 ② 둘\n[A] ⑤')
        self.assertEqual(questions, [])
        self.assertEqual(len(errors), 1)

    def test_partial_import_reports_errors_instead_of_silently_dropping(self):
        questions, errors = validate_quiz_text('[Q1] 질문\n[O] ① 하나 ② 둘\n[A] ②\n[Q2] 잘못된 문제')
        self.assertEqual(len(questions), 1)
        self.assertEqual(len(errors), 1)

    def test_numbered_chatgpt_response_and_passage(self):
        questions, errors = validate_quiz_text('```text\n[Q1] <지문>본문</지문> 수도는?\n[O]\n1. 서울\n2. 부산\n[A] 1\n[E] 서울\n```')
        self.assertEqual(errors, [])
        self.assertEqual(questions[0]['o'], ['서울', '부산'])
        self.assertEqual(questions[0]['p'], '본문')
        self.assertEqual(questions[0]['a'], 0)
