"""Notion 내보내기 모달 — 연결된 계정이 있으면 한 화면에서 (워크스페이스 · 페이지 · 제목 · 항목) 설정 후 내보내기.

단계: connect(계정 연결 · 변경) → options(내보내기 설정) → result(완료/오류)
"""
import streamlit as st

import api_client as api
import state
from components import ui

ITEMS = [
    ("questions", "문제 및 보기"),
    ("user_answers", "내 답안"),
    ("results", "정답 및 오답 결과"),
    ("answers", "정답"),
    ("explanations", "AI 해설"),
    ("sources", "원문 출처 페이지"),
    ("stats", "최종 학습 통계"),
    ("tutor", "AI 튜터 질문 기록"),
    ("filename", "PDF 파일명"),
]
TITLE_KEY = "notion_title"


def open_dialog(source: dict, default_title: str, context: str) -> None:
    """context: 'flow'(학습 완료 화면) | 'history'(내 문제집 화면)"""
    s = state.ss()
    s.notion_ui = {
        "stage": "connect",
        "source": source,
        "context": context,
        "default_title": default_title,
        "status": None,
        "connection_id": None,
        "known_connections": None,
        "authorize_url": None,
        "pages": {},
        "page_id": None,
        "result_url": None,
        "record_saved": False,
        "error": None,
    }
    s.pop(TITLE_KEY, None)  # 새로 열 때마다 기본 제목부터 시작
    s.notion_open = True


def render_if_open() -> None:
    s = state.ss()
    if s.notion_open and s.notion_ui:
        _dialog()


def _finish() -> None:
    """모달 닫기. 학습 흐름에서 저장에 성공했다면 완료 화면으로 이동."""
    s = state.ss()
    ui_state = s.notion_ui or {}
    s.notion_open = False
    s.notion_ui = None
    if ui_state.get("result_url") and ui_state.get("context") == "flow":
        state.update_flow(
            saved={"via": "notion", "url": ui_state["result_url"], "record": bool(ui_state.get("record_saved"))},
            step="done",
        )


def _refresh_status(u: dict, prefer_new: bool = False) -> None:
    try:
        status = api.notion_status()
    except api.APIError as e:
        u["error"] = str(e)
        return
    ids = [c["id"] for c in status["connections"]]
    new_ids = [i for i in ids if u["known_connections"] is not None and i not in u["known_connections"]]
    u["status"] = status
    u["known_connections"] = ids
    if new_ids:
        u["connection_id"] = new_ids[-1]
        u["authorize_url"] = None
        if prefer_new:
            u["stage"] = "options"
    elif u["connection_id"] not in ids:
        u["connection_id"] = ids[-1] if ids else None


@st.dialog("Notion으로 내보내기", width="medium", on_dismiss=_finish)
def _dialog() -> None:
    u = state.ss().notion_ui
    if u["status"] is None:
        _refresh_status(u)
        if u["status"] and u["status"]["connections"]:
            u["stage"] = "options"  # 이미 연결된 계정이 있으면 바로 내보내기 설정

    if u["error"] and u["stage"] != "result":
        st.error(u["error"])
        u["error"] = None

    {"connect": _connect, "options": _options, "result": _result}[u["stage"]](u)


def _go(u: dict, stage: str) -> None:
    u["stage"] = stage
    st.rerun(scope="fragment")


def _conn_name(c: dict) -> str:
    return c["workspace_name"] + (f" · {c['owner_name']}" if c.get("owner_name") else "")


