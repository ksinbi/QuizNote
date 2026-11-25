"""Notion 연동 관리: 연결된 워크스페이스 확인 · 새 계정 연결 · 연결 해제"""
import streamlit as st

import api_client as api
import state
from components import ui


def render() -> None:
    s = state.ss()
    ui.page_header(None, "학습 결과를 내 Notion 페이지로 정리", "<b>Notion</b> 연동")
    try:
        status = api.notion_status()
    except api.APIError as e:
        st.error(str(e))
        return

    left, right = st.columns([1.3, 1], gap="medium")
    with left, st.container(key="qn_card_notion", height="stretch"):
        ui.card_title("book", "연결된 워크스페이스")
        if not status["configured"]:
            st.warning("지금은 Notion 연동을 사용할 수 없어요. 학습 결과는 '내 문제집'에 저장할 수 있어요.")
            return
        conns = status["connections"]
        if not conns:
            st.caption("아직 연결된 Notion 계정이 없어요. 오른쪽에서 연결해주세요.")
        for c in conns:
            with st.container(horizontal=True, vertical_alignment="center", key=f"qn_conn_page_{c['id']}"):
                ui.html_block(
                    f'<div class="qn-conn">{ui.icon("check-circle", 18)}<div><b>{ui.esc(c["workspace_name"])}</b>'
                    f'<small>{ui.esc(c.get("owner_name") or "")}</small></div></div>'
                )
                with st.popover("연결 해제", type="tertiary"):
                    st.caption(f"'{c['workspace_name']}' 연결을 해제할까요? 이미 Notion에 만든 페이지는 그대로 남아요.")
                    if st.button("해제", type="primary", key=f"page_disconnect_{c['id']}"):
                        try:
                            api.notion_disconnect(c["id"])
                        except api.APIError as e:
                            st.error(str(e))
                        else:
                            st.rerun()

    with right, st.container(key="qn_card_notion_connect", height="stretch"):
        ui.card_title("sparkles", "다른 Notion 계정 연결" if status["connections"] else "Notion 계정 연결")
        st.caption(
            "1. 아래 버튼으로 Notion 로그인 창을 열어요\n\n"
            "2. 권한을 승인하고, 학습 결과를 저장할 페이지를 선택해요\n\n"
            "3. 이 화면으로 돌아와 '연결 확인'을 눌러요"
        )
        url = s.get("notion_page_auth")
        if not url:
            if st.button("Notion 연결", icon=":material/link:", type="primary", width="stretch"):
                try:
                    s.notion_page_auth = api.notion_start()
                except api.APIError as e:
                    st.error(str(e))
                else:
                    st.rerun()
        else:
            st.link_button("Notion 로그인 창 열기", url, icon=":material/open_in_new:", type="primary", width="stretch")
            if st.button("연결 확인", icon=":material/check:", width="stretch"):
                s.notion_page_auth = None
                st.rerun()
        st.caption("학습 완료 화면에서 'Notion으로 저장'을 누르면 연결된 계정으로 바로 내보낼 수 있어요.")
