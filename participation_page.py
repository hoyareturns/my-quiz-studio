import streamlit as st
import pandas as pd

def show_participation_status(season_res, all_quizzes):
    st.subheader("📊 참여 현황 (퀴즈별 성취도)")

    # 1. 퀴즈 데이터에서 유효한 카테고리(그룹) 목록만 추출
    categories = sorted(list(set(q.get('Category', '미분류') for q in all_quizzes if q.get('Category'))))
    category_options = ["전체 퀴즈"] + categories
    
    # 카테고리 선택 드롭박스
    selected_cat = st.selectbox("📂 퀴즈 그룹 선택", category_options)

    # 2. 선택된 그룹에 속한 "퀴즈 제목 목록"을 추출 (컬럼으로 사용할 예정)
    if selected_cat == "전체 퀴즈":
        target_quiz_titles = sorted(list(set(q.get('Title') for q in all_quizzes)))
    else:
        target_quiz_titles = sorted(list(set(q.get('Title') for q in all_quizzes if q.get('Category', '미분류') == selected_cat)))

    # 해당 그룹의 퀴즈가 하나도 없으면 안내 후 종료
    if not target_quiz_titles:
        st.info(f"'{selected_cat}' 그룹에 등록된 퀴즈가 없습니다.")
        return

    # 결과 데이터 중 해당 퀴즈 제목을 가진 데이터만 필터링
    display_res = [r for r in season_res if r.get('QuizTitle') in target_quiz_titles]

    st.write("---")

    if not display_res:
        st.info(f"'{selected_cat}' 그룹에 해당하는 참여 기록이 없습니다.")
        return

    # 3. 데이터프레임 생성 및 피벗 테이블(가로/세로 표) 변환
    df = pd.DataFrame(display_res)
    
    if 'User' in df.columns and 'QuizTitle' in df.columns and 'Score' in df.columns:
        # 점수를 숫자로 강제 변환 (문자열 방지, 오류 시 0 처리)
        df['Score'] = pd.to_numeric(df['Score'], errors='coerce').fillna(0)
        
        # [핵심] 피벗 테이블 생성: 행=User, 열=QuizTitle, 값=Score(여러 번 풀었으면 최고 점수 max)
        pivot_df = df.pivot_table(index='User', columns='QuizTitle', values='Score', aggfunc='max')
        
        # 그룹에는 속해있지만 아직 아무도 풀지 않은 퀴즈도 '빈 열'로 표시되도록 강제 추가
        for title in target_quiz_titles:
            if title not in pivot_df.columns:
                pivot_df[title] = None
                
        # 퀴즈 제목 순서를 원래 리스트대로 깔끔하게 정렬
        pivot_df = pivot_df[target_quiz_titles]
        
        # 빈 칸(NaN) 처리 및 점수를 보기 좋게 정수형 문자열로 변환 (예: 100.0 -> "100")
        for col in target_quiz_titles:
            pivot_df[col] = pivot_df[col].apply(lambda x: str(int(x)) if pd.notnull(x) else "-")
            
        # 인덱스(User)를 일반 컬럼으로 꺼내고 이름을 '이름'으로 변경
        pivot_df = pivot_df.reset_index()
        pivot_df.rename(columns={'User': '이름'}, inplace=True)
        
        # 4. 화면 출력
        st.success(f"🔍 **{selected_cat}** 현황: 총 {len(pivot_df)}명 참여")
        st.dataframe(pivot_df, use_container_width=True, hide_index=True)
        
    else:
        st.warning("데이터에 'User', 'QuizTitle', 'Score' 컬럼이 없어 표를 생성할 수 없습니다.")