import streamlit as st
import pandas as pd
from database import get_unique_players

def show_participation_status(season_res, all_quizzes):
    # 이모지 제거
    st.subheader("참여 현황 (퀴즈별 성취도)")

    # 1. 카테고리 목록 추출
    categories = sorted(list(set(q.get('Category', '미분류') for q in all_quizzes if q.get('Category'))))
    # 기본이 첫 번째 그룹이 되도록 "전체 퀴즈"를 가장 뒤에 배치
    category_options = categories + ["전체 퀴즈"]
    
    col1, col2, col3 = st.columns([2, 1, 1.2])
    with col1:
        # index=0 설정으로 항상 첫 번째 카테고리가 기본값이 됨
        selected_cat = st.selectbox(
            "퀴즈 그룹 선택", 
            category_options, 
            index=0, 
            label_visibility="collapsed"
        )
    with col2:
        # 이 옵션이 체크되면 'Guest' 단어가 포함된 모든 ID가 필터링됨
        exclude_guest = st.checkbox("Guest 포함 아이디 제외", value=True)
    with col3:
        hide_empty = st.checkbox("미참여 퀴즈 제외", value=True)

    # 2. 명단 관리 (Guest 포함 여부 원천 차단)
    raw_players = get_unique_players()
    
    if exclude_guest:
        # [핵심] 'guest'라는 글자가 포함만 되어도 명단에서 제외 (대소문자 무시)
        all_players = [p for p in raw_players if 'guest' not in str(p).lower()]
    else:
        all_players = raw_players
    
    all_players = sorted(list(set(all_players)))

    # 3. 대상 퀴즈 필터링
    if selected_cat == "전체 퀴즈":
        target_quiz_titles = sorted(list(set(q.get('Title') for q in all_quizzes)))
    else:
        target_quiz_titles = sorted(list(set(q.get('Title') for q in all_quizzes if q.get('Category') == selected_cat)))

    # 4. 데이터프레임 전처리
    df = pd.DataFrame(season_res)
    
    # [핵심] 성적 기록 데이터(df) 내에서도 'guest' 포함 아이디를 완전히 제거
    if not df.empty and exclude_guest:
        df = df[~df['User'].str.lower().str.contains('guest', na=False)]

    # 5. 피벗 및 데이터 병합
    if not df.empty:
        df['Score'] = pd.to_numeric(df['Score'], errors='coerce')
        # 피벗 테이블 생성
        pivot_df = df.pivot_table(index='User', columns='QuizTitle', values='Score', aggfunc='max')
        
        # [구조적 장치] 필터링된 깨끗한 명단(all_players)으로 행을 재구성 (reindex)
        # 이 과정에서 명단에 없는 Guest 관련 아이디나 미참여 데이터가 완벽히 정리됨
        pivot_df = pivot_df.reindex(index=all_players)
        
        # 퀴즈(열) 필터링
        if hide_empty:
            actual_quiz_in_data = [t for t in target_quiz_titles if t in pivot_df.columns and pivot_df[t].notnull().any()]
            pivot_df = pivot_df[actual_quiz_in_data]
        else:
            for t in target_quiz_titles:
                if t not in pivot_df.columns: pivot_df[t] = None
            pivot_df = pivot_df[target_quiz_titles]
    else:
        # 기록이 아예 없는 경우 필터링된 유저 명단만 표시
        pivot_df = pd.DataFrame("-", index=all_players, columns=target_quiz_titles)

    # 6. 최종 텍스트 변환 ("완료" 또는 "-")
    pivot_df = pivot_df.fillna("-")
    for col in pivot_df.columns:
        pivot_df[col] = pivot_df[col].apply(lambda x: "완료" if x != "-" else "-")

    pivot_df.index.name = "사용자 ID"
    st.dataframe(pivot_df, use_container_width=True)