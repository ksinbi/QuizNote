"""Quiz Note 프런트엔드 (Streamlit)

실행: frontend 폴더에서  streamlit run app.py
흐름: 로그인 → PDF 업로드 → 조건 설정 → 문제 생성 → 채팅형 풀이 → 결과 · 저장 → 새 학습/종료
"""
import streamlit as st

import state
from components import ui
from views import auth, done, generating, history, notion_dialog, quiz, settings, summary, upload

st.set_page_config(page_title="Quiz Note · PDF AI 학습", page_icon="🎓", layout="wide", initial_sidebar_state="collapsed")
state.init()
ui.inject_css()

s = state.ss()
if s.auth_expired:
    state.logout()
    st.toast("로그인이 만료되었어요. 다시 로그인해주세요.", icon="🔒")
state.restore_login()

if not s.user:
    auth.render()
    state.render_cookie_js()
    st.stop()

# ---------- 상단 바 ----------
brand, nav, user_col, logout_col = st.columns([2.2, 3, 2, 1], vertical_alignment="center")
with brand:
    ui.html_block('<div class="qn-brand"><i>Q</i>Quiz Note</div>')
with nav:
    labels = {"study": "학습하기", "history": "학습 기록"}
    view = st.segmented_control("메뉴", list(labels), default=s.view, format_func=labels.get, required=True, label_visibility="collapsed", key=f"nav_{s.view}")
    if view and view != s.view:
        s.view = view
        st.rerun()
with user_col:
    ui.html_block(f'<div class="qn-user">👤 {ui.esc(s.user.get("name") or s.user["email"])}</div>')
if logout_col.button("로그아웃", width="stretch"):
    state.logout()
    st.rerun()
st.divider()

# ---------- 본문 ----------
STEP_VIEWS = {
    "upload": upload.render,
    "settings": settings.render,
    "generating": generating.render,
    "quiz": quiz.render,
    "summary": summary.render,
    "done": done.render,
}

if s.view == "history":
    history.render()
else:
    flow = state.flow()
    step = flow["step"] if flow.get("upload") else "upload"
    ui.step_indicator(step)
    STEP_VIEWS[step]()

notion_dialog.render_if_open()
state.render_cookie_js()
