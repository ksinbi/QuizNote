"""AI 튜터 채팅: 힌트 · 문제 풀이 중 질문 · 채점 후 질문 · 복습 질문을 하나의 대화로 관리.

대화 기록은 백엔드 DB(세션의 tutor_log)에 저장되고 화면에서는 session_state에 캐시합니다.
(새로고침해도 유지되며 Notion 내보내기 · 웹 계정 저장에 포함됩니다) 각 메시지에
- qid   : 어느 문제를 보며 한 질문인지 (None이면 학습 완료 화면에서 한 질문)
- after : 그 문제를 채점한 뒤에 한 질문인지
를 함께 기록해 채팅 흐름 안에 시간 순서대로 끼워 넣습니다.
백엔드 튜터도 같은 기록의 최근 대화를 맥락으로 사용합니다.
"""
import streamlit as st

import api_client as api
import state

AI_AVATAR = "🤖"
USER_AVATAR = "🙂"

_TOOL_LABELS = {
    "search_lecture_notes": "📄 학습 자료 검색",
    "web_search": "🌐 웹 검색",
    "get_quiz_progress": "📊 풀이 기록 확인",
}

HINT_PROMPT = "이 문제를 풀 수 있도록 정답은 말하지 말고 힌트만 주세요."


def log(sid: str) -> list[dict]:
    return state.ss().tutor.setdefault(sid, [])


def sync(sid: str, entries: list[dict] | None) -> None:
    """서버에서 받은 대화 기록으로 화면 캐시를 교체."""
    state.ss().tutor[sid] = list(entries or [])


def entries_for(sid: str, qid: int | None, after: bool | None = None) -> list[dict]:
    return [e for e in log(sid) if e["qid"] == qid and (after is None or e["after"] == after)]


def render_entries(entries: list[dict]) -> None:
    for e in entries:
        with st.chat_message("user", avatar=USER_AVATAR):
            st.markdown(e["label"])
        with st.chat_message("assistant", avatar=AI_AVATAR):
            st.markdown(e["reply"])
            tools = [_TOOL_LABELS[t] for t in dict.fromkeys(e.get("tools") or []) if t in _TOOL_LABELS]
            if tools:
                st.caption(" · ".join(tools))


def ask(
    container,
    sid: str,
    message: str,
    qid: int | None,
    use_web: bool,
    label: str | None = None,
) -> None:
    """질문을 보내고 답변을 대화 기록에 추가한 뒤 화면을 새로고침합니다.

    label: 채팅에 표시할 사용자 말풍선 문구 (힌트 버튼처럼 실제 요청문과 다르게 보여줄 때)
    채점 전/후 구분(after)은 서버가 질문 시점의 채점 여부로 정해 기록에 저장합니다.
    """
    shown = label or message
    with container:
        with st.chat_message("user", avatar=USER_AVATAR):
            st.markdown(shown)
        with st.chat_message("assistant", avatar=AI_AVATAR), st.spinner("튜터가 답변을 준비하는 중..."):
            try:
                res = api.chat(sid, message, qid, use_web, label)
            except api.APIError as e:
                state.ss().tutor_error = f"튜터 응답에 실패했어요: {e}"
                res = None
    if res:
        log(sid).append(res["entry"])
    st.rerun()


def show_error() -> None:
    s = state.ss()
    if s.tutor_error:
        st.error(s.tutor_error)
        s.tutor_error = None