# ---------- 계정 연결 · 변경 ----------
def _connect(u: dict) -> None:
    status = u["status"]
    if status is None:
        return
    if not status["configured"]:
        st.warning("지금은 Notion 저장을 사용할 수 없어요. '웹 계정에 저장'을 이용해주세요.")
        return

    conns = status["connections"]
    if conns:
        st.markdown("**연결된 워크스페이스**")
        for c in conns:
            with st.container(horizontal=True, vertical_alignment="center", key=f"qn_conn_{c['id']}"):
                ui.html_block(f'<div class="qn-conn">{ui.icon("check-circle", 18)}<div><b>{ui.esc(c["workspace_name"])}</b>'
                              f'<small>{ui.esc(c.get("owner_name") or "")}</small></div></div>')
                with st.popover("연결 해제", type="tertiary"):
                    st.caption(f"'{c['workspace_name']}' 연결을 해제할까요?")
                    if st.button("해제", type="primary", key=f"disconnect_{c['id']}"):
                        try:
                            api.notion_disconnect(c["id"])
                        except api.APIError as e:
                            u["error"] = str(e)
                        _refresh_status(u)
                        st.rerun(scope="fragment")

    with st.container(border=True):
        st.markdown("**" + ("다른 Notion 계정 연결" if conns else "Notion 계정을 연결해주세요") + "**")
        st.caption("새 창에서 Notion에 로그인 → 권한 승인 → 결과를 저장할 페이지를 선택(공유)한 뒤, 이 창으로 돌아와 '연결 확인'을 눌러주세요.")
        if not u["authorize_url"]:
            if st.button("Notion 연결", icon=":material/link:", type="secondary" if conns else "primary"):
                try:
                    u["authorize_url"] = api.notion_start()
                    u["known_connections"] = [c["id"] for c in conns]
                except api.APIError as e:
                    u["error"] = str(e)
                st.rerun(scope="fragment")
        else:
            c1, c2 = st.columns(2)
            c1.link_button("Notion 로그인 창 열기", u["authorize_url"], icon=":material/open_in_new:", type="primary", width="stretch")
            if c2.button("연결 확인", icon=":material/check:", width="stretch"):
                before = list(u["known_connections"] or [])
                _refresh_status(u, prefer_new=True)
                if u["stage"] == "connect" and [c["id"] for c in u["status"]["connections"]] == before:
                    u["error"] = "아직 연결이 완료되지 않았어요. Notion 창에서 '허용'까지 마쳤는지 확인해주세요."
                st.rerun(scope="fragment")

    if conns and st.button("내보내기 설정으로", icon=":material/arrow_forward:", icon_position="right", type="primary",
                           disabled=u["connection_id"] is None):
        _go(u, "options")


# ---------- 내보내기 설정 (한 화면) ----------
def _reset_title(u: dict) -> None:
    st.session_state[TITLE_KEY] = u["default_title"]


def _web_only(u: dict) -> None:
    """Notion에는 저장하지 않고 웹 계정에만 저장 → 완료 화면."""
    try:
        api.save_record(u["source"]["session_id"])
    except api.APIError as e:
        u["error"] = str(e)
        st.rerun(scope="fragment")
    s = state.ss()
    s.notion_open = False
    s.notion_ui = None
    state.update_flow(saved={"via": "web"}, step="done")
    st.rerun()


