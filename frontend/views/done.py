"""STEP 8. 새로운 문제 생성 여부 확인"""
import streamlit as st

import state
from components import ui


def render() -> None:
    flow = state.flow()
    saved = flow.get("saved")
    _, mid, _ = st.columns([1, 2, 1])
    with mid, st.container(border=True):
        if saved:
            if saved["via"] == "notion":
                link = f'<br><a href="{ui.esc(saved.get("url", ""))}" target="_blank">Notion 페이지 열기 ↗</a>' if saved.get("url") else ""
                where = "Notion과 웹 계정 학습 기록에" if saved.get("record") else "Notion에"
                ui.html_block(f'<div class="qn-saved">✅ {where} 학습 결과를 저장했어요{link}</div>')
            else:
                ui.html_block('<div class="qn-saved">✅ 웹 계정에 학습 결과를 저장했어요</div>')

        if flow.get("ended"):
            ui.html_block(
                '<div class="qn-center"><div class="qn-big">🌙</div><h2>오늘의 학습을 마쳤어요</h2>'
                '<p class="qn-subtitle">수고하셨어요! 저장한 기록은 언제든 다시 볼 수 있어요.</p></div>'
            )
            c1, c2 = st.columns(2)
            if c1.button("학습 기록 보기", width="stretch"):
                state.ss().view = "history"
                st.rerun()
            if c2.button("새 학습 시작", type="primary", width="stretch"):
                state.reset_flow()
                st.rerun()
        else:
            ui.html_block(
                '<div class="qn-center"><div class="qn-big">📚</div><h2>새로운 문제를 생성할까요?</h2>'
                '<p class="qn-subtitle">다른 PDF로 새 학습 세션을 시작할 수 있어요.</p></div>'
            )
            c1, c2 = st.columns(2)
            if c1.button("종료", width="stretch"):
                state.update_flow(ended=True)
                st.rerun()
            if c2.button("새로운 문제 생성", type="primary", width="stretch"):
                state.reset_flow()
                st.rerun()
