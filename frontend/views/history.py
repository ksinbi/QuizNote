"""웹 계정에 저장된 학습 기록 (조회 · 삭제 · Notion 내보내기)"""
from datetime import datetime

import streamlit as st

import api_client as api
import state
from components import ui
from views import notion_dialog
from views.summary import default_title


def _fmt_date(iso: str | None) -> str:
    if not iso:
        return "-"
    try:
        return datetime.fromisoformat(iso).astimezone().strftime("%Y.%m.%d %H:%M")
    except ValueError:
        return iso


def _acc_color(acc: float) -> str:
    return "#059669" if acc >= 80 else "#d97706" if acc >= 50 else "#e11d48"


def render() -> None:
    s = state.ss()
    head, btn = st.columns([4, 1], vertical_alignment="bottom")
    with head:
        ui.page_header(None, "웹 계정에 저장한 학습 결과", "내 <b>문제집</b>")
    if btn.button("새 문제 만들기", icon=":material/add:", type="primary", width="stretch"):
        s.view = "study"
        s.history_selected = None
        st.rerun()

    if s.history_selected:
        _detail(s.history_selected)
    else:
        _list()


def _list() -> None:
    try:
        records = api.list_records()
    except api.APIError as e:
        st.error(str(e))
        return
    if not records:
        with st.container(key="qn_card_empty"):
            ui.html_block(
                f'<div class="qn-center"><span class="qn-big">{ui.icon("folder", 28)}</span><h2>저장된 학습 기록이 없어요</h2>'
                "<p class=\"qn-subtitle\">문제를 다 푼 뒤 Notion 또는 웹 계정에 저장하면 여기에 표시돼요.</p></div>"
            )
        return

    cols = st.columns(2)
    for i, r in enumerate(records):
        with cols[i % 2], st.container(key=f"qn_card_rec_{r['id']}"):
            diff = (r.get("settings") or {}).get("difficulty", "")
            ui.html_block(
                f"""<div class="qn-rec"><div class="acc" style="color:{_acc_color(r['accuracy'])}">{round(r['accuracy'])}%</div>
<div style="min-width:0"><b>{ui.esc(r['filename'])}</b><small>{_fmt_date(r['created_at'])}</small>
<div class="tags"><span class="qn-tag">{r['total']}문항</span><span class="qn-tag ok">정답 {r['correct']}</span><span class="qn-tag ng">오답 {r['wrong']}</span>{f'<span class="qn-tag pri">{ui.esc(diff)}</span>' if diff else ''}</div></div></div>"""
            )
            if st.button("자세히 보기", key=f"rec_{r['id']}", width="stretch"):
                state.ss().history_selected = r["id"]
                state.ss().record_cache = None
                st.rerun()


def _detail(record_id: int) -> None:
    s = state.ss()
    if not s.record_cache or s.record_cache["id"] != record_id:
        try:
            s.record_cache = api.get_record(record_id)
        except api.APIError as e:
            st.error(str(e))
            if st.button("← 목록으로"):
                s.history_selected = None
                st.rerun()
            return
    rec = s.record_cache

    if st.button("목록으로", icon=":material/arrow_back:", type="tertiary"):
        s.history_selected = None
        st.rerun()

    ui.html_block(f'<div class="qn-section" style="margin-top:.4rem">{ui.esc(rec["filename"])}</div>')
    cfg = rec.get("settings") or {}
    meta = f":material/schedule: {_fmt_date(rec['created_at'])}"
    if cfg:
        meta += f"  ·  총 {cfg.get('num_questions')}문항 (서술형 {cfg.get('num_essay')}) · 난이도 {cfg.get('difficulty')}"
    st.caption(meta)
    ui.stat_cards(rec["total"], rec["correct"], rec["wrong"], rec["accuracy"])

    ui.html_block('<div class="qn-section">문제 · 정답 · 해설</div>')
    ui.question_review(rec["questions"])

    st.write("")
    c1, _, c2 = st.columns([1, 1, 1])
    with c1.popover("기록 삭제", icon=":material/delete:", width="stretch"):
        st.caption("삭제 후에는 되돌릴 수 없어요.")
        if st.button("삭제", type="primary"):
            try:
                api.delete_record(record_id)
            except api.APIError as e:
                st.error(str(e))
            else:
                s.history_selected = None
                s.record_cache = None
                st.rerun()
    if c2.button("Notion으로 내보내기", icon=":material/description:", type="primary", width="stretch"):
        notion_dialog.open_dialog({"record_id": record_id}, default_title(rec["filename"]), context="history")
        st.rerun()
