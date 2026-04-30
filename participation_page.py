import streamlit as st
import pandas as pd

def show_participation_status(season_res, all_quizzes):
    st.subheader("📊 참여 현황 (퀴즈별 성취도)")

    # 1. 퀴즈 데이터에서 유효한 카테고리(그룹) 목록 추출
    categories = sorted(list(set(q.get('Category', '미분류') for q in all_quizzes if q.get('Category'))))
    category_options = ["전체 퀴즈"] + categories
    
    # UI 배치: 드롭박스와 Guest 제외 체크박스를 나란히 배치
    col1, col2 = st.columns([3, 1])
    with col1:
        selected_cat = st.selectbox("📂 퀴즈 그룹 선택", category_options, label_visibility="collapsed")
    with col2:
        # [핵심 기능 1] Guest 제외 옵션 (기본값: True)
        exclude_guest = st.checkbox("Guest 제외", value=True)

    # 2. 선택된 그룹에 속한 "퀴즈 제목 목록" 추출
    if selected_cat == "전체 퀴즈":
        target_quiz_titles = sorted(list(set(q.get('Title') for q in all_quizzes)))
    else:
        target_quiz_titles = sorted(list(set(q.get('Title') for q in all_quizzes if q.get('Category', '미분류') == selected_cat)))

    if not target_quiz_titles:
        st.info(f"'{selected_cat}' 그룹에 등록된 퀴즈가 없습니다.")
        return

    # 결과 데이터 1차 필터링 (선택한 퀴즈에 해당하는 기록만)
    display_res = [r for r in season_res if r.get('QuizTitle') in target_quiz_titles]

    # [핵심 기능 1] Guest 계정 필터링 적용
    if exclude_guest:
        # User 이름에 "Guest"라는 글자가 포함되지 않은 데이터만 남김
        display_res = [r for r in display_res if "Guest" not in str(r.get('User', ''))]

    st.write("---")

    if not display_res:
        st.info("선택한 조건에 해당하는 참여 기록이 없습니다.")
        return

    # 3. 데이터프레임 생성 및 피벗 테이블 변환
    df = pd.DataFrame(display_res)
    
    if 'User' in df.columns and 'QuizTitle' in df.columns and 'Score' in df.columns:
        # 점수가 있는지 확인하기 위해 숫자로 변환
        df['Score'] = pd.to_numeric(df['Score'], errors='coerce')
        
        # 피벗 테이블 생성: 행=User, 열=QuizTitle
        pivot_df = df.pivot_table(index='User', columns='QuizTitle', values='Score', aggfunc='max')
        
        # 그룹에는 속해있지만 아직 아무도 풀지 않은 퀴즈를 빈 열로 강제 추가
        for title in target_quiz_titles:
            if title not in pivot_df.columns:
                pivot_df[title] = None
                
        # 퀴즈 제목 순서 정렬
        pivot_df = pivot_df[target_quiz_titles]
        
        # [핵심 기능 2] 점수가 존재하면 "완료", 없으면 "-" 기호로 표시
        for col in target_quiz_titles:
            pivot_df[col] = pivot_df[col].apply(lambda x: "완료" if pd.notnull(x) else "-")
            
        # 인덱스(User)를 일반 컬럼으로 꺼내고 이름을 변경
        pivot_df = pivot_df.reset_index()
        pivot_df.rename(columns={'User': '이름'}, inplace=True)
        
        # 4. 화면 출력
        st.success(f"🔍 **{selected_cat}** 현황: 총 {len(pivot_df)}명 참여")
        st.dataframe(pivot_df, use_container_width=True, hide_index=True)
        
    else:
        st.warning("데이터에 'User', 'QuizTitle', 'Score' 컬럼이 없어 표를 생성할 수 없습니다.")