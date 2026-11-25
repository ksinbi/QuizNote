"""학습 세션: PDF 업로드 → 문제 생성(백그라운드, 단계별 진행) → 채점 → 결과"""
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, UploadFile

from backend.config import settings
from backend.errors import friendly_llm_error
from backend.graphs.grading_graph import run_grading
from backend.graphs.quiz_graph import QuizGenerationError, run_quiz_generation
from backend.graphs.tutor_agent import chat_with_tutor
from backend.models import User
from backend.prompts.templates import SUMMARY_SYSTEM, SUMMARY_USER
from backend.schemas import AnswerRequest, ChatRequest, QuizSettings, UploadResponse
from backend.security import get_current_user
from backend.services import progress
from backend.services.llm import invoke_json
from backend.services.pdf_processor import PDFProcessingError, chunk_documents, extract_pages
from backend.services.session_store import QuizSession, store
from backend.services.vector_store import format_docs

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/sessions", tags=["sessions"])

_QUOTE_LEN = 160


def _owned(session_id: str, user: User) -> QuizSession:
    return store.get(session_id, user.id)


def _session_state(session: QuizSession) -> dict:
    return {
        "session_id": session.id,
        "filename": session.filename,
        "file_size": session.file_size,
        "num_pages": session.num_pages,
        "num_text_pages": session.num_text_pages,
        "summary": session.summary,
        "settings": session.settings,
        "questions": [QuizSession.public_question(q) for q in session.questions],
        "results": {str(k): v for k, v in session.results.items()},
        "tutor_log": session.tutor_log,
        "generation": progress.get(session.id),
    }


# ---------- STEP 1. 업로드 ----------
@router.post("", response_model=UploadResponse)
def upload_pdf(file: UploadFile = File(...), user: User = Depends(get_current_user)):
    """PDF 업로드 → PyMuPDF 텍스트 추출 → Chunking → 검색 인덱스 생성"""
    filename = file.filename or "document.pdf"
    if not filename.lower().endswith(".pdf"):
        raise HTTPException(400, "PDF 파일만 업로드할 수 있습니다.")
    data = file.file.read()
    if not data:
        raise HTTPException(400, "빈 파일입니다.")
    if len(data) > settings.max_upload_mb * 1024 * 1024:
        raise HTTPException(413, f"파일이 너무 큽니다. (최대 {settings.max_upload_mb}MB)")
    try:
        pages, num_pages = extract_pages(data, filename)
    except PDFProcessingError as e:
        raise HTTPException(400, str(e)) from e

    chunks = chunk_documents(pages)
    session = store.create(user.id, filename, len(data), num_pages, len(pages), chunks)
    return UploadResponse(
        session_id=session.id,
        filename=filename,
        file_size=len(data),
        num_pages=num_pages,
        num_text_pages=len(pages),
        num_chunks=len(chunks),
        num_chars=sum(len(p.page_content) for p in pages),
        retriever_mode=session.retriever.mode,
    )


@router.get("/{session_id}")
def get_session(session_id: str, user: User = Depends(get_current_user)):
    """세션 상태 복원용 (새로고침 후 이어서 풀기)"""
    return _session_state(_owned(session_id, user))


# ---------- STEP 3. 문제 생성 ----------
def _attach_sources(session: QuizSession, questions: list[dict]) -> list[dict]:
    """출처 페이지가 실제 문서 범위인지 확인하고, 원문 발췌가 없으면 검색으로 보완합니다."""
    valid_pages = {c.metadata.get("page") for c in session.chunks}
    out = []
    for q in questions:
        q = dict(q)
        page = q.get("source_page")
        quote = (q.get("source_quote") or "").strip()
        if page not in valid_pages or not quote:
            hits = session.retriever.search(f"{q.get('concept', '')} {q['question']}", k=1)
            if hits:
                if page not in valid_pages:
                    page = hits[0].metadata.get("page")
                if not quote:
                    same_page = [c for c in session.chunks if c.metadata.get("page") == page] or hits
                    best = next((c for c in hits if c.metadata.get("page") == page), same_page[0])
                    quote = " ".join(best.page_content.split())[:_QUOTE_LEN]
        q["source_page"] = page if page in valid_pages else None
        q["source_quote"] = quote[:300]
        out.append(q)
    return out


