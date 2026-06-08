import streamlit as st
import pandas as pd
from database import get_unique_players

def show_participation_status(season_res, all_quizzes):
    # 제목 (이모지 제거)
    st.subheader(" ")

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
    if not season_res:
        st.info("표시할 참여 기록이 없습니다.")
        return

    # [수정] 데이터프레임 강제 생성 및 컬럼명 재정의
    df = pd.DataFrame(season_res)
    
    # 만약 df가 컬럼명을 제대로 못 읽어왔다면(KeyError의 원인)
    expected_cols = ['QuizTitle', 'User', 'Score', 'Duration', 'Time']
    
    # 데이터프레임의 열 개수가 5개가 아니면 뭉쳐있다고 판단
    if df.shape[1] != 5:
        # 0번 열을 쉼표로 분리하여 5개 열로 강제 생성
        df = df.iloc[:, 0].str.split(',', expand=True)
        # 헤더를 강제로 입힘
        df.columns = expected_cols[:df.shape[1]]
    else:
        # 정상적으로 읽혔다면 컬럼명을 확실하게 보정
        df.columns = expected_cols

    # [핵심] 이제 여기에서 서식에 상관없이 0 처리 및 정제 수행
    # Score 컬럼이 숫자인지 확인하고, 아니면 0으로
    df['Score'] = pd.to_numeric(df['Score'], errors='coerce').fillna(0)
    df['User'] = df['User'].astype(str).str.strip()
    df['QuizTitle'] = df['QuizTitle'].astype(str).str.strip()

    if not df.empty:
        # [원천 차단] 데이터에서도 'test' 포함 아이디 삭제
        df = df[~df['User'].str.lower().str.contains('test', na=False)]
        
        # [옵션 차단] 데이터에서도 'guest' 포함 아이디 삭제
        if exclude_guest:
            df = df[~df['User'].str.lower().str.contains('guest', na=False)]


    st.write("--- 데이터 확인 ---")
    st.write(df.head()) # 데이터가 어떻게 생겼는지 출력
    st.write("Score 데이터 타입:", df['Score'].dtype) # 숫자인지 확인    
    df['Score'] = pd.to_numeric(df['Score'], errors='coerce')

    # 5. 피벗 테이블 생성 및 명단 재구성
    # 명단에 있는 유저만 필터링하여 데이터프레임 구성
    if not df.empty:
        # 데이터프레임의 User 리스트와 all_players를 확실하게 대조
        df = df[df['User'].isin(all_players)]
        
        # 피벗 테이블 생성: fill_value=0으로 설정하여 NaN을 0으로 처리
        pivot_df = df.pivot_table(index='User', columns='QuizTitle', values='Score', aggfunc='max')
        
        # [핵심] all_players 전체 명단을 인덱스로 강제 설정 (참여하지 않은 유저도 행으로 남김)
        pivot_df = pivot_df.reindex(index=all_players)
        
        # target_quiz_titles에 있는 컬럼만 남기거나 새로 생성
        for t in target_quiz_titles:
            if t not in pivot_df.columns:
                pivot_df[t] = None
        pivot_df = pivot_df[target_quiz_titles]
        
        # [옵션] 모두 미참여 제외 처리
        if hide_empty:
            actual_cols = [t for t in target_quiz_titles if pivot_df[t].notnull().any()]
            pivot_df = pivot_df[actual_cols]
    else:
        # 데이터가 아예 없을 경우 빈 데이터프레임 생성
        pivot_df = pd.DataFrame(index=all_players, columns=target_quiz_titles)

    # 6. 최종 텍스트 변환 및 정리
    is_admin = st.session_state.get("is_admin", False)
    
    if is_admin:
        # [관리자 모드]
        # map 함수 내에서 숫자인지 확실히 체크하여 변환합니다.
        def format_score(x):
            try:
                # 데이터가 NaN이면 "-"
                if pd.isnull(x): return "-"
                # 숫자면 정수형으로 변환
                return str(int(float(x)))
            except:
                # 숫자 변환이 안 되는 찌꺼기 데이터면 그냥 원래 값을 문자열로 반환
                return str(x)
        
        pivot_df = pivot_df.map(format_score)
    else:
        # [사용자 모드] 기존 방식대로 "완료" 표시
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