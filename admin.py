import streamlit as st
from database import (get_all_quizzes, save_setting, save_chat, get_worksheet, 
                      update_quiz, delete_quiz, save_quiz)

# [수정] 하드코딩 변수 대신 get_ui_labels 함수를 불러옵니다.
from prompts import get_ui_labels, FEEDBACK_MODES, EXTERNAL_PROMPT_TEMPLATE

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
        
        # --- [핵심 수정] get_ui_labels를 이용해 선택 옵션을 동적으로 생성 ---
        p_labels = get_ui_labels("personal")
        w_labels = get_ui_labels("work")
        
        # 두 모드의 탭 이름을 하나로 합치고, 중복(오답 정복, 개인 기록 등)을 제거합니다.
        dynamic_view_options = list(dict.fromkeys([
            p_labels["TAB_QUIZ"], p_labels["TAB_REVIEW"], p_labels["TAB_RECORDS"], p_labels["TAB_RANK"], p_labels["TAB_CHAT"],
            w_labels["TAB_QUIZ"], w_labels["TAB_REVIEW"], w_labels["TAB_RECORDS"], w_labels["TAB_RANK"], w_labels["TAB_CHAT"]
        ]))
        
        default_view = st.selectbox("처음 열릴 탭", dynamic_view_options, 
                                    index=dynamic_view_options.index(app_settings.get('default_view', dynamic_view_options[0])) if app_settings.get('default_view') in dynamic_view_options else 0)
        # ---------------------------------------------------------------
        
        f_mode = st.selectbox("피드백 모드", FEEDBACK_MODES, 
                              index=FEEDBACK_MODES.index(app_settings.get('feedback_mode', '실시간 팩폭')) if app_settings.get('feedback_mode') in FEEDBACK_MODES else 0)
        
        if st.button("설정 저장", use_container_width=True):
            save_setting("default_view", default_view)
            save_setting("feedback_mode", f_mode)
            st.success("저장됨")
        
        st.divider()
        
        with st.expander("AI 출제 프롬프트 확인 (복사용)"):
            st.caption("노트북LM 등 외부 AI에서 정밀 출제 시 아래 내용을 복사해서 사용하세요.")
            st.text_area("프롬프트 양식", EXTERNAL_PROMPT_TEMPLATE, height=300)

        with st.expander("새 퀴즈 배포"):
            nc = st.selectbox("그룹 선택", all_cats, key="admin_new_cat")
            nt = st.text_input("제목", key="admin_new_title")
            nx = st.text_area("AI 텍스트 붙여넣기", height=150, key="admin_new_content")
            
            is_work_new = st.checkbox("💼 업무용 퀴즈로 등록", value=False)
            
            if st.button("배포", use_container_width=True):
                if nc and nt and nx:
                    save_quiz(nc, nt, nx, is_work_new)
                    st.success("배포 성공!")
                    st.rerun()

        with st.expander("퀴즈 수정/삭제"):
            if all_q:
                sel_tit = st.selectbox("대상 퀴즈", [q['Title'] for q in all_q])
                curr_q = next(q for q in all_q if q['Title'] == sel_tit)
                
                e_cat = st.selectbox("그룹 변경", all_cats, 
                                     index=all_cats.index(curr_q.get('Category', '미분류')) if curr_q.get('Category') in all_cats else 0)
                e_tit = st.text_input("제목 수정", value=curr_q['Title'])
                e_con = st.text_area("내용 수정", value=curr_q['Content'], height=200)
                
                current_is_work = (str(curr_q.get('IsWork', 'X')) == "O")
                is_work_edit = st.checkbox("💼 업무용 퀴즈 지정", value=current_is_work, key="admin_edit_work")
                
                c1, c2 = st.columns(2)
                if c1.button("수정 저장", use_container_width=True):
                    if update_quiz(sel_tit, e_cat, e_tit, e_con, is_work_edit):
                        st.success("수정되었습니다.")
                        st.rerun()
                
                if c2.button("삭제", type="primary", use_container_width=True):
                    if delete_quiz(sel_tit):
                        st.success("삭제되었습니다.")
                        st.rerun()