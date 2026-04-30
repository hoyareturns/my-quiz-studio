import streamlit as st
import pandas as pd
from database import get_unique_players

def show_participation_status(season_res, all_quizzes):
    # 제목 (이모지 제거)
    st.subheader("참여 현황 (퀴즈별 성취도)")

    # 1. 카테고리 목록 추출
    categories = sorted(list(set(q.get('Category', '미분류') for q in all_quizzes if q.get('Category'))))
    category_options = categories + ["전체 퀴즈"]
    
    col1, col2, col3 = st.columns([2, 1, 1.2])
    with col1:
        # [해결 1] index=0으로 설정하여 항상 첫 번째 그룹이 기본으로 선택되게 함
        selected_cat = st.selectbox(
            "퀴즈 그룹 선택", 
            category_options, 
            index=0, 
            label_visibility="collapsed"
        )
    with col2:
        exclude_guest = st.checkbox("Guest 제외", value=True)
    with col3:
        hide_empty = st.checkbox("미참여 퀴즈 제외", value=True)

    # 2. [원천 차단] 모든 사용자 명단에서 Guest 필터링
    raw_players = get_unique_players()
    if exclude_guest:
        # 명단 생성 시점부터 guest를 제외 (strip, lower로 모든 변수 차단)
        all_players = [p for p in raw_players if str(p).strip().lower() != 'guest']
    else:
        all_players = raw_players
    all_players = sorted(list(set(all_players)))

    # 3. 대상 퀴즈 필터링
    if selected_cat == "전체 퀴즈":
        target_quiz_titles = sorted(list(set(q.get('Title') for q in all_quizzes)))
    else:
        target_quiz_titles = sorted(list(set(q.get('Title') for q in all_quizzes if q.get('Category') == selected_cat)))

    # 4. 기록 데이터 전처리
    df = pd.DataFrame(season_res)
    
    # [해결 2] 기록 데이터(df) 내에서도 Guest를 원천 차단
    # 기록이 있더라도 여기서 필터링되면 피벗 테이블에 나타나지 않음
    if not df.empty and exclude_guest:
        df = df[df['User'].str.strip().str.lower() != 'guest']

    # 5. 피벗 테이블 생성 및 명단 재구성
    if not df.empty:
        df['Score'] = pd.to_numeric(df['Score'], errors='coerce')
        # 피벗 생성
        pivot_df = df.pivot_table(index='User', columns='QuizTitle', values='Score', aggfunc='max')
        
        # [핵심] 필터링된 명단(all_players)으로 행을 다시 맞춤 (reindex)
        # 이 과정에서 명단에 없는 Guest 기록은 모두 버려지게 됩니다.
        pivot_df = pivot_df.reindex(index=all_players)
        
        # 퀴즈(열) 필터링
        if hide_empty:
            actual_cols = [t for t in target_quiz_titles if t in pivot_df.columns and pivot_df[t].notnull().any()]
            pivot_df = pivot_df[actual_cols]
        else:
            for t in target_quiz_titles:
                if t not in pivot_df.columns: pivot_df[t] = None
            pivot_df = pivot_df[target_quiz_titles]
    else:
        # 기록이 없는 경우 깨끗한 명단만 표시
        pivot_df = pd.DataFrame("-", index=all_players, columns=target_quiz_titles)

    # 6. 최종 텍스트 변환 및 정리
    pivot_df = pivot_df.fillna("-")
    for col in pivot_df.columns:
        pivot_df[col] = pivot_df[col].apply(lambda x: "완료" if x != "-" else "-")

    pivot_df.index.name = "사용자 ID"
    st.dataframe(pivot_df, use_container_width=True)