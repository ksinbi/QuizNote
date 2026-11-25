"""STEP 3. 문제 생성 — 단계별 진행 상황 (1.5초마다 갱신)"""
import time

import streamlit as st

import api_client as api
import state
from components import ui

FALLBACK_STAGES = [
    {"key": "extract", "label": "문서 내용 추출"},
    {"key": "analyze", "label": "핵심 내용 분석"},
    {"key": "generate", "label": "조건에 맞춰 문제 생성"},
    {"key": "answers", "label": "정답 및 해설 검증"},
    {"key": "sources", "label": "원문 출처 연결"},
]


def render() -> None:
    flow = state.flow()
    if state.ss().gen_started is None:
        state.ss().gen_started = time.time()
    _, mid, _ = st.columns([1, 3, 1])
    with mid:
        _panel(flow["upload"]["session_id"], flow["settings"]["num_questions"])


def _stage_list(stages: list[dict], current: int, detail: str, error: bool) -> str:
    rows = []
    for i, s in enumerate(stages):
        if error and i == current:
            cls, mark = "error", "!"
        elif i < current:
            cls, mark = "done", "✓"
        elif i == current:
            cls, mark = "active", str(i + 1)
        else:
            cls, mark = "", str(i + 1)
        sub = f"<small>{ui.esc(detail)}</small>" if cls == "active" and detail else ""
        rows.append(f'<li class="{cls}"><span class="n">{mark}</span><div>{ui.esc(s["label"])}{sub}</div></li>')
    return f'<ol class="qn-stages">{"".join(rows)}</ol>'


@st.fragment(run_every=1.5)
def _panel(session_id: str, num_questions: int) -> None:
    s = state.ss()
    progress = None
    if not s.gen_error:
        try:
            progress = api.progress(session_id)
        except api.APIError as e:
            s.gen_error = str(e)
        else:
            if progress["status"] == "done":
                state.update_flow(step="quiz", current_index=0)
                st.rerun()
            elif progress["status"] == "error":
                s.gen_error = progress.get("error") or "문제 생성 중 오류가 발생했어요."
            elif progress["status"] == "idle":
                # 서버 재시작 등으로 작업 정보가 사라진 경우
                try:
                    if api.get_session(session_id)["questions"]:
                        state.update_flow(step="quiz", current_index=0)
                        st.rerun()
                except api.APIError:
                    pass
                s.gen_error = "문제 생성 작업이 중단되었어요. 다시 시도해주세요."

    stages = (progress or {}).get("stages") or FALLBACK_STAGES
    current = max(0, (progress or {}).get("stage_index", 0))
    if s.gen_error:
        current = s.get("gen_last_stage", current)
    else:
        s.gen_last_stage = current

    with st.container(border=True):
        if s.gen_error:
            ui.html_block('<div class="qn-center"><div class="qn-big">⚠️</div><h3>문제를 생성하지 못했어요</h3></div>')
        else:
            elapsed = int(time.time() - (s.gen_started or time.time()))
            ui.html_block(
                f'<div class="qn-center"><div class="qn-big">🪄</div><h3>{num_questions}개의 문제를 만들고 있어요</h3>'
                f'<p class="qn-subtitle">문서 분량에 따라 30초~1분 정도 걸려요 · {elapsed}초 경과</p></div>'
            )
            st.progress(min(0.99, (current + 0.5) / len(stages)))
        ui.html_block(_stage_list(stages, current, (progress or {}).get("detail", ""), bool(s.gen_error)))

        if s.gen_error:
            st.error(s.gen_error)
            c1, c2 = st.columns(2)
            if c1.button("설정으로 돌아가기", width="stretch"):
                s.gen_error = None
                state.update_flow(step="settings")
                st.rerun()
            if c2.button("다시 시도", type="primary", width="stretch"):
                try:
                    api.generate(session_id, state.flow()["settings"])
                except api.APIError as e:
                    s.gen_error = str(e)
                else:
                    s.gen_error = None
                    s.gen_started = time.time()
                st.rerun(scope="fragment")
