"""Quiz Note 프런트엔드 (Streamlit)

실행: frontend 폴더에서  streamlit run app.py
흐름: 로그인 → PDF 업로드 · 조건 설정 → 문제 생성 → 채팅형 풀이 → 결과 · 저장 → 새 학습/종료
"""
import streamlit as st

import state
from components import ui
from views import auth, done, generating, history, notion_dialog, notion_page, quiz, setup, summary

st.set_page_config(page_title="Quiz Note · PDF AI 학습", page_icon=":material/quiz:", layout="wide", initial_sidebar_state="collapsed")
state.init()
ui.inject_css()

s = state.ss()
if s.auth_expired:
    state.logout()
    st.toast("로그인이 만료되었어요. 다시 로그인해주세요.", icon=":material/lock:")
state.restore_login()

if not s.user:
    auth.render()
    ui.footer()
    state.render_cookie_js()
    st.stop()

# ---------- 상단 바: 로고 · 메뉴 · 계정 ----------
MENU = {"study": "새 문제 만들기", "history": "내 문제집", "notion": "Notion 연동"}


def _go_view(view: str) -> None:
    s.view = view
    s.history_selected = None


with st.container(key="qn_header"):
    brand_col, nav_col, user_col = st.columns([1, 2, 1], vertical_alignment="center")
    with brand_col:
        ui.html_block(ui.brand())
    with nav_col, st.container(horizontal=True, key="qn_nav"):
        for view, label in MENU.items():
            st.button(label, key=f"nav_{view}", type="primary" if s.view == view else "tertiary", on_click=_go_view, args=(view,))
    with user_col, st.container(horizontal=True, horizontal_alignment="right"), st.popover(
        "", icon=":material/person:", key="qn_profile", help="내 계정"
    ):
        ui.html_block(
            f'<div class="qn-who"><b>{ui.esc(s.user.get("name") or "학습자")}</b><small>{ui.esc(s.user["email"])}</small></div>'
        )
        if st.button("로그아웃", icon=":material/logout:", width="stretch"):
            state.logout()
            st.rerun()

# ---------- 본문 ----------
STEP_VIEWS = {
    "upload": setup.render,
    "settings": setup.render,  # 업로드와 조건 설정은 한 화면 (예전 저장 단계 호환)
    "generating": generating.render,
    "quiz": quiz.render,
    "summary": summary.render,
    "done": done.render,
}

if s.view == "history":
    history.render()
elif s.view == "notion":
    notion_page.render()
else:
    flow = state.flow()
    step = flow["step"] if flow.get("upload") else "upload"
    STEP_VIEWS[step]()

ui.footer()
notion_dialog.render_if_open()
state.render_cookie_js()
