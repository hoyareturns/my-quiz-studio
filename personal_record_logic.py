import streamlit as st
import pandas as pd

def show_personal_records(current_player, all_results):
    st.subheader("📊 개인 성적표")
    st.caption("나의 퀴즈 기록과 점수 분포를 확인하세요.")

    if not all_results:
        st.info("아직 기록된 성적이 없습니다. 퀴즈를 먼저 풀어보세요!")
        return

    df = pd.DataFrame(all_results)
    
    # [방어 로직] User가 비어있는 행 제외 및 문자열 변환 후 정렬
    # sorted() 에러를 방지하기 위해 리스트 컴프리헨션 사용
    all_users = sorted([str(u) for u in df['User'].unique() if u and str(u).strip()])
    
    if not all_users:
        st.warning("유효한 유저 기록이 없습니다.")
        return

    # 아이디 선택 (로그인 유저를 기본값으로)
    default_idx = all_users.index(current_player) if current_player in all_users else 0
    target_user = st.selectbox("기록을 확인할 아이디 선택", all_users, index=default_idx)

    # 해당 유저 데이터만 필터링
    user_df = df[df['User'] == target_user].copy()
    
    # 점수 데이터를 숫자로 변환 (변환 안 되는 건 제외)
    user_df['Score'] = pd.to_numeric(user_df['Score'], errors='coerce')
    user_df = user_df.dropna(subset=['Score'])

    # --- 구간별 통계 계산 ---
    # 1. 100점
    s100 = len(user_df[user_df['Score'] == 100])
    # 2. 90점 이상 ~ 100점 미만
    s90 = len(user_df[(user_df['Score'] >= 90) & (user_df['Score'] < 100)])
    # 3. 80점 이상 ~ 90점 미만
    s80 = len(user_df[(user_df['Score'] >= 80) & (user_df['Score'] < 90)])
    # 4. 80점 미만
    s_low = len(user_df[user_df['Score'] < 80])

    # 상단 요약 지표 (st.metric 사용)
    st.write("")
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("💯 100점", f"{s100}회")
    col2.metric("🥇 90~99점", f"{s90}회")
    col3.metric("🥈 80~89점", f"{s80}회")
    col4.metric("📉 기타", f"{s_low}회")

    st.divider()

    # --- 상세 목록 ---
    st.markdown(f"#### 📑 {target_user}님의 상세 풀이 이력")
    if not user_df.empty:
        # 최신순 정렬 (Time 기준)
        display_df = user_df.sort_values(by='Time', ascending=False).reset_index(drop=True)
        display_df.index = display_df.index + 1  # 1번부터 번호 부여
        
        # 테이블 출력
        st.table(display_df[['QuizTitle', 'Score', 'Duration', 'Time']].rename(columns={
            'QuizTitle': '퀴즈 제목',
            'Score': '점수',
            'Duration': '시간(초)',
            'Time': '완료일시'
        }))
    else:
        st.write("상세 기록이 존재하지 않습니다.")
