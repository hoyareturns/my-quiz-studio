# participation_page.py 수정
import streamlit as st
import pandas as pd

def show_participation_status(season_res, all_quizzes):
    st.subheader(" 전체 참여 현황 분석")
    
    if not season_res:
        st.info("기록된 참여 현황이 없습니다.")
        return

    # 1. 퀴즈명-카테고리 매핑 딕셔너리 생성
    quiz_to_cat = {q['Title']: q.get('Category', '미분류') for q in all_quizzes}
    categories = sorted(list(set(quiz_to_cat.values())))
    
    # 2. 드롭박스(필터) 생성
    # [전체] 옵션을 가장 아래가 아닌 관례상 가장 위에 두거나, 원하시는 대로 아래에 배치 가능합니다.
    filter_options = categories + ["전체"]
    selected_cat = st.selectbox("📂 카테고리 필터", filter_options, index=len(filter_options)-1)

    # 3. 데이터프레임 생성 및 데이터 정리
    df = pd.DataFrame(season_res)
    
    # 카테고리 정보 병합
    df['Category'] = df['QuizTitle'].map(quiz_to_cat).fillna('미분류')
    
    # 필터 적용
    if selected_cat != "전체":
        df = df[df['Category'] == selected_cat]

    if df.empty:
        st.warning(f"'{selected_cat}' 카테고리에 해당하는 참여 기록이 없습니다.")
        return

    # 4. 출력용 데이터 정리 (이미지 양식 기준)
    df = df.sort_values(by='Time', ascending=False)
    
    display_df = df.copy()
    display_df['Score'] = display_df['Score'].apply(lambda x: f"{int(float(x))}점")
    display_df['Duration'] = display_df['Duration'].apply(lambda x: f"{int(float(x))}초")

    column_map = {
        'User': '사용자 ID',
        'QuizTitle': '퀴즈 명칭',
        'Score': '취득 점수',
        'Duration': '소요 시간',
        'Time': '완료 일시'
    }
    
    display_df = display_df[list(column_map.keys())].rename(columns=column_map)

    # 5. 테이블 출력
    st.dataframe(
        display_df,
        use_container_width=True,
        hide_index=True,
        column_config={
            "완료 일시": st.column_config.DatetimeColumn("완료 일시", format="YYYY-MM-DD HH:mm"),
        }
    )