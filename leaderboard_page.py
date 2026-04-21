import streamlit as st
import pandas as pd

def show_season_leaderboard(season_res, season_start):
    """퀴즈별 상위 3위 표시"""
    st.subheader("구역별 최강자")
    st.caption(f"이번 시즌 시작일: {season_start[:10]}")
    
    if not season_res:
        st.info("이번 시즌 기록이 없습니다.")
        return

    df = pd.DataFrame(season_res)
    quiz_titles = df['QuizTitle'].unique()

    for title in quiz_titles:
        st.markdown(f"#### {title}")
        quiz_df = df[df['QuizTitle'] == title].sort_values(
            by=['Score', 'Duration'], ascending=[False, True]
        ).reset_index(drop=True)

        for i in range(min(3, len(quiz_df))):
            row = quiz_df.iloc[i]
            st.write(f"{i+1}위: {row['User']} ({int(row['Score'])}점 / {row['Duration']}초)")
        st.write("")