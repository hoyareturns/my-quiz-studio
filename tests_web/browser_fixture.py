"""Isolated browser QA server. Uses fabricated data and never connects to Google."""
from tests_web.test_api import FakeStorage, CONTENT
from web_app import create_app
from web_config import WebConfig


class BrowserStorage(FakeStorage):
    def save_attempt(self, attempt_id, title, category, user, score, duration, questions, review):
        if attempt_id in self.attempts:
            return
        super().save_attempt(attempt_id, title, category, user, score, duration, questions, review)
        self.result_rows.append({'QuizTitle':title,'User':user,'Score':score,'Duration':duration,'Time':'2026-09-30 15:30'})
        for item in review:
            if not item['correct']:
                self.wrong_rows.append({'QuizTitle':title,'User':user,'QuestionText':item['question'],'Status':'오답'})


store = BrowserStorage()
store.quiz_rows = [
    {'Title':title,'Category':category,'Content':CONTENT}
    for title, category in [
        ('엑셀 기본 함수, 어디까지 알고 있나요?','디지털 역량'),
        ('업무에 바로 쓰는 데이터 분석','디지털 역량'),
        ('함께 일하는 소통의 기술','공통 역량'),
        ('일상에서 만나는 수학','기초 학습'),
        ('보고서를 읽는 힘','공통 역량'),
        ('오늘의 상식 한 걸음','기초 학습'),
    ]
]
store.quiz_rows[3]['Content'] = '[Q1] $x^2=4$의 양의 해는?\n[O] ① $x=1$ ② $x=2$\n[A] ②\n[E] $\\sqrt{4}=2$입니다.'
store.result_rows=[{'QuizTitle':store.quiz_rows[0]['Title'],'User':'미리보기','Score':100,'Duration':62,'Time':'2026-09-29 10:15'}]
store.result_rows += [
    {'QuizTitle':'등록','User':'등록만한사람','Score':0},
    {'QuizTitle':store.quiz_rows[1]['Title'],'User':'Guest01','Score':100},
    {'QuizTitle':store.quiz_rows[2]['Title'],'User':'TEST01','Score':100},
    {'QuizTitle':store.quiz_rows[0]['Title'],'User':'영점참여자','Score':0},
    {'QuizTitle':store.quiz_rows[0]['Title'],'User':'빈점수','Score':''},
]
store.chat_rows=[{'User':'학습 도우미','Message':'배운 내용을 서로 나눠 주세요. 함께 배우면 더 오래 기억할 수 있어요.','Time':'오늘'}]
app = create_app(store, WebConfig(admin_password='browser-test-only'))
