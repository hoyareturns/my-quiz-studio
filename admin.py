import streamlit as st
import pandas as pd
from database import (get_all_quizzes, save_setting, save_chat, get_worksheet, 
                      update_quiz, delete_quiz)
# EXTERNAL_PROMPT_TEMPLATE를 추가로 불러옵니다.
from prompts import VIEW_OPTIONS, FEEDBACK_MODES, EXTERNAL_PROMPT_TEMPLATE

def show_admin_sidebar(app_settings, get_kst_time):
    ADMIN_PASSWORD = "2662"
    
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

        # --- 수정된 섹션: 최근 접속 및 학습 현황 (사용자 정의 순서) ---
        st.divider()
        with st.expander(" 최근 접속 및 학습 현황", expanded=True):
            ws_res = get_worksheet("Results")
            if ws_res:
                res_data = ws_res.get_all_records()
                if res_data:
                    res_df = pd.DataFrame(res_data)
                    
                    # 1. 최신 데이터가 위로 오도록 역순 정렬
                    res_df = res_df.iloc[::-1].head(20)
                    
                    # 2. 사용자 요청 순서대로 매칭 정의
                    # 시트 헤더: User, Quiz Title, Score, Time, Duration
                    display_map = {
                        'User': 'ID',
                        'QuizTitle': '퀴즈명',
                        'Score': '점수',
                        'Time': '접속시간',
                        'Duration': '소요시간'
                    }
                    
                    # 3. [핵심] 보여줄 컬럼의 '순서'를 리스트로 고정합니다.
                    requested_order = ['User', 'QuizTitle', 'Score', 'Time', 'Duration']
                    
                    # 4. 실제 시트에 존재하는 컬럼만 골라내어 위에서 정한 순서를 유지합니다.
                    existing_cols = [col for col in requested_order if col in res_df.columns]
                    
                    if existing_cols:
                        st.dataframe(
                            res_df[existing_cols].rename(columns=display_map),
                            use_container_width=True,
                            hide_index=True
                        )
                    else:
                        st.warning("시트의 헤더명(User, Quiz Title 등)을 확인해주세요.")
                else:
                    st.info("기록된 데이터가 없습니다.")
            else:
                st.error("Results 시트를 찾을 수 없습니다.")    