import streamlit as st
import pandas as pd
from database import (get_all_quizzes, save_setting, save_chat, get_worksheet, 
                      update_quiz, delete_quiz, reset_all_data)
from prompts import VIEW_OPTIONS, FEEDBACK_MODES, EXTERNAL_PROMPT_TEMPLATE

def show_admin_sidebar(app_settings, get_kst_time):
    ADMIN_PASSWORD = "2662"
    
    st.subheader("출제 위원실 (관리자)")
    pw = st.text_input("비밀번호", type="password", label_visibility="collapsed")
    
    if pw == ADMIN_PASSWORD:
        st.success("인증 완료")
        
        # --- [추가] 구글 시트 백업 버튼 영역 ---
        # st.subheader(" 데이터 보관")
        # st.info("시즌 초기화 전, 현재 데이터를 구글 드라이브에 안전하게 백업해두세요.")
        
        if st.button(" 지금 즉시 구글 시트 백업 실행", use_container_width=True):
            from utils import trigger_google_sheet_backup # utils에 있는 함수 호출
            with st.spinner("구글 서버로 백업 명령을 전달 중입니다..."):
                success, msg = trigger_google_sheet_backup()
                if success:
                    st.success(" 백업이 완료되었습니다! 구글 드라이브 폴더를 확인하세요.")
                else:
                    st.error(f" {msg}")
        
        # --------------------------------------
        # --- [추가] 순위표 노출 인원 설정 구역 ---
        st.write("---")
        st.subheader(" 순위표 노출 설정")
        st.info("순위표 페이지의 '영역별 성취도' 섹션에 표시될 인원수를 설정합니다.")
        
        # 1. 현재 설정된 값 불러오기 (기본값 3)
        # app_settings는 show_admin_sidebar의 인자로 전달받은 값을 활용합니다.
        current_top_count = int(app_settings.get('top_achievers_count', 3))
        
        # 2. 숫자 입력 위젯
        new_top_count = st.number_input(
            "우수 성취자 노출 인원 (TOP N)", 
            min_value=1, 
            max_value=1000, 
            value=current_top_count,
            step=1,
            help="모든 유저를 보고 싶다면 인원수를 넉넉하게 설정하세요."
        )
        
        # 3. 설정 저장 버튼
        if st.button("순위 노출 인원 설정 저장", use_container_width=True):
            # database.py에서 임포트한 save_setting 함수를 사용합니다.
            success, msg = save_setting("top_achievers_count", str(new_top_count))
            if success:
                st.success(f"설정 완료! 이제 순위표에 TOP {new_top_count}명이 표시됩니다.")
                # 즉시 반영을 위해 앱 재실행
                st.rerun()
            else:
                st.error(f"설정 저장 실패: {msg}")



        with st.expander(" 새 시즌 시작 (데이터 전체 초기화)", expanded=False):
            st.warning("이 작업은 '퀴즈 목록', '학습 결과', '오답 기록'을 모두 영구 삭제합니다. (복구 불가)")
            
            # 삭제 전용 비밀번호 재확인
            confirm_pw = st.text_input("초기화 확인을 위해 비밀번호를 다시 입력하세요", type="password", key="reset_confirm_pw")
            
            if st.button(" 모든 데이터 삭제 및 시즌 초기화 실행", use_container_width=True, type="primary"):
                if confirm_pw == ADMIN_PASSWORD:
                    with st.spinner("데이터를 초기화 중입니다..."):
                        success, msg = reset_all_data()
                        if success:
                            # 시즌 시작 로그 기록
                            save_setting("season_start", get_kst_time())
                            save_chat("시스템", "새로운 시즌이 시작되었습니다! 모든 데이터가 초기화되었습니다.")
                            
                            st.success(msg)
                            get_all_quizzes.clear() # 캐시 비우기
                            st.rerun()
                        else:
                            st.error(msg)
                else:
                    st.error("비밀번호가 일치하지 않습니다.")
        
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