import streamlit as st
import pandas as pd
from utils import natural_sort_key


def show_season_leaderboard(season_res, season_start):
    """퀴즈별 상위 3위 표시 (자연어 정렬 적용)"""
    st.subheader("영역별 성취도 TOP3")
    st.caption(f"이번 시즌 시작일: {season_start[:10]}")
    
    if not season_res:
        st.info("이번 시즌 기록이 없습니다.")
        return

    df = pd.DataFrame(season_res)
    
    # [수정 핵심] key=natural_sort_key를 추가하여 숫자 크기순으로 정렬합니다.
    quiz_titles = sorted(df['QuizTitle'].unique(), key=natural_sort_key)

    for title in quiz_titles:
        st.markdown(f"#### {title}")
        
        quiz_df = df[df['QuizTitle'] == title].sort_values(
            by=['Score', 'Duration'], ascending=[False, True]
        ).reset_index(drop=True)

        for i in range(min(3, len(quiz_df))):
            row = quiz_df.iloc[i]
            st.write(f"{i+1}위: {row['User']} ({int(row['Score'])}점 / {row['Duration']}초)")
        
        st.write("")