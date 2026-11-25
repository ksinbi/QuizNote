"""STEP 4. 학습 완료 화면 + 저장 방식 선택"""
from datetime import datetime

import streamlit as st

import api_client as api
import state
from components import tutor, ui
from views import notion_dialog


def default_title(filename: str) -> str:
    return f"[학습 결과] {filename.removesuffix('.pdf').removesuffix('.PDF')} · {datetime.now():%Y-%m-%d}"


def render() -> None:
    s = state.ss()
    sid = state.flow()["upload"]["session_id"]
    if not s.report_cache or s.report_cache.get("sid") != sid:
        try:
            s.report_cache = {"sid": sid, "data": api.report(sid)}
            tutor.sync(sid, s.report_cache["data"].get("tutor_log"))
        except api.APIError as e:
            st.error(str(e))
            return
    rep = s.report_cache["data"]
    display = rep.get("settings") or {"show_answer": True, "show_explanation": True, "show_source": True}

    acc = rep["accuracy"]
    cheer = "훌륭해요! 핵심 개념을 잘 이해하고 있어요." if acc >= 80 else "잘했어요! 틀린 개념만 한 번 더 복습해 볼까요?" if acc >= 50 else "괜찮아요. 해설과 AI 튜터로 차근차근 복습해 봐요."

    _, mid, _ = st.columns([1, 5, 1])
    with mid:
        ui.page_header(4, "학습 결과 확인 및 저장", "학습 <b>결과</b>")
        with st.container(key="qn_card_done"):
            ui.html_block(
                f'<div class="qn-done-head"><span class="qn-avatar">{ui.icon("bot", 24)}</span><div>'
                f'<small>Quiz Note AI <i>학습 완료</i></small>'
                f'<h2>모든 문제를 다 풀었습니다! (총 {rep["total"]}문제 중 {rep["correct"]}문제 정답)</h2>'
                f'<p>{ui.esc(rep["filename"])} · {cheer}</p></div></div>'
            )
            ui.stat_cards(rep["total"], rep["correct"], rep["wrong"], acc)

            unanswered = rep["total"] - rep["answered"]
            if unanswered:
                st.warning(f"아직 풀지 않은 문제가 {unanswered}개 있어요. 미응답 문제는 오답으로 계산돼요.")
            if rep["weak_concepts"]:
                ui.html_block(
                    '<div class="qn-weak"><small>복습이 필요한 개념</small><div class="qn-chiplist">'
                    + "".join(f"<span>{ui.esc(c)}</span>" for c in rep["weak_concepts"])
                    + "</div></div>"
                )

            # ---------- 저장 방식 선택 ----------
            with st.container(horizontal=True, key="qn_save_actions"):
                if st.button("Notion으로 저장", icon=":material/description:", type="primary", width="stretch",
                             help="내 Notion 페이지에 정리하고, 웹 계정 학습 기록에도 함께 저장해요"):
                    notion_dialog.open_dialog({"session_id": sid}, default_title(rep["filename"]), context="flow")
                    st.rerun()
                if st.button("웹 계정에만 저장", icon=":material/cloud_upload:", width="stretch",
                             help="'내 문제집'에서 언제든 다시 볼 수 있어요"):
                    with st.spinner("저장하는 중..."):
                        try:
                            api.save_record(sid)
                        except api.APIError as e:
                            st.error(str(e))
                        else:
                            state.update_flow(saved={"via": "web"}, step="done")
                            st.rerun()
            st.caption("Notion으로 저장하면 웹 계정의 '내 문제집'에도 함께 저장돼요.")

        ui.html_block('<div class="qn-section">문제별 답변 결과</div>')
        ui.question_review(rep["questions"], display)

        _review_chat(sid, bool((rep.get("settings") or {}).get("use_web")))

        if st.button("풀이 화면으로 돌아가기", icon=":material/arrow_back:", type="tertiary"):
            state.update_flow(step="quiz")
            st.rerun()


REVIEW_SUGGESTIONS = {
    "약한 개념 정리해줘": "내가 틀린 문제를 바탕으로 복습이 필요한 개념을 학습 자료 근거와 함께 정리해줘",
    "틀린 문제 다시 설명해줘": "내가 틀린 문제들을 하나씩 왜 틀렸는지와 정답 근거를 짧게 설명해줘",
    "비슷한 문제 하나 더": "내가 약한 개념으로 연습 문제를 하나 더 내줘. 정답은 내가 답한 뒤에 알려줘",
}
_SUGGESTION_ICONS = [":material/target:", ":material/replay:", ":material/edit_note:"]


def _review_chat(sid: str, use_web: bool) -> None:
    """학습 완료 후 복습용 AI 튜터 대화 (풀이 중 대화 맥락을 이어서 사용)."""
    ui.html_block('<div class="qn-section">AI 튜터와 복습하기</div>')
    st.caption("틀린 문제나 헷갈린 개념을 물어보세요. 업로드한 자료를 근거로 답해드려요.")
    entries = tutor.entries_for(sid, None)
    chat = st.container(height=480 if len(entries) > 2 else "content", border=False, autoscroll=True)
    with chat:
        if not entries:
            with st.chat_message("assistant", avatar=ui.BOT_AVATAR):
                ui.html_block('<div class="qn-card"><p class="qn-body" style="margin:0">수고했어요! 결과를 보고 궁금한 점이 있으면 무엇이든 물어보세요.</p></div>')
        tutor.render_entries(entries)
    tutor.show_error()

    with st.container(horizontal=True):
        for (label, message), ic in zip(REVIEW_SUGGESTIONS.items(), _SUGGESTION_ICONS):
            if st.button(label, icon=ic, key=f"review_{label}"):
                tutor.ask(chat, sid, message, None, use_web, label=label)

    with st.container(key="qn_ask_review"):
        question = st.chat_input("AI 튜터에게 복습 질문하기", max_chars=3000, key="tutor_summary")
    if question and question.strip():
        tutor.ask(chat, sid, question.strip(), None, use_web)
