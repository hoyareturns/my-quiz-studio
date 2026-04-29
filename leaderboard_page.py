import streamlit as st
import pandas as pd
from utils import natural_sort_key


def show_season_leaderboard(season_res, season_start, app_settings): # app_settings 인자 추가
    """퀴즈별 상위 N위 표시 (관리자 설정 반영)"""
    
    # 1. 관리자 모드에서 설정한 인원수 가져오기 (설정 없으면 기본값 3)
    top_count = int(app_settings.get('top_achievers_count', 3))
    
    # 2. 타이틀에 설정된 숫자 반영
    st.subheader(f"영역별 성취도 TOP {top_count}")
    st.caption(f"이번 시즌 시작일: {season_start[:10]}")
    
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
            st.write(f"{i+1}위: {row['User']} ({int(row['Score'])}점 / {row['Duration']}초)")
        
        st.write("")