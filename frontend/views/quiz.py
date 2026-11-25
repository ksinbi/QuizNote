"""STEP 3. 채팅형 문제 풀이 · 즉시 채점"""
import re

import streamlit as st

import api_client as api
import state
from components import tutor, ui


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


def _md(text: str) -> str:
    """버튼 라벨에서 마크다운으로 해석되는 문자를 그대로 보이게."""
    return re.sub(r"([\\`*_\[\]#<>~|$])", r"\\\1", text)


def _pick(qid: int, i: int) -> None:
    state.ss().quiz_choice[qid] = i


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
    correct = sum(1 for r in results.values() if r["is_correct"])

    ui.html_block(ui.quiz_bar(session["filename"], index, total, len(results), correct))

    # ---------- 채팅 영역 (자동 스크롤) ----------
    chat = st.container(height=680, border=False, autoscroll=True, key="qn_chat")
    with chat:
        with st.chat_message("assistant", avatar=ui.BOT_AVATAR):
            summary = (session.get("summary") or {}).get("summary", "")
            ui.html_block(
                f'<div class="qn-card"><p class="qn-question"><b>{ui.esc(session["filename"])}</b> 문서로 '
                f'<b>{total}문제</b>를 준비했어요. (난이도: {ui.esc(settings["difficulty"])})</p>'
                + (f'<p class="qn-body" style="margin-top:.5rem">{ui.esc(summary)}</p>' if summary else "")
                + '<p class="qn-body" style="margin-top:.4rem">한 문제씩 풀어볼까요? 궁금한 점은 아래 입력창에서 AI 튜터에게 물어보세요.</p></div>'
            )
        for i, q in enumerate(questions[: index + 1]):
            r = results.get(q["id"])
            if i == index and r is None:
                _current_card(chat, sid, q, index)
            else:
                with st.chat_message("assistant", avatar=ui.BOT_AVATAR):
                    ui.html_block(ui.question_card(q, i))
            # 채점 전 질문(힌트 포함) → 내 답변 · 채점 결과 → 채점 후 질문 순서로 표시
            tutor.render_entries(tutor.entries_for(sid, q["id"], after=False))
            if r:
                ui.html_block(ui.my_bubble(ui.format_user_answer(q, r["user_answer"])))
                with st.chat_message("assistant", avatar=ui.BOT_AVATAR):
                    ui.html_block(ui.result_card(q, r, settings))
                tutor.render_entries(tutor.entries_for(sid, q["id"], after=True))

    if s.quiz_error:
        st.error(s.quiz_error)
        s.quiz_error = None
    tutor.show_error()

    # ---------- 다음 문제 · AI 튜터 빠른 질문 ----------
    qid = current["id"]
    with st.container(horizontal=True, key="qn_tutor_actions"):
        if current_result is None:
            if st.button("힌트 보기", icon=":material/lightbulb:", key=f"hint_{qid}"):
                tutor.ask(chat, sid, tutor.HINT_PROMPT, qid, use_web, label="힌트 주세요")
        else:
            why = "왜 이게 정답이야?" if current_result.get("is_correct") else "내 답은 왜 틀렸어?"
            if st.button(why, icon=":material/help:", key=f"why_{qid}"):
                tutor.ask(chat, sid, why, qid, use_web, label=why)
            if st.button("이 개념 더 자세히", icon=":material/menu_book:", key=f"more_{qid}"):
                tutor.ask(chat, sid, "이 문제의 핵심 개념을 학습 자료를 근거로 더 자세히 설명해줘", qid, use_web)
            last = index >= total - 1
            if st.button(
                "결과 보기" if last else "다음 문제",
                icon=":material/emoji_events:" if last else ":material/arrow_forward:",
                icon_position="left" if last else "right",
                type="primary",
                key=f"next_{qid}",
            ):
                if last:
                    s.report_cache = None
                    state.update_flow(step="summary")
                else:
                    state.update_flow(current_index=index + 1)
                st.rerun()

    # 컨테이너 안에 두면 화면 하단 고정이 아니라 대화 바로 아래에 함께 놓임
    with st.container(key="qn_ask"):
        question = st.chat_input("AI 튜터에게 질문하기 (예: 이 개념 다시 설명해줘)", max_chars=3000, key="tutor_quiz")
    if question and question.strip():
        tutor.ask(chat, sid, question.strip(), qid, use_web)


def _current_card(chat, sid: str, q: dict, index: int) -> None:
    """현재 문제: 객관식은 보기 선택 → 정답 제출, 서술형은 답안 입력 → 제출."""
    s = state.ss()
    qid = q["id"]
    with st.chat_message("assistant", avatar=ui.BOT_AVATAR), st.container(key=f"qn_cur_{qid}"):
        ui.html_block(ui.question_head(q, index, True))
        if q["type"] == "mcq":
            picked = s.quiz_choice.get(qid)
            with st.container(key=f"qn_opts_{qid}"):
                for i, opt in enumerate(q.get("options") or []):
                    st.button(
                        f"**{i + 1}** {_md(opt)}",
                        key=f"opt_{qid}_{i}",
                        type="primary" if picked == i else "secondary",
                        width="stretch",
                        on_click=_pick,
                        args=(qid, i),
                    )
            with st.container(horizontal=True, key=f"qn_submit_{qid}", vertical_alignment="center"):
                ui.html_block(
                    f'<span class="qn-picked">선택된 보기: <b>{picked + 1}번</b></span>'
                    if picked is not None
                    else '<span class="qn-picked">보기를 선택한 뒤 제출해주세요</span>'
                )
                if st.button(
                    "정답 제출하기", icon=":material/send:", icon_position="right", type="primary",
                    disabled=picked is None, key=f"submit_{qid}",
                ):
                    _submit(chat, sid, q, str(picked + 1))
        else:
            with st.form(key=f"essay_{qid}", clear_on_submit=True, border=False):
                text = st.text_area(
                    "내 답안",
                    placeholder="핵심 키워드를 포함해 2~5문장으로 작성해주세요. 키워드와 의미를 기준으로 채점해요.",
                    max_chars=5000,
                    height=120,
                )
                if st.form_submit_button("답안 제출하기", icon=":material/send:", type="primary") and text.strip():
                    _submit(chat, sid, q, text.strip())


def _submit(chat, sid: str, q: dict, answer: str) -> None:
    s = state.ss()
    with chat:
        ui.html_block(ui.my_bubble(ui.format_user_answer(q, answer)))
        with st.chat_message("assistant", avatar=ui.BOT_AVATAR):
            label = "핵심 키워드와 의미를 기준으로 채점하는 중..." if q["type"] == "essay" else "채점하는 중..."
            with st.spinner(label):
                try:
                    result = api.answer(sid, q["id"], answer)
                except api.APIError as e:
                    s.quiz_error = f"채점에 실패했어요: {e}"
                    result = None
    if result:
        s.quiz_cache["results"][q["id"]] = result
        s.quiz_choice.pop(q["id"], None)
    st.rerun()
