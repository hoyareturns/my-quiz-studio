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
        # index=0 설정으로 첫 번째 카테고리 기본 선택
        selected_cat = st.selectbox(
            "퀴즈 그룹 선택", 
            category_options, 
            index=0, 
            label_visibility="collapsed"
        )
    with col2:
        exclude_guest = st.checkbox("Guest 제외", value=True)
    with col3:
        hide_empty = st.checkbox("모두 미참여 제외", value=True)

    # 2. 명단 관리 (test는 무조건 제외, Guest는 옵션에 따라 제외)
    raw_players = get_unique_players()
    
    clean_players = []
    for p in raw_players:
        p_str = str(p).strip().lower()
        
        # [원천 차단] 'test'가 포함된 아이디는 무조건 제외
        if 'test' in p_str:
            continue
            
        # [옵션 차단] 'guest'가 포함된 아이디는 체크박스 상태에 따라 제외
        if exclude_guest and 'guest' in p_str:
            continue
            
        clean_players.append(p)
    
    all_players = sorted(list(set(clean_players)))

    # 3. 대상 퀴즈 필터링
    if selected_cat == "전체 퀴즈":
        target_quiz_titles = sorted(list(set(q.get('Title') for q in all_quizzes)))
    else:
        target_quiz_titles = sorted(list(set(q.get('Title') for q in all_quizzes if q.get('Category') == selected_cat)))

    # 4. 기록 데이터 전처리
    df = pd.DataFrame(season_res)
    
    if not df.empty:
        # [원천 차단] 데이터에서도 'test' 포함 아이디 삭제
        df = df[~df['User'].str.lower().str.contains('test', na=False)]
        
        # [옵션 차단] 데이터에서도 'guest' 포함 아이디 삭제
        if exclude_guest:
            df = df[~df['User'].str.lower().str.contains('guest', na=False)]

    # 5. 피벗 테이블 생성 및 명단 재구성
    if not df.empty:
        df['Score'] = pd.to_numeric(df['Score'], errors='coerce')
        pivot_df = df.pivot_table(index='User', columns='QuizTitle', values='Score', aggfunc='max')
        
        # 필터링된 깨끗한 명단(all_players)으로 행 재구성
        pivot_df = pivot_df.reindex(index=all_players)
        
        if hide_empty:
            actual_cols = [t for t in target_quiz_titles if t in pivot_df.columns and pivot_df[t].notnull().any()]
            pivot_df = pivot_df[actual_cols]
        else:
            for t in target_quiz_titles:
                if t not in pivot_df.columns: pivot_df[t] = None
            pivot_df = pivot_df[target_quiz_titles]
    else:
        pivot_df = pd.DataFrame("-", index=all_players, columns=target_quiz_titles)

    # 6. 최종 텍스트 변환 및 정리
    pivot_df = pivot_df.fillna("-")
    for col in pivot_df.columns:
        pivot_df[col] = pivot_df[col].apply(lambda x: "완료" if x != "-" else "-")

    pivot_df.index.name = "사용자 ID"
    # [수정] height 파라미터를 추가하여 기본 노출 높이를 늘립니다.
    # 750px는 대략 20~22개 행을 한 화면에 보여주기에 적당한 높이입니다.
    st.dataframe(
        pivot_df, 
        use_container_width=True, 
        height=750  # 이 부분을 추가/수정하세요.
    )