import streamlit as st
import pandas as pd
from database import get_unique_players

def show_participation_status(season_res, all_quizzes):
    # 이모지 제거 및 깔끔한 제목
    st.subheader("참여 현황 (퀴즈별 성취도)")

    # 1. 카테고리 목록 추출
    categories = sorted(list(set(q.get('Category', '미분류') for q in all_quizzes if q.get('Category'))))
    category_options = categories + ["전체 퀴즈"]
    
    # UI 배치 (라벨 숨김 및 체크박스)
    col1, col2, col3 = st.columns([2, 1, 1.2])
    with col1:
        selected_cat = st.selectbox("퀴즈 그룹 선택", category_options, index=len(category_options)-1, label_visibility="collapsed")
    with col2:
        exclude_guest = st.checkbox("Guest 제외", value=True)
    with col3:
        hide_empty = st.checkbox("미참여 퀴즈 제외", value=True)

    # 2. 명단 관리 (Guest 필터링 강화)
    raw_players = get_unique_players()
    
    if exclude_guest:
        # 전체 명단에서 Guest 제외
        all_players = [p for p in raw_players if str(p).strip().lower() != 'guest']
    else:
        all_players = raw_players
    
    all_players = sorted(list(set(all_players)))

    # 3. 데이터프레임 전처리
    df = pd.DataFrame(season_res)
    
    # 결과 데이터에서도 Guest를 확실히 제거 (이게 누락되면 표에 다시 나타남)
    if not df.empty and exclude_guest:
        df = df[df['User'].str.strip().str.lower() != 'guest']

    # 4. 대상 퀴즈 필터링
    if selected_cat == "전체 퀴즈":
        target_quiz_titles = sorted(list(set(q.get('Title') for q in all_quizzes)))
    else:
        target_quiz_titles = sorted(list(set(q.get('Title') for q in all_quizzes if q.get('Category') == selected_cat)))

    # 5. 피벗 및 데이터 병합
    if not df.empty:
        df['Score'] = pd.to_numeric(df['Score'], errors='coerce')
        # 피벗 테이블 생성
        pivot_df = df.pivot_table(index='User', columns='QuizTitle', values='Score', aggfunc='max')
        
        # [핵심] 참여하지 않은 유저 ID도 모두 표시하기 위해 reindex 수행
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
        # 데이터가 아예 없는 경우 빈 표 생성
        pivot_df = pd.DataFrame("-", index=all_players, columns=target_quiz_titles)

    # 6. 최종 텍스트 변환 및 출력
    pivot_df = pivot_df.fillna("-")
    for col in pivot_df.columns:
        pivot_df[col] = pivot_df[col].apply(lambda x: "완료" if x != "-" else "-")

    pivot_df.index.name = "사용자 ID"
    st.dataframe(pivot_df, use_container_width=True)