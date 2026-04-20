# wrong_answer_logic.py (새로 생성)

import streamlit as st
import time
from database import get_wrong_answers_by_user, update_wrong_answer_status, get_all_users_with_wrongs

def show_wrong_answer_conquest(current_player, all_quizzes, robust_parse):
    st.subheader("🔥 오답 정복")
    st.caption("틀린 문제만 다시 풀어보세요. 맞히면 목록에서 사라집니다.")

    # 오답 기록이 있는 아이디만 드롭박스 표시
    wrong_users = get_all_users_with_wrongs()
    
    if not wrong_users:
        st.info("현재 정복할 오답이 없습니다. 모두 완벽하시네요!")
        return

    # 유저 선택
    default_idx = wrong_users.index(current_player) if current_player in wrong_users else 0
    target_user = st.selectbox("리뷰할 아이디 선택", wrong_users, index=default_idx)

    # 선택된 아이디의 오답 목록
    records = get_wrong_answers_by_user(target_user)
    
    if not records:
        st.success(f"🎉 {target_user}님은 모든 오답을 정복했습니다!")
        return

    st.write(f"현재 **{len(records)}개**의 오답이 남아있습니다.")

    for idx, rec in enumerate(records):
        with st.container(border=True):
            q_title = rec.get('QuizTitle')
            q_text = rec.get('QuestionText')
            
            # 원본 퀴즈 데이터에서 해당 문제의 옵션과 정답 찾기
            parent_quiz = next((q for q in all_quizzes if q['Title'] == q_title), None)
            if not parent_quiz: 
                st.caption(f"원본 퀴즈({q_title})가 삭제되었습니다.")
                continue
            
            parsed = robust_parse(parent_quiz['Content'])
            q_data = next((p for p in parsed if p['q'] == q_text), None)
            if not q_data: continue

            st.caption(f"출처: {q_title}")
            if q_data.get('p'):
                with st.container(border=True):
                    st.markdown(f"📄 **[지문]**\n\n{q_data['p']}")
            
            st.markdown(f"**Q.** {q_data['q']}")

            is_short = q_data['o'] == ["주관식"]
            ans_key = f"wrong_{target_user}_{idx}"
            
            if is_short:
                user_ans = st.text_input("정답 입력", key=ans_key)
            else:
                user_ans = st.radio("보기 선택", q_data['o'], index=None, key=ans_key, label_visibility="collapsed")

            if st.button("정답 확인", key=f"btn_{ans_key}"):
                correct = str(q_data['a']) if is_short else q_data['o'][q_data['a']]
                
                # 정답 비교 로직
                is_correct = (str(user_ans).replace(" ","").lower() == str(correct).replace(" ","").lower())
                
                if is_correct:
                    st.success("정답입니다! 정복 완료.")
                    update_wrong_answer_status(target_user, q_title, q_text, "정복")
                    time.sleep(1)
                    st.rerun()
                else:
                    st.error("아직 틀렸습니다! 다시 생각해보세요.")
                    with st.expander("💡 해설 보기"):
                        st.markdown(q_data['e'])
