import streamlit as st
import pandas as pd
from database import get_unique_players
from utils import natural_sort_key


def show_participation_status(season_res, all_quizzes):
    st.subheader("참여 현황")
    st.caption("퀴즈별 참여 여부를 확인하세요. 관리자에게는 최고 점수가 표시됩니다.")
    categories = sorted({str(q.get("Category") or "미분류") for q in all_quizzes}, key=natural_sort_key)
    category = st.selectbox("퀴즈 분류", ["전체 퀴즈"] + categories)
    with st.expander("표시 조건"):
        exclude_guest = st.checkbox("Guest 제외", value=True)
        hide_empty = st.checkbox("참여 기록 없는 퀴즈 숨기기", value=True)
        only_participants = st.checkbox("참여자만 표시", value=True)
    if not season_res:
        st.info("표시할 참여 기록이 없습니다.")
        return
    frame = pd.DataFrame(season_res)
    required = {"User", "QuizTitle", "Score"}
    if not required.issubset(frame.columns):
        st.warning("성적 시트에 User, QuizTitle, Score 열이 필요합니다.")
        return
    frame["User"] = frame["User"].astype(str).str.strip()
    frame["QuizTitle"] = frame["QuizTitle"].astype(str)
    frame["Score"] = pd.to_numeric(frame["Score"], errors="coerce")
    players = sorted({str(r.get("User", "")).strip() for r in season_res if r.get("User")}, key=natural_sort_key)
    players = [p for p in players if 'test' not in p.lower() and (not exclude_guest or 'guest' not in p.lower())]
    frame = frame[frame["User"].isin(players)]
    titles = sorted({q["Title"] for q in all_quizzes if category == "전체 퀴즈" or q.get("Category") == category}, key=natural_sort_key)
    table = frame.pivot_table(index="User", columns="QuizTitle", values="Score", aggfunc="max").reindex(index=players, columns=titles)
    if hide_empty:
        table = table.dropna(axis=1, how="all")
    if only_participants:
        table = table.dropna(axis=0, how="all")
    if table.empty:
        st.info("선택한 조건에 맞는 참여 기록이 없습니다.")
        return
    if st.session_state.get("is_admin"):
        table = table.map(lambda v: "-" if pd.isna(v) else str(int(v)))
    else:
        table = table.map(lambda v: "-" if pd.isna(v) else "완료")
    table.index.name = "학습자"
    st.caption(f"{len(table)}명 · {len(table.columns)}개 퀴즈 · 표를 좌우로 밀어 전체 내용을 볼 수 있습니다.")
    st.dataframe(table, use_container_width=True, height=min(520, 40 + 35 * len(table)))
