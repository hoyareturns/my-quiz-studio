import streamlit as st
from database import (get_all_quizzes, save_setting, save_chat, get_worksheet, 
                      update_quiz, delete_quiz)
# EXTERNAL_PROMPT_TEMPLATE를 추가로 불러옵니다.
from prompts import VIEW_OPTIONS, FEEDBACK_MODES, EXTERNAL_PROMPT_TEMPLATE

def show_admin_sidebar(app_settings, get_kst_time):
    ADMIN_PASSWORD = "1234"
    
    st.subheader("출제 위원실 (관리자)")
    pw = st.text_input("비밀번호", type="password", label_visibility="collapsed")
    
    if pw == ADMIN_PASSWORD:
        st.success("인증 완료")
        
        if st.button("새 시즌 시작 (랭킹 초기화)", use_container_width=True, type="primary"):
            save_setting("season_start", get_kst_time())
            save_chat("시스템", "새로운 시즌이 시작되었습니다!")
            st.rerun()
        
        st.divider()
        all_q = get_all_quizzes()
        custom_cats = [c.strip() for c in app_settings.get("custom_categories", "").split(",") if c.strip()]
        all_cats = list(dict.fromkeys(custom_cats + [q.get('Category', '미분류') for q in all_q]))
        
        st.caption("앱 기본 설정")
        default_view = st.selectbox("처음 열릴 탭", VIEW_OPTIONS, index=VIEW_OPTIONS.index(app_settings.get('default_view', VIEW_OPTIONS[0])) if app_settings.get('default_view') in VIEW_OPTIONS else 0)
        if default_view != app_settings.get('default_view'):
            save_setting("default_view", default_view)
            st.rerun()
            
        default_cat = st.selectbox("처음 열릴 카테고리", all_cats, index=all_cats.index(app_settings.get('default_category', all_cats[0])) if app_settings.get('default_category') in all_cats else 0)
        if default_cat != app_settings.get('default_category'):
            save_setting("default_category", default_cat)
            st.rerun()

        cust_cat = st.text_input("카테고리 목록 (쉼표 구분)", app_settings.get("custom_categories", ""))
        if st.button("카테고리 저장", use_container_width=True):
            save_setting("custom_categories", cust_cat)
            st.rerun()

        feedback_mode = st.selectbox("피드백 모드", FEEDBACK_MODES, index=FEEDBACK_MODES.index(app_settings.get('feedback_mode', FEEDBACK_MODES[0])) if app_settings.get('feedback_mode') in FEEDBACK_MODES else 0)
        if feedback_mode != app_settings.get('feedback_mode'):
            save_setting("feedback_mode", feedback_mode)
            st.rerun()

        st.divider()
        
        with st.expander("AI 출제 프롬프트 확인 (복사용)"):
            st.caption("노트북LM 등 외부 AI에서 정밀 출제 시 아래 내용을 복사해서 사용하세요.")
            # 앱 내부용이 아닌 외부용 프롬프트(주관식 포함)를 노출합니다.
            st.text_area("프롬프트 양식", EXTERNAL_PROMPT_TEMPLATE, height=300)

        with st.expander("새 퀴즈 배포"):
            nc = st.selectbox("그룹 선택", all_cats)
            nt = st.text_input("제목")
            nx = st.text_area("AI 텍스트 붙여넣기", height=150)
            if st.button("배포", use_container_width=True):
                ws = get_worksheet("Quizzes")
                if ws and nc and nt and nx:
                    ws.append_row([nc, nt, nx, get_kst_time()])
                    get_all_quizzes.clear()
                    st.success("배포 성공!")
                    st.rerun()

        with st.expander("퀴즈 수정/삭제"):
            if all_q:
                sel_tit = st.selectbox("대상 퀴즈", [q['Title'] for q in all_q])
                curr_q = next(q for q in all_q if q['Title'] == sel_tit)
                e_cat = st.selectbox("그룹 변경", all_cats, index=all_cats.index(curr_q['Category']) if curr_q['Category'] in all_cats else 0)
                e_tit = st.text_input("제목 변경", curr_q['Title'])
                if st.button("정보 수정", use_container_width=True):
                    update_quiz(sel_tit, e_cat, e_tit)
                    st.rerun()
                if st.button("퀴즈 삭제", use_container_width=True):
                    if delete_quiz(sel_tit):
                        st.rerun()

# --- 추가된 섹션: 최근 접속자 현황 ---
        st.divider()
        with st.expander(" 최근 접속 및 학습 현황 (최근 20개)"):
            ws_res = get_worksheet("Results") # 결과 시트 가져오기
            if ws_res:
                res_data = ws_res.get_all_records()
                if res_data:
                    # 데이터프레임 변환 및 전처리
                    res_df = pd.DataFrame(res_data)
                    
                    # 가장 최근 데이터가 아래에 쌓이므로, 위아래를 뒤집어서 최신순으로 정렬
                    res_df = res_df.iloc[::-1].head(20)
                    
                    # 화면에 보여줄 컬럼만 선택 (시트에 'Timestamp' 또는 '날짜' 컬럼이 있다고 가정)
                    # 만약 컬럼명이 다르다면 시트의 헤더에 맞춰 'User', 'QuizTitle' 등으로 수정하세요.
                    display_cols = [c for c in ['User', 'QuizTitle', 'Score', 'Timestamp'] if c in res_df.columns]
                    
                    if display_cols:
                        st.dataframe(
                            res_df[display_cols].rename(columns={
                                'User': 'ID/이름',
                                'QuizTitle': '퀴즈명',
                                'Score': '점수',
                                'Timestamp': '시간'
                            }),
                            use_container_width=True,
                            hide_index=True
                        )
                    else:
                        st.table(res_df.head(10)) # 컬럼명이 불확실할 경우 전체 출력
                else:
                    st.info("아직 기록된 학습 데이터가 없습니다.")
            else:
                st.error("Results 시트를 불러올 수 없습니다.")