import streamlit as st
import pandas as pd
from database import get_unique_players

def show_participation_status(season_res, all_quizzes):
    st.subheader("📊 참여 현황 (퀴즈별 성취도)")

    # 1. 카테고리(그룹) 목록 추출
    categories = sorted(list(set(q.get('Category', '미분류') for q in all_quizzes if q.get('Category'))))
    category_options = categories + ["전체 퀴즈"]
    
    # UI 배치: 드롭박스 라벨 제거 (collapsed) 및 체크박스 배치
    col1, col2, col3 = st.columns([2, 1, 1.2])
    with col1:
        selected_cat = st.selectbox("퀴즈 그룹 선택", category_options, index=len(category_options)-1, label_visibility="collapsed")
    with col2:
        exclude_guest = st.checkbox("Guest 제외", value=True)
    with col3:
        hide_empty = st.checkbox("미참여 퀴즈 제외", value=True)

    # 2. [명단 관리] 모든 사용자(ID) 명단 확보 및 Guest 필터링 강화
    raw_players = get_unique_players()
    
    if exclude_guest:
        # 공백 제거 및 소문자 변환 후 'guest'가 아닌 것만 추출
        all_players = [p for p in raw_players if str(p).strip().lower() != 'guest']
    else:
        all_players = raw_players
    
    all_players = sorted(list(set(all_players))) # 중복 제거 및 정렬

    # 3. 선택된 그룹에 속한 퀴즈 제목 목록 추출
    if selected_cat == "전체 퀴즈":
        target_quiz_titles = sorted(list(set(q.get('Title') for q in all_quizzes)))
    else:
        target_quiz_titles = sorted(list(set(q.get('Title') for q in all_quizzes if q.get('Category') == selected_cat)))

    # 4. 데이터 처리
    if not season_res:
        # 시즌 기록이 아예 없는 경우: 모든 유저에 대해 "-"로 채운 표 생성
        final_df = pd.DataFrame("-", index=all_players, columns=target_quiz_titles)
        final_df.index.name = "사용자 ID"
        st.dataframe(final_df, use_container_width=True)
        return

    # 기록 데이터프레임 생성
    df = pd.DataFrame(season_res)
    
    # [중요] 결과 데이터에서도 Guest 데이터 제외 처리
    if exclude_guest:
        df = df[df['User'].str.strip().str.lower() != 'guest']

    if df.empty and not all_players:
        st.info("표시할 사용자 정보나 퀴즈 기록이 없습니다.")
        return

    # 점수 숫자 변환
    df['Score'] = pd.to_numeric(df['Score'], errors='coerce')
    
    # 피벗 테이블 생성 (User x QuizTitle)
    pivot_df = df.pivot_table(index='User', columns='QuizTitle', values='Score', aggfunc='max')
    
    # [핵심] 필터링된 all_players로 행(Row) 재구성 (참여 안 한 유저도 여기서 포함됨)
    pivot_df = pivot_df.reindex(all_players)
    
    # 퀴즈(열) 필터링
    if hide_empty:
        # 기록에 실제로 존재하는 퀴즈만 필터링
        actual_quiz_in_data = [title for title in target_quiz_titles if title in pivot_df.columns and pivot_df[title].notnull().any()]
        pivot_df = pivot_df[actual_quiz_in_data]
        final_quiz_columns = actual_quiz_in_data
    else:
        # 선택된 카테고리의 모든 퀴즈를 열로 생성
        for title in target_quiz_titles:
            if title not in pivot_df.columns:
                pivot_df[title] = None
        pivot_df = pivot_df[target_quiz_titles]
        final_quiz_columns = target_quiz_titles

    # 데이터 변환: 값이 있으면 "완료", 없으면 "-"
    pivot_df = pivot_df.fillna("-")
    for col in pivot_df.columns:
        pivot_df[col] = pivot_df[col].apply(lambda x: "완료" if x != "-" else "-")

    # 5. 최종 출력
    pivot_df.index.name = "사용자 ID"
    st.dataframe(pivot_df, use_container_width=True)