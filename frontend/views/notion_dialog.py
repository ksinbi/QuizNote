"""STEP 7-A. Notion 내보내기 — 단계별 모달 (계정 연결 → 페이지 선택 → 제목·항목 설정 → 완료)"""
import streamlit as st

import api_client as api
import state

ITEMS = [
    ("filename", "PDF 파일명"),
    ("questions", "전체 문제"),
    ("answers", "정답"),
    ("explanations", "해설"),
    ("user_answers", "사용자 답변"),
    ("results", "정답 및 오답 결과"),
    ("sources", "원문 출처"),
    ("stats", "최종 학습 통계"),
    ("tutor", "AI 튜터 질문 기록"),
]
TITLE_KEY = "notion_title"
STAGES = [("connect", "계정 연결"), ("select", "페이지 선택"), ("options", "내보내기 설정"), ("result", "완료")]


def open_dialog(source: dict, default_title: str, context: str) -> None:
    """context: 'flow'(학습 흐름 STEP 7) | 'history'(학습 기록 화면)"""
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
    """모달 닫기. 학습 흐름에서 저장에 성공했다면 STEP 8로 이동."""
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
            u["stage"] = "select"
    elif u["connection_id"] not in ids:
        u["connection_id"] = ids[-1] if ids else None


@st.dialog("📝 Notion으로 저장", width="large", on_dismiss=_finish)
def _dialog() -> None:
    u = state.ss().notion_ui
    if u["status"] is None:
        _refresh_status(u)

    idx = [k for k, _ in STAGES].index(u["stage"])
    st.progress((idx + 1) / len(STAGES), text=" → ".join(f"**{label}**" if i == idx else label for i, (_, label) in enumerate(STAGES)))

    if u["error"] and u["stage"] != "result":
        st.error(u["error"])
        u["error"] = None

    {"connect": _connect, "select": _select, "options": _options, "result": _result}[u["stage"]](u)


def _go(u: dict, stage: str) -> None:
    u["stage"] = stage
    st.rerun(scope="fragment")


# ---------- 1. 계정 연결 ----------
def _connect(u: dict) -> None:
    status = u["status"]
    if status is None:
        return
    if not status["configured"]:
        st.warning("서버에 Notion 연동(OAuth)이 설정되지 않았어요. 관리자는 .env에 NOTION_CLIENT_ID / NOTION_CLIENT_SECRET을 설정해주세요.")
        return

    conns = status["connections"]
    if conns:
        st.markdown("**연결된 워크스페이스**")
        ids = [c["id"] for c in conns]
        names = {c["id"]: f"{c['workspace_icon'] if len(c['workspace_icon']) <= 2 else '🗂️'} {c['workspace_name']}" + (f"  ·  {c['owner_name']}" if c["owner_name"] else "") for c in conns}
        chosen = st.radio("워크스페이스", ids, index=ids.index(u["connection_id"]) if u["connection_id"] in ids else 0, format_func=names.get, label_visibility="collapsed")
        u["connection_id"] = chosen
        with st.popover("연결 해제"):
            st.caption(f"'{names[chosen]}' 연결을 해제할까요?")
            if st.button("해제", type="primary"):
                try:
                    api.notion_disconnect(chosen)
                except api.APIError as e:
                    u["error"] = str(e)
                _refresh_status(u)
                st.rerun(scope="fragment")

    with st.container(border=True):
        st.markdown("**" + ("다른 워크스페이스 연결" if conns else "Notion 계정을 연결해주세요") + "**")
        st.caption("새 창에서 Notion에 로그인 → 권한 승인 → 결과를 저장할 페이지를 선택(공유)한 뒤, 이 창으로 돌아와 '연결 확인'을 눌러주세요.")
        if not u["authorize_url"]:
            if st.button("🔗 Notion 연결", type="secondary" if conns else "primary"):
                try:
                    u["authorize_url"] = api.notion_start()
                    u["known_connections"] = [c["id"] for c in conns]
                except api.APIError as e:
                    u["error"] = str(e)
                st.rerun(scope="fragment")
        else:
            c1, c2 = st.columns(2)
            c1.link_button("🔐 Notion 로그인 창 열기 ↗", u["authorize_url"], type="primary", width="stretch")
            if c2.button("✅ 연결 확인", width="stretch"):
                before = list(u["known_connections"] or [])
                _refresh_status(u, prefer_new=True)
                if u["stage"] == "connect" and [c["id"] for c in u["status"]["connections"]] == before:
                    u["error"] = "아직 연결이 완료되지 않았어요. Notion 창에서 '허용'까지 마쳤는지 확인해주세요."
                st.rerun(scope="fragment")

    if st.button("다음 →", type="primary", disabled=u["connection_id"] is None):
        _go(u, "select")


# ---------- 2. 워크스페이스 · 페이지 선택 ----------
def _select(u: dict) -> None:
    conns = u["status"]["connections"]
    if len(conns) > 1:
        ids = [c["id"] for c in conns]
        u["connection_id"] = st.selectbox(
            "워크스페이스", ids, index=ids.index(u["connection_id"]), format_func=lambda i: next(c["workspace_name"] for c in conns if c["id"] == i)
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

    query = st.text_input("페이지 검색", placeholder="페이지 제목으로 검색")
    filtered = [p for p in pages if query.strip().lower() in p["title"].lower()]
    if not pages:
        st.info("공유된 페이지가 없어요. '이전'으로 돌아가 다시 연결하면서 저장할 페이지를 선택해주세요.")
    elif not filtered:
        st.info("검색 결과가 없어요.")
    else:
        ids = [p["id"] for p in filtered]
        titles = {p["id"]: f"{p['icon'] or '📄'}  {p['title']}" for p in filtered}
        u["page_id"] = st.radio(
            "저장할 위치 (상위 페이지)", ids, index=ids.index(u["page_id"]) if u["page_id"] in ids else 0, format_func=titles.get
        )

    c1, c2 = st.columns(2)
    if c1.button("← 이전", width="stretch"):
        _go(u, "connect")
    if c2.button("다음 →", type="primary", width="stretch", disabled=not filtered):
        _go(u, "options")


# ---------- 3. 제목 · 항목 선택 ----------
def _reset_title(u: dict) -> None:
    st.session_state[TITLE_KEY] = u["default_title"]


def _options(u: dict) -> None:
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
    st.markdown("**내보낼 항목**")
    cols = st.columns(2)
    chosen = []
    for i, (key, label) in enumerate(ITEMS):
        if cols[i % 2].checkbox(label, value=key in u.get("items", [k for k, _ in ITEMS]), key=f"notion_item_{key}"):
            chosen.append(key)
    u["items"] = chosen
    if not chosen:
        st.caption(":red[최소 1개 항목을 선택해주세요.]")

    c1, c2 = st.columns(2)
    if c1.button("← 이전", width="stretch"):
        _go(u, "select")
    if c2.button("내보내기", type="primary", width="stretch", disabled=not chosen):
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


# ---------- 4. 결과 ----------
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
    st.success(f"✅ Notion에 저장했어요!\n\n**{u['title'] or u['default_title']}**")
    if u.get("record_saved") and u.get("context") == "flow":
        st.caption("☁️ 웹 계정의 '학습 기록'에도 함께 저장했어요.")
    c1, c2 = st.columns(2)
    if u["result_url"]:
        c1.link_button("Notion에서 열기 ↗", u["result_url"], width="stretch")
    if c2.button("닫기", type="primary", width="stretch"):
        _finish()
        st.rerun()
