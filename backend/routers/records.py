"""웹 계정에 학습 결과 저장 · 조회 (STEP 7-B)"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.db import get_db, iso
from backend.models import StudyRecord, User
from backend.schemas import SaveRecordRequest
from backend.security import get_current_user
from backend.services.session_store import QuizSession, build_report, store

router = APIRouter(prefix="/records", tags=["records"])


def record_summary(r: StudyRecord) -> dict:
    return {
        "id": r.id,
        "session_id": r.session_id,
        "filename": r.filename,
        "created_at": iso(r.created_at),
        "settings": r.settings,
        "total": r.total,
        "correct": r.correct,
        "wrong": r.wrong,
        "accuracy": r.accuracy,
    }


def record_results(r: StudyRecord) -> dict[int, dict]:
    return {int(k): v for k, v in (r.results or {}).items()}


def get_owned_record(db: Session, record_id: int, user: User) -> StudyRecord:
    record = db.get(StudyRecord, record_id)
    if record is None or record.user_id != user.id:
        raise HTTPException(404, "학습 기록을 찾을 수 없습니다.")
    return record


def upsert_record(db: Session, user_id: int, session: QuizSession) -> StudyRecord:
    """세션을 웹 학습 기록으로 저장. 같은 세션을 다시 저장하면 기존 기록을 갱신합니다."""
    rep = session.report()
    record = db.scalar(
        select(StudyRecord).where(StudyRecord.user_id == user_id, StudyRecord.session_id == session.id)
    )
    if record is None:
        record = StudyRecord(user_id=user_id, session_id=session.id)
        db.add(record)
    record.filename = session.filename
    record.settings = session.settings or {}
    record.questions = session.questions
    record.results = {str(k): v for k, v in session.results.items()}
    record.tutor_log = session.tutor_log
    record.total, record.correct, record.wrong, record.accuracy = rep["total"], rep["correct"], rep["wrong"], rep["accuracy"]
    db.commit()
    db.refresh(record)
    return record


@router.post("", status_code=201)
def save_record(req: SaveRecordRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    session = store.get(req.session_id, user.id)
    if not session.questions:
        raise HTTPException(400, "저장할 문제가 없습니다.")
    return record_summary(upsert_record(db, user.id, session))


@router.get("")
def list_records(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = db.scalars(
        select(StudyRecord).where(StudyRecord.user_id == user.id).order_by(StudyRecord.created_at.desc())
    ).all()
    return {"records": [record_summary(r) for r in rows]}


@router.get("/{record_id}")
def get_record(record_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    r = get_owned_record(db, record_id, user)
    results = record_results(r)
    rep = build_report(r.filename, r.questions, results)
    questions = [{**q, "result": results.get(q["id"])} for q in r.questions]
    return {**record_summary(r), "report": rep, "questions": questions, "tutor_log": r.tutor_log or []}


@router.delete("/{record_id}", status_code=204)
def delete_record(record_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    db.delete(get_owned_record(db, record_id, user))
    db.commit()
