# personal_record_logic.py
import streamlit as st
import pandas as pd

def show_personal_records(current_player, all_results):
    st.subheader(" 개인 성적표")
    st.caption("지금까지의 학습 성과와 퀴즈 기록을 확인하세요.")

    if not all_results:
        st.info("아직 기록된 성적이 없습니다.")
        return

    df = pd.DataFrame(all_results)
    
    # 1. 아이디 목록 추출 (성적 기록이 있는 아이디만)
    all_users = sorted(df['User'].unique().tolist())
    
    # 2. 아이디 선택 드롭박스 (현재 로그인 유저를 기본값으로)
    default_idx = all_users.index(current_player) if current_player in all_users else 0
    target_user = st.selectbox("성적을 확인할 아이디 선택", all_users, index=default_idx)

    # 3. 데이터 필터링 및 전처리
    user_df = df[df['User'] == target_user].copy()
    user_df['Score'] = pd.to_numeric(user_df['Score'], errors='coerce')
    
    # 4. 구간별 횟수 계산
    # 100점 / 90~99점 / 80~89점 / 80점 미만
    s100 = len(user_df[user_df['Score'] == 100])
    s90 = len(user_df[(user_df['Score'] >= 90) & (user_df['Score'] < 100)])
    s80 = len(user_df[(user_df['Score'] >= 80) & (user_df['Score'] < 90)])
    s_low = len(user_df[user_df['Score'] < 80])

    # 요약 지표 출력 (상단 컬럼)
    st.write("")
    col1, col2, col3, col4 = st.columns(4)
    col1.metric(" 100점", f"{s100}회")
    col2.metric(" 90~99점", f"{s90}회")
    col3.metric(" 80~89점", f"{s80}회")
    col4.metric(" 기타", f"{s_low}회")

    st.divider()

    # 5. 상세 목록 표시
    st.markdown(f"####  {target_user}님의 상세 풀이 이력")
    if not user_df.empty:
        # 최신순 정렬
        display_df = user_df.sort_values(by='Time', ascending=False).reset_index(drop=True)
        display_df.index = display_df.index + 1 # 번호를 1부터 시작
        
        # 보기 좋게 컬럼명 변경 후 출력
        st.table(display_df[['QuizTitle', 'Score', 'Duration', 'Time']].rename(columns={
            'QuizTitle': '퀴즈 제목',
            'Score': '점수',
            'Duration': '소요시간(초)',
            'Time': '완료 시간'
        }))
    else:
        st.write("표시할 상세 기록이 없습니다.")
