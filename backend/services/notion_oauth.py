"""Notion OAuth 로그인 (Public Integration)

흐름
1. 프런트: POST /notion/oauth/start (JWT 필요) → {authorize_url}  → 팝업으로 열기
2. 사용자: Notion 로그인 → 권한 승인 → 공유할 페이지 선택
3. Notion → GET /notion/oauth/callback?code&state
   백엔드가 code를 access_token으로 교환하고, state에 묶인 사용자 계정에 토큰을 '암호화'해 저장
4. 콜백 페이지가 window.opener에 결과를 postMessage 하고 팝업을 닫음 → 프런트가 연결 목록을 새로고침

토큰은 프런트엔드로 전달되지 않습니다.
"""
import html
import json
import secrets
import threading
import time
from urllib.parse import urlencode

import httpx
from sqlalchemy import select

from backend.config import settings
from backend.db import SessionLocal
from backend.models import NotionConnection
from backend.security import encrypt_secret

AUTHORIZE_URL = "https://api.notion.com/v1/oauth/authorize"
TOKEN_URL = "https://api.notion.com/v1/oauth/token"
LOGIN_TTL = 600  # 로그인 대기 유효시간(초)


class NotionOAuthError(Exception):
    pass


_pending: dict[str, dict] = {}  # state -> {"created": ts, "user_id": int}
_lock = threading.Lock()


def is_configured() -> bool:
    return bool(settings.notion_client_id and settings.notion_client_secret)


def _cleanup() -> None:
    now = time.time()
    for state in [s for s, v in _pending.items() if now - v["created"] > LOGIN_TTL]:
        _pending.pop(state, None)


def start_login(user_id: int) -> dict:
    if not is_configured():
        raise NotionOAuthError("서버에 Notion 연동(OAuth)이 설정되지 않았습니다. 관리자에게 문의하세요.")
    state = secrets.token_urlsafe(24)
    with _lock:
        _cleanup()
        _pending[state] = {"created": time.time(), "user_id": user_id}
    query = urlencode(
        {
            "client_id": settings.notion_client_id,
            "response_type": "code",
            "owner": "user",
            "redirect_uri": settings.notion_redirect_uri,
            "state": state,
        }
    )
    return {"authorize_url": f"{AUTHORIZE_URL}?{query}"}


def _exchange_code(code: str) -> dict:
    try:
        resp = httpx.post(
            TOKEN_URL,
            auth=(settings.notion_client_id, settings.notion_client_secret),
            json={"grant_type": "authorization_code", "code": code, "redirect_uri": settings.notion_redirect_uri},
            headers={"Notion-Version": "2022-06-28"},
            timeout=15,
        )
    except httpx.HTTPError as e:
        raise NotionOAuthError(f"Notion 서버에 연결할 수 없습니다: {e}") from e
    if resp.status_code != 200:
        raise NotionOAuthError(f"토큰 발급 실패 ({resp.status_code})")
    return resp.json()


def _save_connection(user_id: int, data: dict) -> str:
    workspace_id = data.get("workspace_id") or data.get("bot_id") or "unknown"
    workspace_name = data.get("workspace_name") or "Notion 워크스페이스"
    owner = ((data.get("owner") or {}).get("user") or {}).get("name") or ""
    with SessionLocal() as db:
        conn = db.scalar(
            select(NotionConnection).where(
                NotionConnection.user_id == user_id, NotionConnection.workspace_id == workspace_id
            )
        )
        if conn is None:
            conn = NotionConnection(user_id=user_id, workspace_id=workspace_id)
            db.add(conn)
        conn.workspace_name = workspace_name
        conn.workspace_icon = data.get("workspace_icon") or ""
        conn.owner_name = owner
        conn.access_token_enc = encrypt_secret(data["access_token"])
        db.commit()
    return workspace_name


def handle_callback(state: str, code: str | None, error: str | None) -> dict:
    """Notion 리다이렉트 처리 → 연결 저장. 결과(토큰 제외)를 반환."""
    with _lock:
        entry = _pending.pop(state, None)
    if entry is None or time.time() - entry["created"] > LOGIN_TTL:
        return {"status": "error", "message": "연결 요청이 만료되었거나 올바르지 않습니다. 다시 시도해주세요."}
    if error:
        msg = "Notion 연결이 취소되었습니다." if error == "access_denied" else f"Notion 연결 오류: {error}"
        return {"status": "error", "message": msg}
    if not code:
        return {"status": "error", "message": "인증 코드가 없습니다."}
    try:
        workspace_name = _save_connection(entry["user_id"], _exchange_code(code))
    except NotionOAuthError as e:
        return {"status": "error", "message": str(e)}
    return {"status": "done", "workspace_name": workspace_name}


def callback_page(result: dict) -> str:
    ok = result.get("status") == "done"
    title = "Notion 연결 완료" if ok else "Notion 연결 실패"
    body = (
        f"<b>{html.escape(result.get('workspace_name', ''))}</b> 워크스페이스가 연결되었어요.<br>이 창을 닫고 Quiz Note로 돌아가 <b>'연결 확인'</b>을 눌러주세요."
        if ok
        else f"{html.escape(result.get('message', '알 수 없는 오류'))}<br>창을 닫고 다시 시도해주세요."
    )
    message = json.dumps({"type": "notion-oauth", **result}, ensure_ascii=False)
    target = json.dumps(settings.frontend_url)
    return f"""<!doctype html><html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>{title}</title>
<style>body{{margin:0;min-height:100vh;display:flex;align-items:center;justify-content:center;
background:#f1f5f9;font-family:-apple-system,BlinkMacSystemFont,'Apple SD Gothic Neo',sans-serif}}
.card{{background:#fff;border-radius:16px;padding:32px 28px;max-width:380px;text-align:center;box-shadow:0 8px 24px rgba(15,23,42,.08)}}
.icon{{font-size:44px}}h1{{font-size:20px;margin:12px 0;color:#0f172a}}p{{color:#475569;line-height:1.6}}
button{{margin-top:14px;background:#4f46e5;color:#fff;border:0;padding:10px 18px;border-radius:10px;font-weight:600;cursor:pointer}}</style>
</head><body><div class="card"><div class="icon">{'✅' if ok else '⚠️'}</div><h1>{title}</h1><p>{body}</p>
<button onclick="window.close()">창 닫기</button></div>
<script>
try {{ if (window.opener) window.opener.postMessage({message}, {target}); }} catch (e) {{}}
{'setTimeout(function(){ window.close(); }, 1500);' if ok else ''}
</script></body></html>"""
