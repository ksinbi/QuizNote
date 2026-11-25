"""FastAPI 백엔드 호출 (UI 로직과 분리). 로그인 토큰은 st.session_state["token"]에서 읽습니다."""
import os

import requests
import streamlit as st

BACKEND_URL = os.getenv("BACKEND_URL", "http://127.0.0.1:8000").rstrip("/")


class APIError(Exception):
    def __init__(self, message: str, status: int = 0):
        super().__init__(message)
        self.status = status


def _detail(data, status: int) -> str:
    detail = (data or {}).get("detail") if isinstance(data, dict) else None
    if isinstance(detail, str):
        return detail
    if isinstance(detail, list):  # Pydantic 검증 오류
        msgs = [str(d.get("msg", "")).removeprefix("Value error, ") for d in detail if isinstance(d, dict)]
        return "\n".join(m for m in msgs if m) or "입력값을 확인해주세요."
    if status >= 500:
        return "서버 오류가 발생했습니다. 잠시 후 다시 시도해주세요."
    return f"요청을 처리하지 못했습니다. ({status})"


def _request(method: str, path: str, *, json=None, files=None, timeout: float = 60):
    headers = {}
    token = st.session_state.get("token")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    try:
        r = requests.request(method, BACKEND_URL + path, json=json, files=files, headers=headers, timeout=timeout)
    except requests.Timeout as e:
        raise APIError("서버 응답 시간이 초과되었습니다. 잠시 후 다시 시도해주세요.") from e
    except requests.RequestException as e:
        raise APIError("백엔드 서버에 연결할 수 없습니다. 서버 실행 여부를 확인해주세요.") from e
    if r.status_code == 204:
        return None
    try:
        data = r.json()
    except ValueError:
        data = None
    if not r.ok:
        if r.status_code == 401 and token:
            st.session_state["auth_expired"] = True
        raise APIError(_detail(data, r.status_code), r.status_code)
    return data


# ---------- 인증 ----------
def login(email: str, password: str) -> dict:
    return _request("POST", "/auth/login", json={"email": email, "password": password})


def register(email: str, password: str, name: str) -> dict:
    return _request("POST", "/auth/register", json={"email": email, "password": password, "name": name})


def me() -> dict:
    return _request("GET", "/auth/me")


def get_flow() -> dict | None:
    return _request("GET", "/auth/me/flow")["state"]


def put_flow(state: dict) -> None:
    _request("PUT", "/auth/me/flow", json={"state": state}, timeout=10)


# ---------- 학습 세션 ----------
def upload_pdf(filename: str, data: bytes) -> dict:
    # 첫 업로드 시 임베딩 모델 로딩으로 오래 걸릴 수 있음
    return _request("POST", "/sessions", files={"file": (filename, data, "application/pdf")}, timeout=300)


def get_session(session_id: str) -> dict:
    return _request("GET", f"/sessions/{session_id}")


def generate(session_id: str, settings: dict) -> dict:
    return _request("POST", f"/sessions/{session_id}/quiz", json=settings)


def progress(session_id: str) -> dict:
    return _request("GET", f"/sessions/{session_id}/progress", timeout=15)


def answer(session_id: str, question_id: int, text: str) -> dict:
    return _request("POST", f"/sessions/{session_id}/answer", json={"question_id": question_id, "answer": text}, timeout=180)


def chat(
    session_id: str, message: str, current_question_id: int | None, use_web: bool = False, label: str | None = None
) -> dict:
    return _request(
        "POST",
        f"/sessions/{session_id}/chat",
        json={"message": message, "current_question_id": current_question_id, "use_web": use_web, "label": label},
        timeout=120,
    )


def report(session_id: str) -> dict:
    return _request("GET", f"/sessions/{session_id}/report")


# ---------- 학습 기록 ----------
def save_record(session_id: str) -> dict:
    return _request("POST", "/records", json={"session_id": session_id})


def list_records() -> list[dict]:
    return _request("GET", "/records")["records"]


def get_record(record_id: int) -> dict:
    return _request("GET", f"/records/{record_id}")


def delete_record(record_id: int) -> None:
    _request("DELETE", f"/records/{record_id}")


# ---------- Notion ----------
def notion_status() -> dict:
    return _request("GET", "/notion/status")


def notion_start() -> str:
    return _request("POST", "/notion/oauth/start")["authorize_url"]


def notion_disconnect(connection_id: int) -> None:
    _request("DELETE", f"/notion/connections/{connection_id}")


def notion_pages(connection_id: int) -> list[dict]:
    return _request("GET", f"/notion/connections/{connection_id}/pages")["pages"]


def notion_export(source: dict, connection_id: int, parent_page_id: str, title: str, items: list[str]) -> dict:
    """반환: {"url": Notion 페이지 주소, "record_saved": 웹 학습 기록에도 저장됐는지}"""
    body = {
        "session_id": source.get("session_id"),
        "record_id": source.get("record_id"),
        "connection_id": connection_id,
        "parent_page_id": parent_page_id,
        "title": title,
        "items": items,
    }
    return _request("POST", "/notion/export", json=body, timeout=120)
