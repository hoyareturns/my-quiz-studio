import streamlit as st
from database import (get_all_quizzes, save_setting, save_chat, get_worksheet, 
                      update_quiz, delete_quiz)
from prompts import QUIZ_GENERATION_PROMPT, VIEW_OPTIONS, FEEDBACK_MODES

def show_admin_sidebar(app_settings, get_kst_time):
    # 비밀번호 및 기본 UI 설정
    ADMIN_PASSWORD = "1234"
    
    st.subheader("출제 위원실 (관리자)")
    pw = st.text_input("비밀번호", type="password", label_visibility="collapsed")
    
    if pw == ADMIN_PASSWORD:
        st.success("인증 완료")
        
        # 1. 시즌 관리
        if st.button("🔥 새 시즌 시작 (랭킹 초기화)", use_container_width=True, type="primary"):
            save_setting("season_start", get_kst_time())
            save_chat("💻 시스템", "🚨 새로운 시즌이 시작되었습니다!")
            st.rerun()
        
        st.divider()
        all_q = get_all_quizzes()
        custom_cats = [c.strip() for c in app_settings.get("custom_categories", "").split(",") if c.strip()]
        all_cats = list(dict.fromkeys(custom_cats + [q.get('Category', '미분류') for q in all_q]))
        
        # 2. 앱 기본 설정
        st.caption("⚙️ 앱 기본 설정")
        cur_def = app_settings.get('default_category', all_cats[0] if all_cats else "미분류")
        def_cat = st.selectbox("처음 열릴 카테고리", all_cats, index=all_cats.index(cur_def) if cur_def in all_cats else 0)
        if def_cat != cur_def: save_setting("default_category", def_cat); st.rerun()
        
        saved_view = app_settings.get('default_view', "퀴즈 선택")
        def_view = st.selectbox("기본 시작 화면", VIEW_OPTIONS, index=VIEW_OPTIONS.index(saved_view) if saved_view in VIEW_OPTIONS else 0)
        if def_view != saved_view: save_setting("default_view", def_view); st.rerun()

        saved_mode = app_settings.get('feedback_mode', FEEDBACK_MODES[0])
        feedback_mode = st.selectbox("채점 방식 설정", FEEDBACK_MODES, index=FEEDBACK_MODES.index(saved_mode) if saved_mode in FEEDBACK_MODES else 0)
        if feedback_mode != saved_mode: save_setting("feedback_mode", feedback_mode); st.rerun()

        # 3. 데이터 관리
        st.divider()
        with st.expander("🆕 새 퀴즈 배포"):
            nc = st.selectbox("그룹 선택", all_cats); nt = st.text_input("제목"); nx = st.text_area("AI 텍스트 붙여넣기", height=150)
            if st.button("배포", use_container_width=True):
                ws = get_worksheet("Quizzes")
                if ws and nc and nt and nx: ws.append_row([nc, nt, nx, get_kst_time()]); get_all_quizzes.clear(); st.success("배포 성공!"); st.rerun()

        with st.expander("✏️ 퀴즈 수정/삭제"):
            if all_q:
                sel_tit = st.selectbox("대상 퀴즈", [q['Title'] for q in all_q])
                curr_q = next(q for q in all_q if q['Title'] == sel_tit)
                e_cat = st.selectbox("그룹 변경", all_cats, index=all_cats.index(curr_q['Category']) if curr_q['Category'] in all_cats else 0)
                e_tit = st.text_input("제목 변경", curr_q['Title'])
                if st.button("정보 수정"): update_quiz(sel_tit, e_cat, e_tit); st.rerun()
                if st.button("퀴즈 삭제"): delete_quiz(sel_tit); st.rerun()

        with st.expander("➕ 그룹(카테고리) 추가"):
            new_g = st.text_input("새 그룹 이름", placeholder="예: 국어, 영어")
            if st.button("추가") and new_g:
                save_setting("custom_categories", app_settings.get("custom_categories","") + f",{new_g}"); st.success("추가됨!"); st.rerun()
        
        st.info("🪄 AI 출제 프롬프트")
        st.code(QUIZ_GENERATION_PROMPT, language="text")