"""STEP 6. 학습 완료 화면 + STEP 7. 저장 방식 선택"""
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

    emoji = "🏆" if rep["accuracy"] >= 80 else "👏" if rep["accuracy"] >= 50 else "💪"
    ui.html_block(
        f'<div class="qn-center"><div class="qn-big">{emoji}</div><h1 class="qn-title">학습을 완료했어요!</h1>'
        f'<p class="qn-subtitle">📄 {ui.esc(rep["filename"])}</p></div>'
    )

    ui.stat_cards(rep["total"], rep["correct"], rep["wrong"], rep["accuracy"])

    unanswered = rep["total"] - rep["answered"]
    if unanswered:
        st.warning(f"아직 풀지 않은 문제가 {unanswered}개 있어요. 미응답 문제는 오답으로 계산돼요.")

    if rep["weak_concepts"]:
        with st.container(border=True):
            st.markdown("**🎯 복습이 필요한 개념**")
            ui.html_block('<div class="qn-chiplist">' + "".join(f"<span>{ui.esc(c)}</span>" for c in rep["weak_concepts"]) + "</div>")

    st.markdown("#### 문제별 답변 결과")
    ui.question_review(rep["questions"], display)

    _review_chat(sid, bool((rep.get("settings") or {}).get("use_web")))

    # ---------- 저장 방식 선택 ----------
    st.write("")
    with st.container(border=True):
        st.markdown("### 학습 결과를 저장할까요?")
        st.caption("저장 방식을 선택해주세요.")
        c1, c2 = st.columns(2)
        with c1:
            if st.button("📝 Notion으로 저장", width="stretch", help="내 Notion 페이지에 학습 결과를 정리해요"):
                notion_dialog.open_dialog({"session_id": sid}, default_title(rep["filename"]), context="flow")
                st.rerun()
            st.caption("내 Notion 페이지에 정리하고, 웹 계정 학습 기록에도 함께 저장해요")
        with c2:
            if st.button("☁️ 웹 계정에 저장", type="primary", width="stretch"):
                with st.spinner("저장하는 중..."):
                    try:
                        api.save_record(sid)
                    except api.APIError as e:
                        st.error(str(e))
                    else:
                        state.update_flow(saved={"via": "web"}, step="done")
                        st.rerun()
            st.caption("'학습 기록'에서 언제든 다시 볼 수 있어요")

    if st.button("← 풀이 화면으로 돌아가기"):
        state.update_flow(step="quiz")
        st.rerun()


REVIEW_SUGGESTIONS = {
    "🎯 약한 개념 정리해줘": "내가 틀린 문제를 바탕으로 복습이 필요한 개념을 학습 자료 근거와 함께 정리해줘",
    "❌ 틀린 문제 다시 설명해줘": "내가 틀린 문제들을 하나씩 왜 틀렸는지와 정답 근거를 짧게 설명해줘",
    "✏️ 비슷한 문제 하나 더": "내가 약한 개념으로 연습 문제를 하나 더 내줘. 정답은 내가 답한 뒤에 알려줘",
}


def _review_chat(sid: str, use_web: bool) -> None:
    """학습 완료 후 복습용 AI 튜터 대화 (풀이 중 대화 맥락을 이어서 사용)."""
    st.write("")
    st.markdown("#### 🤖 AI 튜터와 복습하기")
    st.caption("틀린 문제나 헷갈린 개념을 물어보세요. 업로드한 자료를 근거로 답해드려요.")
    entries = tutor.entries_for(sid, None)
    chat = st.container(height=420 if entries else "content", border=True, autoscroll=True)
    with chat:
        if not entries:
            with st.chat_message("assistant", avatar=tutor.AI_AVATAR):
                st.markdown("수고했어요! 결과를 보고 궁금한 점이 있으면 무엇이든 물어보세요.")
        tutor.render_entries(entries)
    tutor.show_error()

    with st.container(horizontal=True):
        for label, message in REVIEW_SUGGESTIONS.items():
            if st.button(label, key=f"review_{label}"):
                tutor.ask(chat, sid, message, None, use_web, label=label)

    question = st.chat_input("AI 튜터에게 복습 질문하기", max_chars=3000, key="tutor_summary")
    if question and question.strip():
        tutor.ask(chat, sid, question.strip(), None, use_web)