def _generate_job(session_id: str, cfg: QuizSettings, job_id: str) -> None:
    try:
        progress.set_stage(session_id, "extract", "문서를 불러오는 중")
        session = store.get(session_id)
        _ = session.retriever  # 검색 인덱스 준비

        progress.set_stage(session_id, "analyze", "문서의 핵심 개념을 파악하는 중")
        if session.summary is None:
            context = format_docs(session.retriever.sample_diverse(10), max_chars=15000)
            try:
                session.summary = invoke_json(SUMMARY_SYSTEM, SUMMARY_USER.format(context=context), max_tokens=2000)
            except Exception as e:  # 요약은 부가 정보이므로 실패해도 출제는 계속
                logger.warning("요약 생성 실패: %s", e)
            store.save(session)

        questions = run_quiz_generation(
            session_id, cfg.num_questions, cfg.num_essay, cfg.difficulty, cfg.focus_topic, cfg.use_web
        )

        progress.set_stage(session_id, "sources", "PDF 페이지 정보를 연결하는 중")
        questions = _attach_sources(session, questions)
        if not progress.is_current(session_id, job_id):
            logger.info("취소되었거나 새 작업으로 바뀐 문제 생성 결과는 저장하지 않습니다 (%s)", session_id)
            return
        # 생성하는 동안 바뀌었을 수 있는 값(요약 등)을 덮어쓰지 않도록 최신 세션에 문제만 반영
        session = store.get(session_id)
        session.settings = cfg.model_dump()
        session.set_questions(questions)
        store.save(session)
        progress.finish(session_id, job_id)
    except QuizGenerationError as e:
        progress.fail(session_id, str(e), job_id)
    except Exception as e:  # noqa: BLE001 — 어떤 오류든 사용자에게 안내
        logger.exception("문제 생성 실패")
        progress.fail(session_id, friendly_llm_error(e), job_id)


@router.post("/{session_id}/quiz", status_code=202)
def create_quiz(
    session_id: str, cfg: QuizSettings, background: BackgroundTasks, user: User = Depends(get_current_user)
):
    """문제 생성 작업 시작 → GET /sessions/{id}/progress 로 진행 상황 확인"""
    _owned(session_id, user)
    job_id = progress.start(session_id)
    if job_id is None:
        raise HTTPException(409, "이미 문제를 생성하고 있습니다.")
    background.add_task(_generate_job, session_id, cfg, job_id)
    return progress.get(session_id)


@router.post("/{session_id}/quiz/cancel")
def cancel_quiz(session_id: str, user: User = Depends(get_current_user)):
    """진행 중인 문제 생성 취소 (결과를 저장하지 않음). 취소 후 바로 다시 생성할 수 있습니다."""
    _owned(session_id, user)
    return {"cancelled": progress.cancel(session_id)}


@router.get("/{session_id}/progress")
def quiz_progress(session_id: str, user: User = Depends(get_current_user)):
    _owned(session_id, user)
    return progress.get(session_id)


# ---------- STEP 4~5. 풀이 · 채점 ----------
@router.post("/{session_id}/answer")
def answer(session_id: str, req: AnswerRequest, user: User = Depends(get_current_user)):
    """객관식 판정 / 서술형 의미 기반 AI 채점 / 오답 보충 설명"""
    session = _owned(session_id, user)
    use_web = bool((session.settings or {}).get("use_web"))
    try:
        return run_grading(session, req.question_id, req.answer, use_web)
    except KeyError:
        raise
    except Exception as e:  # noqa: BLE001
        logger.exception("채점 실패")
        raise HTTPException(502, f"채점 중 오류가 발생했습니다. {friendly_llm_error(e)}") from e


@router.post("/{session_id}/chat")
def chat(session_id: str, req: ChatRequest, user: User = Depends(get_current_user)):
    """AI 튜터 (힌트 · 자유 질문 · 복습 질문). 질문과 답변은 세션에 저장되어 Notion 내보내기에 포함됩니다."""
    session = _owned(session_id, user)
    qid = req.current_question_id
    try:
        res = chat_with_tutor(session, req.message, qid, req.use_web)
    except Exception as e:  # noqa: BLE001
        logger.exception("튜터 응답 실패")
        raise HTTPException(502, friendly_llm_error(e)) from e
    entry = {
        "qid": qid,
        "after": qid is None or qid in session.results,  # 채점 후(또는 학습 완료 화면)에 한 질문인지
        "label": (req.label or req.message).strip(),
        "message": req.message,
        "reply": res["reply"],
        "tools": res["tools_used"],
        "at": datetime.now(timezone.utc).isoformat(),
    }
    store.append_tutor(session.id, entry)
    return {**res, "entry": entry}


# ---------- STEP 6. 결과 ----------
@router.get("/{session_id}/report")
def report(session_id: str, user: User = Depends(get_current_user)):
    session = _owned(session_id, user)
    rep = session.report()
    # 풀이를 마친 문항에 한해 정답 · 해설 · 출처 포함
    detail = []
    for q in session.questions:
        r = session.results.get(q["id"])
        detail.append({**q, "result": r} if r else QuizSession.public_question(q))
    return {**rep, "questions": detail, "settings": session.settings, "tutor_log": session.tutor_log}
