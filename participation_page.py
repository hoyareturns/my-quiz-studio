import streamlit as st
import pandas as pd

def show_participation_status(season_res, all_quizzes):
    st.subheader(" 참여 현황")

    # 1. 퀴즈 데이터에서 유효한 카테고리(그룹) 목록만 추출
    categories = sorted(list(set(q.get('Category', '미분류') for q in all_quizzes if q.get('Category'))))
    category_options = ["전체 퀴즈"] + categories
    
    # 카테고리 선택 드롭박스 생성
    selected_cat = st.selectbox("📂 퀴즈 그룹 선택", category_options)

    # 2. 선택된 그룹에 따라 결과 데이터(season_res) 필터링
    if selected_cat == "전체 퀴즈":
        display_res = season_res
    else:
        # 1단계: 선택한 카테고리에 속한 퀴즈들의 '제목(Title)' 리스트를 뽑아냄
        target_quiz_titles = [q.get('Title') for q in all_quizzes if q.get('Category', '미분류') == selected_cat]
        
        # 2단계: 결과 데이터(season_res) 중에서 위에서 뽑은 퀴즈 제목과 일치하는 기록만 남김
        display_res = [r for r in season_res if r.get('QuizTitle') in target_quiz_titles]

    st.write("---")

    # 3. 데이터 시각화 및 예외 처리
    if not display_res:
        st.info(f"'{selected_cat}' 그룹에 해당하는 참여 기록이 없습니다.")
        return

    # 필터링된 결과를 판다스 데이터프레임으로 변환
    df = pd.DataFrame(display_res)
    
    # 'User' 컬럼이 시트에 정상적으로 존재하는지 확인 후 집계
    if 'User' in df.columns:
        # 사용자별 참여 횟수 카운트 및 내림차순 정렬
        participation_counts = df['User'].value_counts().reset_index()
        participation_counts.columns = ['사용자(ID)', '참여 횟수(회)']
        
        # 상단 요약 정보 출력
        st.success(f"🔍 **{selected_cat}** 요약: 총 **{len(df)}**회 참여 / 고유 참여자 **{len(participation_counts)}**명")
        
        # 깔끔한 표 형태로 화면에 출력
        st.dataframe(participation_counts, use_container_width=True, hide_index=True)
    else:
        st.warning("데이터에 'User' 컬럼이 없어 집계할 수 없습니다. Results 시트의 헤더를 확인해주세요.")