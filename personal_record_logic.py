import streamlit as st
import pandas as pd


def show_personal_records(current_player, all_results):
    st.subheader("나의 학습 기록")
    st.caption("풀이 이력과 점수를 한눈에 확인하세요.")
    if not current_player.strip() and not st.session_state.get("is_admin"):
        st.info("상단에서 학습자 이름을 입력하면 내 기록을 확인할 수 있습니다.")
        return
    if not all_results:
        st.info("아직 기록된 성적이 없습니다. 첫 퀴즈를 풀어보세요.")
        return
    frame = pd.DataFrame(all_results)
    if not {"User", "Score", "QuizTitle", "Duration", "Time"}.issubset(frame.columns):
        st.warning("성적 시트의 열 이름을 확인해 주세요.")
        return
    frame["User"] = frame["User"].astype(str)
    target = current_player
    if st.session_state.get("is_admin"):
        users = sorted(frame["User"].unique())
        target = st.selectbox("기록을 볼 학습자", users, index=users.index(current_player) if current_player in users else 0)
    frame = frame[frame["User"] == target].copy()
    frame["Score"] = pd.to_numeric(frame["Score"], errors="coerce")
    frame = frame.dropna(subset=["Score"])
    if frame.empty:
        st.info(f"{target}님의 풀이 기록이 아직 없습니다.")
        return
    c1, c2 = st.columns(2)
    c1.metric("풀이 횟수", f"{len(frame)}회")
    c2.metric("평균 점수", f"{frame['Score'].mean():.0f}점")
    st.caption(f"만점 {sum(frame['Score'] == 100)}회 · 최고 점수 {frame['Score'].max():.0f}점")
    st.dataframe(frame.sort_values("Time", ascending=False)[["QuizTitle", "Score", "Duration", "Time"]].rename(columns={"QuizTitle":"퀴즈", "Score":"점수", "Duration":"시간(초)", "Time":"완료 시각"}), hide_index=True, use_container_width=True)
