import streamlit as st
import pandas as pd

def show_participation_status(season_res, all_quizzes):
    st.subheader(" 참여 현황 (퀴즈별 성취도)")

    # 1. 퀴즈 데이터에서 유효한 카테고리(그룹) 목록 추출
    categories = sorted(list(set(q.get('Category', '미분류') for q in all_quizzes if q.get('Category'))))
    
    # [변경 사항 1] "전체 퀴즈" 옵션을 리스트의 마지막으로 이동
    category_options = categories + ["전체 퀴즈"]
    
    # UI 배치: 드롭박스와 옵션들을 배치
    col1, col2, col3 = st.columns([2, 1, 1.2])
    with col1:
        selected_cat = st.selectbox(" 퀴즈 그룹 선택", category_options, index=len(category_options)-1)
    with col2:
        exclude_guest = st.checkbox("Guest 제외", value=True)
    with col3:
        # [변경 사항 2] 미참여 퀴즈 제외 옵션 (기본값: True)
        hide_empty = st.checkbox("미참여 퀴즈 제외", value=True)

    # 2. 선택된 그룹에 속한 "대상 퀴즈 제목 목록" 추출
    if selected_cat == "전체 퀴즈":
        target_quiz_titles = sorted(list(set(q.get('Title') for q in all_quizzes)))
    else:
        target_quiz_titles = sorted(list(set(q.get('Title') for q in all_quizzes if q.get('Category', '미분류') == selected_cat)))

    if not target_quiz_titles:
        st.info(f"'{selected_cat}' 그룹에 등록된 퀴즈가 없습니다.")
        return

    # 결과 데이터 필터링
    display_res = [r for r in season_res if r.get('QuizTitle') in target_quiz_titles]

    # Guest 계정 필터링
    if exclude_guest:
        display_res = [r for r in display_res if "Guest" not in str(r.get('User', ''))]

    st.write("---")

    if not display_res:
        st.info("선택한 조건에 해당하는 참여 기록이 없습니다.")
        return

    # 3. 데이터프레임 생성 및 피벗 테이블 변환
    df = pd.DataFrame(display_res)
    
    if 'User' in df.columns and 'QuizTitle' in df.columns and 'Score' in df.columns:
        # 점수 데이터 숫자 변환
        df['Score'] = pd.to_numeric(df['Score'], errors='coerce')
        
        # 피벗 테이블 생성
        pivot_df = df.pivot_table(index='User', columns='QuizTitle', values='Score', aggfunc='max')
        
        # [변경 사항 2 핵심] 미참여 퀴즈 제외 로직
        if hide_empty:
            # 현재 결과 데이터(display_res)에 존재하는 퀴즈 제목들만 필터링하여 컬럼 유지
            actual_quiz_in_data = [title for title in target_quiz_titles if title in pivot_df.columns]
            pivot_df = pivot_df[actual_quiz_in_data]
            final_quiz_columns = actual_quiz_in_data
        else:
            # 미참여 퀴즈도 모두 포함하는 경우 (기존 로직)
            for title in target_quiz_titles:
                if title not in pivot_df.columns:
                    pivot_df[title] = None
            pivot_df = pivot_df[target_quiz_titles]
            final_quiz_columns = target_quiz_titles
                
        # 점수 존재 여부에 따라 "완료" 또는 "-" 표시
        for col in final_quiz_columns:
            pivot_df[col] = pivot_df[col].apply(lambda x: "완료" if pd.notnull(x) else "-")
            
        # 표 형식 정리
        pivot_df = pivot_df.reset_index()
        pivot_df.rename(columns={'User': '이름'}, inplace=True)
        
        # 4. 화면 출력
        st.success(f"🔍 **{selected_cat}** 현황: 총 {len(pivot_df)}명 참여")
        st.dataframe(pivot_df, use_container_width=True, hide_index=True)
        
    else:
        st.warning("필요한 데이터 컬럼(User, QuizTitle 등)을 찾을 수 없습니다.")