"""세션 상태 · 로그인 유지 · 학습 진행 단계 관리.

Streamlit은 새로고침하면 session_state가 초기화되므로
- 로그인 토큰은 브라우저 쿠키에 저장하고 st.context.cookies로 복원하고
- 학습 진행 단계(업로드 정보, 설정, 풀이 위치 등)는 백엔드 DB(/auth/me/flow)에 사용자별로 저장합니다.
"""
import copy
import json

import streamlit as st

import api_client as api

COOKIE_NAME = "qn_token"
COOKIE_MAX_AGE = 60 * 60 * 24 * 7

STEPS = ["upload", "settings", "generating", "quiz", "summary", "done"]

DEFAULT_SETTINGS = {
    "num_questions": 5,
    "num_essay": 1,
    "difficulty": "보통",
    "show_answer": True,
    "show_explanation": True,
    "show_source": True,
    "focus_topic": "",
    "use_web": False,
}

_SESSION_DEFAULTS = {
    "token": None,
    "user": None,
    "flow": None,
    "flow_saved_json": None,
    "view": "study",
    "logged_out": False,
    "auth_expired": False,
    "cookie_js": None,
    # 화면 전용(새로고침 시 사라져도 되는 값)
    "pdf_bytes": None,
    "uploaded_file_id": None,
    "upload_error": None,
    "uploader_nonce": 0,
    "quiz_cache": None,
    "quiz_error": None,
    "tutor": {},
    "tutor_error": None,
    "gen_error": None,
    "gen_started": None,
    "report_cache": None,
    "notion_ui": None,
    "notion_open": False,
    "history_selected": None,
    "record_cache": None,
}


def ss():
    return st.session_state


def init() -> None:
    for k, v in _SESSION_DEFAULTS.items():
        if k not in st.session_state:
            st.session_state[k] = copy.deepcopy(v)


# ---------- 로그인 유지(쿠키) ----------
def _queue_cookie(token: str | None) -> None:
    if token:
        cookie = f"{COOKIE_NAME}={token}; path=/; max-age={COOKIE_MAX_AGE}; SameSite=Lax"
    else:
        cookie = f"{COOKIE_NAME}=; path=/; max-age=0; SameSite=Lax"
    ss().cookie_js = f"<script>try{{window.parent.document.cookie={json.dumps(cookie)};}}catch(e){{}}</script>"


def render_cookie_js() -> None:
    """대기 중인 쿠키 변경을 브라우저에 반영 (높이 0짜리 컴포넌트)."""
    if ss().cookie_js:
        # 같은 origin iframe에서 실행되어 앱 페이지의 쿠키를 설정 (우리 서버가 발급한 토큰만 포함)
        st.iframe(ss().cookie_js, height=1)
        ss().cookie_js = None


def restore_login() -> None:
    if ss().user or ss().logged_out:
        return
    token = st.context.cookies.get(COOKIE_NAME)
    if not token:
        return
    ss().token = token
    try:
        ss().user = api.me()
        load_flow()
    except api.APIError:
        ss().token = None
        ss().user = None
        _queue_cookie(None)


def login_success(res: dict) -> None:
    ss().token = res["access_token"]
    ss().user = res["user"]
    ss().logged_out = False
    ss().auth_expired = False
    _queue_cookie(res["access_token"])
    load_flow()


def logout() -> None:
    for k, v in _SESSION_DEFAULTS.items():
        st.session_state[k] = copy.deepcopy(v)
    ss().logged_out = True  # 같은 세션에서 기존 쿠키로 자동 로그인되지 않도록
    _queue_cookie(None)


# ---------- 학습 진행 단계 ----------
def default_flow(settings: dict | None = None) -> dict:
    return {
        "step": "upload",
        "upload": None,
        "settings": dict(settings or DEFAULT_SETTINGS),
        "current_index": 0,
        "saved": None,
        "ended": False,
    }


def load_flow() -> None:
    try:
        saved = api.get_flow()
    except api.APIError:
        saved = None
    flow = default_flow()
    if isinstance(saved, dict):
        flow.update({k: v for k, v in saved.items() if k in flow})
        flow["settings"] = {**DEFAULT_SETTINGS, **(saved.get("settings") or {})}
        if flow["step"] not in STEPS:
            flow["step"] = "upload"
    ss().flow = flow
    ss().flow_saved_json = json.dumps(flow, sort_keys=True, ensure_ascii=False)


def flow() -> dict:
    if ss().flow is None:
        ss().flow = default_flow()
    return ss().flow


def _persist() -> None:
    data = json.dumps(flow(), sort_keys=True, ensure_ascii=False)
    if data == ss().flow_saved_json:
        return
    try:
        api.put_flow(flow())
        ss().flow_saved_json = data
    except api.APIError:
        pass  # 저장 실패해도 현재 화면 진행에는 영향 없음


def update_flow(**patch) -> None:
    flow().update(patch)
    _persist()


def clear_study_cache() -> None:
    for k in ("quiz_cache", "quiz_error", "gen_error", "gen_started", "report_cache"):
        st.session_state[k] = copy.deepcopy(_SESSION_DEFAULTS[k])
    ss().tutor = {}


def reset_flow() -> None:
    """새 학습 세션 시작 (문제 설정은 유지)"""
    settings = flow()["settings"]
    ss().flow = default_flow(settings)
    ss().pdf_bytes = None
    ss().uploaded_file_id = None
    ss().upload_error = None
    ss().uploader_nonce += 1
    clear_study_cache()
    _persist()
