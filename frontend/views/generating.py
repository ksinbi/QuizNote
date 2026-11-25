"""STEP 2. 문제 생성 — 단계별 진행 상황 (1.5초마다 갱신)"""
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
    st.space("medium")
    _, mid, _ = st.columns([1, 2.2, 1])
    with mid:
        _panel(flow["upload"]["session_id"], flow["upload"]["filename"], flow["settings"])


def _stage_list(stages: list[dict], current: int, detail: str, error: bool) -> str:
    rows = []
    for i, s in enumerate(stages):
        if error and i == current:
            cls, ic, pill = "error", ui.icon("alert", 18), "오류"
        elif i < current:
            cls, ic, pill = "done", ui.icon("check", 18), "완료"
        elif i == current:
            cls, ic, pill = "active", ui.icon("loader", 18), "진행 중"
        else:
            cls, ic, pill = "wait", ui.icon("clock", 18), "대기"
        label = f"{i + 1}. {ui.esc(s['label'])}" + ("..." if cls == "active" else "")
        sub = f"<small>{ui.esc(detail)}</small>" if cls == "active" and detail else ""
        rows.append(
            f'<li class="{cls}"><span class="qn-st-ic">{ic}</span><span>{label}{sub}</span><span class="qn-st-pill">{pill}</span></li>'
        )
    return f'<ol class="qn-stages">{"".join(rows)}</ol>'


def _cancel(session_id: str) -> None:
    """생성을 취소하고 설정 화면으로. 서버는 취소된 작업의 결과를 저장하지 않습니다."""
    s = state.ss()
    try:
        api.cancel_generation(session_id)
    except api.APIError:
        pass  # 이미 끝났거나 서버가 재시작된 경우 — 설정 화면으로는 그대로 이동
    s.gen_error = None
    s.gen_started = None
    state.update_flow(step="settings")


@st.fragment(run_every=1.5)
def _panel(session_id: str, filename: str, settings: dict) -> None:
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
            elif progress["status"] == "cancelled":
                s.gen_error = "문제 생성이 취소되었어요."
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
    pct = min(99, round((current + 0.5) / len(stages) * 100))
    meta = f"{settings['num_questions']}문항 · {settings['difficulty']} 난이도"
    if settings.get("num_essay"):
        meta += f" · 서술형 {settings['num_essay']}문항 포함"

    with st.container(key="qn_card_gen"):
        if s.gen_error:
            top = (
                f'<span class="qn-orb" style="background:#ef4444;box-shadow:0 0 0 8px #fee2e2">{ui.icon("alert", 28)}</span>'
                "<h2>문제를 생성하지 못했어요</h2>"
            )
        else:
            top = f'<span class="qn-orb">{ui.icon("sparkles", 28)}</span><h2><b>PDF</b>에서 맞춤 문제를 생성하고 있습니다...</h2>'
        ui.html_block(f'<div class="qn-gen-top">{top}<p>{ui.esc(filename)} ({meta})</p></div>')
        if not s.gen_error:
            ui.html_block(
                f'<div class="qn-gen-prog"><div><span>문제 생성 진행률</span><b>{pct}%</b></div>'
                f'<div class="qn-bar"><i style="width:{pct}%"></i></div></div>'
            )
        else:
            st.space("small")
        ui.html_block(_stage_list(stages, current, (progress or {}).get("detail", ""), bool(s.gen_error)))

        if s.gen_error:
            st.error(s.gen_error)
            with st.container(horizontal=True, key="qn_gen_actions"):
                if st.button("설정으로 돌아가기"):
                    _cancel(session_id)
                    st.rerun()
                if st.button("다시 시도", type="primary"):
                    try:
                        api.generate(session_id, state.flow()["settings"])
                    except api.APIError as e:
                        s.gen_error = str(e)
                    else:
                        s.gen_error = None
                        s.gen_started = time.time()
                    st.rerun(scope="fragment")
        else:
            elapsed = int(time.time() - (s.gen_started or time.time()))
            ui.html_block(f'<p class="qn-elapsed">문서 분량에 따라 30초~1분 정도 걸려요 · {elapsed}초 경과</p>')
            with st.container(horizontal=True, key="qn_gen_actions"):
                if st.button("생성 취소", help="생성을 멈추고 설정 화면으로 돌아가요"):
                    _cancel(session_id)
                    st.rerun()
