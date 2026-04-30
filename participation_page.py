import streamlit as st
import pandas as pd
from database import get_unique_players

def show_participation_status(season_res, all_quizzes):
    st.subheader(" 참여 현황 (퀴즈별 성취도)")

    # 1. 퀴즈 데이터에서 유효한 카테고리(그룹) 목록 추출
    categories = sorted(list(set(q.get('Category', '미분류') for q in all_quizzes if q.get('Category'))))
    category_options = categories + ["전체 퀴즈"]
    
    # UI 배치: 드롭박스와 옵션들을 배치
    col1, col2, col3 = st.columns([2, 1, 1.2])
    with col1:
        # [변경 사항 1] 라벨을 숨겨서 UI를 더 간결하게 처리 (label_visibility="collapsed")
        selected_cat = st.selectbox("퀴즈 그룹 선택", category_options, index=len(category_options)-1, label_visibility="collapsed")
    with col2:
        exclude_guest = st.checkbox("Guest 제외", value=True)
    with col3:
        # 미참여 퀴즈 제외 옵션 (기본값: True)
        hide_empty = st.checkbox("미참여 퀴즈 제외", value=True)

    # [변경 사항 2] 모든 사용자(ID) 명단 확보
    # 참여 기록이 전혀 없더라도 명단에 표시하기 위해 전체 유저 목록을 가져옵니다.
    all_players = get_unique_players()
    if exclude_guest:
        all_players = [p for p in all_players if str(p).lower() != 'guest']
    all_players = sorted(all_players)

    # 2. 선택된 그룹에 속한 "대상 퀴즈 제목 목록" 추출
    if selected_cat == "전체 퀴즈":
        target_quiz_titles = sorted(list(set(q.get('Title') for q in all_quizzes)))
    else:
        target_quiz_titles = sorted(list(set(q.get('Title') for q in all_quizzes if q.get('Category') == selected_cat)))

    # 3. 데이터프레임 처리 및 피벗 테이블 생성
    df = pd.DataFrame(season_res)
    
    # 성적 데이터가 있는 경우의 처리
    if not df.empty and 'User' in df.columns and 'QuizTitle' in df.columns:
        df['Score'] = pd.to_numeric(df['Score'], errors='coerce')
        
        # 피벗 테이블 생성 (User x QuizTitle)
        pivot_df = df.pivot_table(index='User', columns='QuizTitle', values='Score', aggfunc='max')
        
        # [핵심] 모든 사용자가 포함되도록 재색인 (참여 안 한 유저는 자동으로 NaN으로 생성됨)
        pivot_df = pivot_df.reindex(all_players)
        
        # 퀴즈 필터링 로직
        if hide_empty:
            # 현재 결과 데이터에 실제로 참여 기록이 있는 퀴즈만 필터링
            actual_quiz_in_data = [title for title in target_quiz_titles if title in pivot_df.columns and pivot_df[title].notnull().any()]
            pivot_df = pivot_df[actual_quiz_in_data]
            final_quiz_columns = actual_quiz_in_data
        else:
            # 미참여 퀴즈도 모두 열(Column)로 포함
            for title in target_quiz_titles:
                if title not in pivot_df.columns:
                    pivot_df[title] = None
            pivot_df = pivot_df[target_quiz_titles]
            final_quiz_columns = target_quiz_titles
                
        # 점수 존재 여부에 따라 "완료" 또는 "-" 표시로 변환
        for col in final_quiz_columns:
            pivot_df[col] = pivot_df[col].apply(lambda x: "완료" if pd.notnull(x) else "-")
            
        pivot_df.index.name = "사용자 ID"
        st.dataframe(pivot_df, use_container_width=True)
    
    else:
        # 시즌 기록이 아예 없는 경우 전체 명단에 "-"만 표시하여 출력
        if all_players:
            final_df = pd.DataFrame("-", index=all_players, columns=target_quiz_titles)
            final_df.index.name = "사용자 ID"
            st.dataframe(final_df, use_container_width=True)
        else:
            st.info("표시할 사용자 정보나 퀴즈 기록이 없습니다.")