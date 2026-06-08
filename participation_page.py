import streamlit as st
import pandas as pd
from database import get_unique_players

def show_participation_status(season_res, all_quizzes):
    # 제목 (이모지 제거)
    st.subheader(" ")

    # 1. 카테고리 목록 추출
    categories = sorted(list(set(q.get('Category', '미분류') for q in all_quizzes if q.get('Category'))))
    category_options = categories + ["전체 퀴즈"]
    
    # [수정] 4개의 컬럼으로 나누어 "참여자만 표시" 옵션 추가
    col1, col2, col3, col4 = st.columns([1.5, 1, 1.2, 1.2])
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
    with col4:
        # [신규] 참여자만 표시 옵션 (기본값 True)
        only_participants = st.checkbox("참여자만 표시", value=True)

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
    if not season_res:
        st.info("표시할 참여 기록이 없습니다.")
        return

    # 데이터프레임 강제 생성 및 컬럼명 재정의
    df = pd.DataFrame(season_res)
    
    expected_cols = ['QuizTitle', 'User', 'Score', 'Duration', 'Time']
    
    if df.shape[1] != 5:
        df = df.iloc[:, 0].str.split(',', expand=True)
        df.columns = expected_cols[:df.shape[1]]
    else:
        df.columns = expected_cols

    # Score 컬럼 정제
    df['Score'] = pd.to_numeric(df['Score'], errors='coerce').fillna(0)
    df['User'] = df['User'].astype(str).str.strip()
    df['QuizTitle'] = df['QuizTitle'].astype(str).str.strip()

    if not df.empty:
        # [원천 차단] 데이터에서도 'test' 포함 아이디 삭제
        df = df[~df['User'].str.lower().str.contains('test', na=False)]
        
        # [옵션 차단] 데이터에서도 'guest' 포함 아이디 삭제
        if exclude_guest:
            df = df[~df['User'].str.lower().str.contains('guest', na=False)]

    # 5. 피벗 테이블 생성 및 명단 재구성
    if not df.empty:
        df = df[df['User'].isin(all_players)]
        
        pivot_df = df.pivot_table(index='User', columns='QuizTitle', values='Score', aggfunc='max')
        pivot_df = pivot_df.reindex(index=all_players)
        
        for t in target_quiz_titles:
            if t not in pivot_df.columns:
                pivot_df[t] = None
        pivot_df = pivot_df[target_quiz_titles]
        
        # [옵션] 모두 미참여 퀴즈(컬럼) 제외 처리
        if hide_empty:
            actual_cols = [t for t in target_quiz_titles if pivot_df[t].notnull().any()]
            pivot_df = pivot_df[actual_cols]
    else:
        pivot_df = pd.DataFrame(index=all_players, columns=target_quiz_titles)

    # 6. 최종 텍스트 변환 및 정리
    is_admin = st.session_state.get("is_admin", False)
    
    if is_admin:
        def format_score(x):
            try:
                if pd.isnull(x): return "-"
                return str(int(float(x)))
            except:
                return str(x)
        pivot_df = pivot_df.map(format_score)
    else:
        pivot_df = pivot_df.fillna("-")
        for col in pivot_df.columns:
            pivot_df[col] = pivot_df[col].apply(lambda x: "완료" if x != "-" else "-")

    # [신규 핵심 로직] "참여자만 표시" 체크 시, 모든 컬럼이 "-"인 사용자(행) 제외
    if only_participants:
        # ~(조건) 은 조건의 반대를 의미합니다. 즉, 모든 열이 "-"가 '아닌' 행만 남깁니다.
        pivot_df = pivot_df[~(pivot_df == "-").all(axis=1)]

    pivot_df.index.name = "사용자 ID"
    
    st.dataframe(
        pivot_df, 
        use_container_width=True, 
        height=750 
    )