def _options(u: dict) -> None:
    conns = u["status"]["connections"]
    if not conns or u["connection_id"] is None:
        u["stage"] = "connect"
        _connect(u)
        return
    ids = [c["id"] for c in conns]
    current = next(c for c in conns if c["id"] == u["connection_id"])

    with st.container(horizontal=True, vertical_alignment="center", key="qn_linked"):
        ui.html_block(f'<div class="qn-linked">{ui.icon("check-circle", 18)}<span><b>{ui.esc(current.get("owner_name") or current["workspace_name"])}</b> 계정 연동됨</span></div>')
        if st.button("계정 변경", type="tertiary"):
            _go(u, "connect")

    u["connection_id"] = st.selectbox(
        "워크스페이스 선택", ids, index=ids.index(u["connection_id"]), format_func=lambda i: _conn_name(next(c for c in conns if c["id"] == i))
    )
    cid = u["connection_id"]
    if cid not in u["pages"]:
        with st.spinner("공유된 페이지를 불러오는 중..."):
            try:
                u["pages"][cid] = api.notion_pages(cid)
            except api.APIError as e:
                u["pages"][cid] = []
                st.error(str(e))
    pages = u["pages"][cid]
    if pages:
        pids = [p["id"] for p in pages]
        titles = {p["id"]: f"{p['icon'] or '📄'}  {p['title']}" for p in pages}
        u["page_id"] = st.selectbox(
            "저장할 위치 (상위 페이지)", pids, index=pids.index(u["page_id"]) if u["page_id"] in pids else 0,
            format_func=titles.get, help="이 페이지 아래에 학습 결과 페이지가 새로 만들어져요. 이름을 입력해서 검색할 수 있어요.",
        )
    else:
        u["page_id"] = None
        st.info("이 앱에 공유된 페이지가 없어요. '계정 변경'에서 다시 연결하면서 저장할 페이지를 선택해주세요.")

    # 단계를 오가며 입력칸이 사라졌다 생기면 값이 지워지므로, 마지막으로 입력한 제목으로 다시 채움
    if TITLE_KEY not in st.session_state:
        st.session_state[TITLE_KEY] = u.get("title") or u["default_title"]
    with st.container(horizontal=True, vertical_alignment="bottom"):
        st.text_input(
            "페이지 제목",
            key=TITLE_KEY,
            max_chars=200,
            placeholder=u["default_title"],
            help="Notion에 만들어질 페이지 이름이에요. 비워두면 기본 제목으로 저장돼요.",
        )
        st.button("기본 제목으로", on_click=_reset_title, args=(u,), key="notion_title_reset")
    u["title"] = st.session_state[TITLE_KEY].strip()

    st.markdown("**내보낼 내용 선택**")
    chosen = []
    with st.container(key="qn_items"):
        cols = st.columns(2)
        for i, (key, label) in enumerate(ITEMS):
            if cols[i % 2].checkbox(label, value=key in u.get("items", [k for k, _ in ITEMS]), key=f"notion_item_{key}", width="stretch"):
                chosen.append(key)
    u["items"] = chosen
    if not chosen:
        st.caption(":red[최소 1개 항목을 선택해주세요.]")

    with st.container(horizontal=True, key="qn_dialog_actions"):
        if u["context"] == "flow" and u["source"].get("session_id"):
            if st.button("저장 안 함 (웹에만 저장)"):
                _web_only(u)
        elif st.button("취소"):
            _finish()
            st.rerun()
        if st.button("Notion에 내보내기", icon=":material/send:", type="primary", disabled=not chosen or not u["page_id"]):
            _export(u)


def _export(u: dict) -> None:
    u["error"] = None
    u["result_url"] = None
    u["record_saved"] = False
    with st.spinner("Notion 페이지를 만들고 있어요..."):
        try:
            title = (u.get("title") or "").strip() or u["default_title"]
            res = api.notion_export(u["source"], u["connection_id"], u["page_id"], title, u["items"])
            u["result_url"] = res.get("url") or ""
            u["record_saved"] = bool(res.get("record_saved"))
        except api.APIError as e:
            u["error"] = str(e)
    _go(u, "result")


# ---------- 결과 ----------
def _result(u: dict) -> None:
    if u["error"]:
        st.error(f"저장에 실패했어요\n\n{u['error']}")
        c1, c2 = st.columns(2)
        if c1.button("설정 수정", width="stretch"):
            u["error"] = None
            _go(u, "options")
        if c2.button("다시 시도", type="primary", width="stretch"):
            _export(u)
        return
    st.success(f"Notion에 저장했어요!\n\n**{u['title'] or u['default_title']}**", icon=":material/check_circle:")
    if u.get("record_saved") and u.get("context") == "flow":
        st.caption("웹 계정의 '내 문제집'에도 함께 저장했어요.")
    c1, c2 = st.columns(2)
    if u["result_url"]:
        c1.link_button("Notion에서 열기", u["result_url"], icon=":material/open_in_new:", width="stretch")
    if c2.button("닫기", type="primary", width="stretch"):
        _finish()
        st.rerun()
