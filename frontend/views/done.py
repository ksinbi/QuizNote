"""STEP 5. 저장 완료 → 새로운 문제 생성 여부 확인"""
import streamlit as st

import state
from components import ui


def _new_study() -> None:
    state.reset_flow()


def render() -> None:
    flow = state.flow()
    saved = flow.get("saved")
    st.space("medium")
    _, mid, _ = st.columns([1, 1.6, 1])
    with mid, st.container(key="qn_card_end"):
        if saved:
            if saved["via"] == "notion":
                where = "Notion과 웹 계정 학습 기록에" if saved.get("record") else "Notion에"
                link = f' <a href="{ui.esc(saved.get("url", ""))}" target="_blank">Notion 페이지 열기 ↗</a>' if saved.get("url") else ""
                ui.html_block(f'<div class="qn-saved">{ui.icon("check-circle", 18)}{where} 학습 결과를 저장했어요{link}</div>')
            else:
                ui.html_block(f'<div class="qn-saved">{ui.icon("check-circle", 18)}웹 계정에 학습 결과를 저장했어요</div>')

        if flow.get("ended"):
            ui.html_block(
                f'<div class="qn-center"><span class="qn-big">{ui.icon("trophy", 28)}</span><h2>오늘의 학습을 마쳤어요</h2>'
                '<p class="qn-subtitle">수고하셨어요! 저장한 기록은 \'내 문제집\'에서 언제든 다시 볼 수 있어요.</p></div>'
            )
            with st.container(horizontal=True, key="qn_end_actions"):
                if st.button("내 문제집 보기", icon=":material/folder_open:", width="stretch"):
                    state.ss().view = "history"
                    st.rerun()
                st.button("새 학습 시작", icon=":material/add:", type="primary", width="stretch", on_click=_new_study)
        else:
            ui.html_block(
                f'<div class="qn-center"><span class="qn-big">{ui.icon("sparkles", 28)}</span><h2>새로운 문제를 생성할까요?</h2>'
                '<p class="qn-subtitle">다른 PDF로 새 학습 세션을 시작할 수 있어요.</p></div>'
            )
            with st.container(horizontal=True, key="qn_end_actions"):
                if st.button("종료", width="stretch"):
                    state.update_flow(ended=True)
                    st.rerun()
                st.button("새로운 문제 생성", icon=":material/auto_awesome:", type="primary", width="stretch", on_click=_new_study)
