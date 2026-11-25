"""Notion 연동 (STEP 7-A): OAuth 연결 · 워크스페이스/페이지 선택 · 항목 선택 내보내기"""
import logging
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.db import as_utc, get_db, iso
from backend.models import NotionConnection, User
from backend.routers.records import get_owned_record, record_results, upsert_record
from backend.schemas import NotionExportRequest
from backend.security import decrypt_secret, get_current_user
from backend.services import notion_oauth
from backend.services.notion_service import NotionExportError, export_to_notion, list_pages
from backend.services.session_store import build_report, store

router = APIRouter(prefix="/notion", tags=["notion"])
logger = logging.getLogger(__name__)


def _connection_out(c: NotionConnection) -> dict:
    return {
        "id": c.id,
        "workspace_name": c.workspace_name,
        "workspace_icon": c.workspace_icon,
        "owner_name": c.owner_name,
        "created_at": iso(c.created_at),
    }


def _owned_connection(db: Session, connection_id: int, user: User) -> NotionConnection:
    conn = db.get(NotionConnection, connection_id)
    if conn is None or conn.user_id != user.id:
        raise HTTPException(404, "Notion 연결을 찾을 수 없습니다. 다시 연결해주세요.")
    return conn


def _token(conn: NotionConnection) -> str:
    try:
        return decrypt_secret(conn.access_token_enc)
    except ValueError as e:
        raise HTTPException(400, f"{e} Notion을 다시 연결해주세요.") from e


@router.get("/status")
def status(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    conns = db.scalars(select(NotionConnection).where(NotionConnection.user_id == user.id)).all()
    return {"configured": notion_oauth.is_configured(), "connections": [_connection_out(c) for c in conns]}


@router.post("/oauth/start")
def oauth_start(user: User = Depends(get_current_user)):
    try:
        return notion_oauth.start_login(user.id)
    except notion_oauth.NotionOAuthError as e:
        raise HTTPException(400, str(e)) from e


@router.get("/oauth/callback", response_class=HTMLResponse, include_in_schema=False)
def oauth_callback(state: str = "", code: str | None = None, error: str | None = None):
    """Notion이 인증 후 리다이렉트하는 주소 (NOTION_REDIRECT_URI)"""
    return HTMLResponse(notion_oauth.callback_page(notion_oauth.handle_callback(state, code, error)))


@router.delete("/connections/{connection_id}", status_code=204)
def disconnect(connection_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    db.delete(_owned_connection(db, connection_id, user))
    db.commit()


@router.get("/connections/{connection_id}/pages")
def pages(connection_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    conn = _owned_connection(db, connection_id, user)
    try:
        return {"pages": list_pages(_token(conn))}
    except NotionExportError as e:
        raise HTTPException(400, str(e)) from e


@router.post("/export")
def export(req: NotionExportRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    conn = _owned_connection(db, req.connection_id, user)
    s = None
    if req.record_id is not None:
        r = get_owned_record(db, req.record_id, user)
        filename, settings_, questions, results = r.filename, r.settings, r.questions, record_results(r)
        created_at, tutor_log = r.created_at, r.tutor_log or []
    else:
        s = store.get(req.session_id, user.id)
        filename, settings_, questions, results = s.filename, s.settings, s.questions, s.results
        created_at, tutor_log = s.created_at, s.tutor_log
    data = {
        "filename": filename,
        "created_at": (as_utc(created_at) or datetime.now().astimezone()).astimezone(),  # 서버 로컬 시간으로 표기
        "settings": settings_,
        "questions": questions,
        "results": results,
        "tutor_log": tutor_log,
        "report": build_report(filename, questions, results),
    }
    try:
        url = export_to_notion(_token(conn), req.parent_page_id, req.title, data, set(req.items))
    except NotionExportError as e:
        raise HTTPException(400, str(e)) from e

    # 학습 세션을 Notion에 저장하면 웹 학습 기록에도 기본으로 저장 (이미 있으면 갱신)
    record_saved = req.record_id is not None
    if s is not None:
        try:
            upsert_record(db, user.id, s)
            record_saved = True
        except Exception:  # noqa: BLE001 — Notion 저장은 이미 성공했으므로 실패해도 응답은 정상
            db.rollback()
            logger.exception("Notion 내보내기 후 웹 학습 기록 저장 실패")
    return {"url": url, "record_saved": record_saved}
