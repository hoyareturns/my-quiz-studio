import streamlit as st
from html import escape
from database import get_chats, save_chat

def show_chat_room(player_name):
    st.markdown("<div id='chat_top_anchor'></div>", unsafe_allow_html=True)
    c1, c2 = st.columns([3, 1])
    c1.subheader("학습 피드백 게시판")
    if c2.button("새로고침", key="chat_refresh"): 
        get_chats.clear()
        st.rerun()
    
    chat_box = st.container(height=400)
    for original in get_chats():
        c = {k: escape(str(v)) for k, v in original.items()}
        t_str = str(c.get('Time', ''))[:16]
        cls = "chat-sys" if c["User"] == "시스템" else "chat-user"
        chat_box.markdown(f'<div class="chat-msg"><span class="{cls}">{c["User"]}:</span>{c["Message"]}<span class="chat-time">{t_str}</span></div>', unsafe_allow_html=True)
    
    with st.form("chat_input", clear_on_submit=True):
        m = st.text_input("메시지 입력", label_visibility="collapsed")
        if st.form_submit_button("전송", use_container_width=True, disabled=not player_name.strip()) and m.strip():
            try:
                save_chat(player_name, m.strip())
                st.rerun()
            except Exception:
                st.error("전송하지 못했습니다. 연결 상태를 확인해 주세요.")