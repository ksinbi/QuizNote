"""STEP 4~5. 채팅형 문제 풀이 · 즉시 채점"""
import streamlit as st

import api_client as api
import state
from components import tutor, ui
from components.tutor import AI_AVATAR, USER_AVATAR


def _load(session_id: str) -> dict:
    s = state.ss()
    if not s.quiz_cache or s.quiz_cache["sid"] != session_id:
        data = api.get_session(session_id)
        s.quiz_cache = {
            "sid": session_id,
            "session": data,
            "results": {int(k): v for k, v in data["results"].items()},
        }
        tutor.sync(session_id, data.get("tutor_log"))
    return s.quiz_cache


def render() -> None:
    s = state.ss()
    flow = state.flow()
    sid = flow["upload"]["session_id"]
    try:
        cache = _load(sid)
    except api.APIError as e:
        if e.status == 404:
            st.warning("학습 세션을 찾을 수 없어요. PDF를 다시 업로드해주세요.")
            if st.button("처음으로", type="primary"):
                state.reset_flow()
                st.rerun()
        else:
            st.error(str(e))
            if st.button("다시 불러오기"):
                st.rerun()
        return

    session, results = cache["session"], cache["results"]
    questions = session["questions"]
    if not questions:
        st.warning("생성된 문제가 없어요. 조건을 다시 설정해주세요.")
        if st.button("설정으로"):
            state.update_flow(step="settings")
            st.rerun()
        return

    settings = session.get("settings") or flow["settings"]
    total = len(questions)
    index = min(flow["current_index"], total - 1)
    current = questions[index]
    current_result = results.get(current["id"])
    use_web = bool(settings.get("use_web"))

    ui.html_block(ui.progress_strip(questions, results, index))

    # ---------- 채팅 영역 (자동 스크롤) ----------
    chat = st.container(height=560, border=True, autoscroll=True)
    with chat:
        with st.chat_message("assistant", avatar=AI_AVATAR):
            summary = (session.get("summary") or {}).get("summary", "")
            st.markdown(
                f"📄 **{session['filename']}** 문서로 **{total}문제**를 준비했어요. (난이도: {settings['difficulty']})"
                + (f"\n\n{summary}" if summary else "")
                + "\n\n한 문제씩 풀어볼까요? 시작합니다! 💪"
            )
        for i, q in enumerate(questions[: index + 1]):
            r = results.get(q["id"])
            with st.chat_message("assistant", avatar=AI_AVATAR):
                ui.html_block(ui.question_card(q, i, total, r, settings))
            # 채점 전 질문(힌트 포함) → 내 답변 · 채점 결과 → 채점 후 질문 순서로 표시
            tutor.render_entries(tutor.entries_for(sid, q["id"], after=False))
            if r:
                with st.chat_message("user", avatar=USER_AVATAR):
                    st.text(ui.format_user_answer(q, r["user_answer"]))
                with st.chat_message("assistant", avatar=AI_AVATAR):
                    ui.html_block(ui.result_card(q, r, settings))
                tutor.render_entries(tutor.entries_for(sid, q["id"], after=True))

    if s.quiz_error:
        st.error(s.quiz_error)
        s.quiz_error = None
    tutor.show_error()

    # ---------- 입력 영역 ----------
    qid = current["id"]
    answered = current_result is not None
    if answered:
        last = index >= total - 1
        if st.button("🎉 결과 보기" if last else "다음 문제 →", type="primary", width="stretch"):
            if last:
                s.report_cache = None
                state.update_flow(step="summary")
            else:
                state.update_flow(current_index=index + 1)
            st.rerun()
    elif current["type"] == "mcq":
        cols = st.columns(2)
        for i, opt in enumerate(current.get("options") or []):
            if cols[i % 2].button(f"{ui.CIRCLED[i]}  {opt}", key=f"opt_{qid}_{i}", width="stretch"):
                _submit(chat, sid, current, str(i + 1))
    else:
        with st.form(key=f"essay_{qid}", clear_on_submit=True, border=False):
            text = st.text_area(
                "내 답안",
                placeholder="핵심 키워드를 포함해 2~5문장으로 작성해주세요",
                max_chars=5000,
                height=110,
            )
            if st.form_submit_button("답안 제출", type="primary", width="stretch") and text.strip():
                _submit(chat, sid, current, text.strip())

    # ---------- AI 튜터: 빠른 질문 + 자유 질문 ----------
    with st.container(horizontal=True):
        if not answered:
            if st.button("💡 힌트 보기", key=f"hint_{qid}"):
                tutor.ask(chat, sid, tutor.HINT_PROMPT, qid, use_web, label="💡 힌트 주세요")
        else:
            why = "🤔 왜 이게 정답이야?" if current_result.get("is_correct") else "🤔 내 답은 왜 틀렸어?"
            if st.button(why, key=f"why_{qid}"):
                tutor.ask(chat, sid, why.removeprefix("🤔 "), qid, use_web, label=why)
            if st.button("📖 이 개념 더 자세히", key=f"more_{qid}"):
                tutor.ask(chat, sid, "이 문제의 핵심 개념을 학습 자료를 근거로 더 자세히 설명해줘", qid, use_web)

    question = st.chat_input("AI 튜터에게 질문하기 (예: 이 개념 다시 설명해줘)", max_chars=3000, key="tutor_quiz")
    if question and question.strip():
        tutor.ask(chat, sid, question.strip(), qid, use_web)


def _submit(chat, sid: str, q: dict, answer: str) -> None:
    s = state.ss()
    with chat:
        with st.chat_message("user", avatar=USER_AVATAR):
            st.text(ui.format_user_answer(q, answer))
        with st.chat_message("assistant", avatar=AI_AVATAR):
            label = "핵심 키워드와 의미를 기준으로 채점하는 중..." if q["type"] == "essay" else "채점하는 중..."
            with st.spinner(label):
                try:
                    result = api.answer(sid, q["id"], answer)
                except api.APIError as e:
                    s.quiz_error = f"채점에 실패했어요: {e}"
                    result = None
    if result:
        s.quiz_cache["results"][q["id"]] = result
    st.rerun()
