"""로그인 · 회원가입"""
import streamlit as st

import api_client as api
import state
from components import ui


def render() -> None:
    left, right = st.columns([1.1, 1], gap="large")
    with left:
        ui.html_block(
            """<div class="qn-hero">
  <div class="qn-brand"><i>Q</i>Quiz Note</div>
  <h2>PDF 한 장으로<br>나만의 문제집을 만드세요</h2>
  <ul>
    <li>📄 PDF 업로드 → AI가 핵심 내용 분석</li>
    <li>💬 채팅으로 한 문제씩 풀고 즉시 채점 · 해설</li>
    <li>📝 학습 결과를 계정 또는 Notion에 저장</li>
  </ul>
</div>"""
        )
    with right:
        login_tab, register_tab = st.tabs(["로그인", "회원가입"])
        with login_tab, st.form("login"):
            email = st.text_input("이메일", placeholder="you@example.com", key="login_email")
            password = st.text_input("비밀번호", type="password", key="login_pw")
            if st.form_submit_button("로그인", type="primary", width="stretch"):
                _submit(lambda: api.login(email.strip(), password), email, password)
        with register_tab, st.form("register"):
            name = st.text_input("이름", placeholder="홍길동", max_chars=100, key="reg_name")
            email2 = st.text_input("이메일", placeholder="you@example.com", key="reg_email")
            password2 = st.text_input("비밀번호 (8자 이상)", type="password", key="reg_pw")
            if st.form_submit_button("가입하고 시작하기", type="primary", width="stretch"):
                if len(password2) < 8:
                    st.error("비밀번호는 8자 이상이어야 해요.")
                else:
                    _submit(lambda: api.register(email2.strip(), password2, name.strip()), email2, password2)


def _submit(call, email: str, password: str) -> None:
    if not email.strip() or not password:
        st.error("이메일과 비밀번호를 입력해주세요.")
        return
    try:
        res = call()
    except api.APIError as e:
        st.error(str(e))
        return
    state.login_success(res)
    st.rerun()
