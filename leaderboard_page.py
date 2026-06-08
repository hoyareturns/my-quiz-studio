import streamlit as st
import pandas as pd
from utils import natural_sort_key


def show_season_leaderboard(season_res, season_start, app_settings): # app_settings 인자 추가
    """퀴즈별 상위 N위 표시 (관리자 설정 반영)"""
    
    # 1. 관리자 모드에서 설정한 인원수 가져오기 (설정 없으면 기본값 3)
    top_count = int(app_settings.get('top_achievers_count', 3))
    
    # 2. 타이틀에 설정된 숫자 반영
    st.subheader(f"영역별 성취도 TOP {top_count}")
    st.caption(f"이번 시즌 시작일: {str(season_start)[:10]}")
    if not season_res:
        st.info("이번 시즌 기록이 없습니다.")
        return

    df = pd.DataFrame(season_res)
    quiz_titles = sorted(df['QuizTitle'].unique(), key=natural_sort_key)

    for title in quiz_titles:
        st.markdown(f"#### {title}")
        
        quiz_df = df[df['QuizTitle'] == title].sort_values(
            by=['Score', 'Duration'], ascending=[False, True]
        ).reset_index(drop=True)

        # 3. 반복 횟수를 top_count에 맞게 조절
        # min(top_count, len(quiz_df))를 통해 실제 데이터 개수와 설정값 중 작은 쪽을 선택합니다.
        for i in range(min(top_count, len(quiz_df))):
            row = quiz_df.iloc[i]
            # 점수(Score) 데이터를 안전하게 정수로 변환하는 내장 방어 로직
            try:
                # 혹시 소수점(예: 100.0)이거나 문자열 숫자인 경우를 고려해 float 변환 후 int 처리
                score_val = int(float(row.get('Score', 0)))
            except (ValueError, TypeError):
                # "완료"나 "-" 같은 숫자가 아닌 문자가 들어있으면 에러 대신 0점으로 처리
                score_val = 0

            # 화면 출력부 (정제된 score_val 변수 사용)
            st.write(f"{i+1}위: {row['User']} ({score_val}점 / {row.get('Duration', '-')}초)")


        st.write("")