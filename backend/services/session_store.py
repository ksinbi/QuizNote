"""문제 세션 저장소 (DB 기반).

업로드한 문서의 청크 · 생성된 문항 · 채점 결과를 quiz_sessions 테이블에 저장하므로
새로고침하거나 서버를 재시작해도 이어서 풀 수 있습니다.
검색기(BM25/벡터 인덱스)는 메모리에 캐시하고, 캐시에 없으면 저장된 청크로 다시 만듭니다.
"""
import threading
import uuid
from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import datetime

from langchain_core.documents import Document

from backend.config import settings
from backend.db import SessionLocal
from backend.models import QuizSessionRow
from backend.services.vector_store import LectureRetriever

_PRIVATE_KEYS = {"answer_index", "explanation", "model_answer", "key_points", "source_quote"}
_RETRIEVER_CACHE_SIZE = 32
_TUTOR_LOG_LIMIT = 300  # 세션당 저장할 튜터 대화 최대 개수


class SessionNotFound(KeyError):
    pass


@dataclass
class QuizSession:
    id: str
    user_id: int
    filename: str
    num_pages: int
    num_text_pages: int
    file_size: int
    chunks: list[Document]
    summary: dict | None = None
    settings: dict | None = None
    questions: list[dict] = field(default_factory=list)
    results: dict[int, dict] = field(default_factory=dict)  # question_id -> 채점 결과
    tutor_log: list[dict] = field(default_factory=list)  # AI 튜터 질문 · 답변 기록
    created_at: datetime | None = None

    @property
    def retriever(self) -> LectureRetriever:
        return store.retriever(self.id, self.chunks)

    def get_question(self, question_id: int) -> dict:
        for q in self.questions:
            if q["id"] == question_id:
                return q
        raise SessionNotFound(f"문항 {question_id}을(를) 찾을 수 없습니다.")

    def set_questions(self, questions: list[dict]) -> None:
        """새 문제 세트로 교체. id는 1부터 다시 매깁니다."""
        self.questions = [{**q, "id": i} for i, q in enumerate(questions, start=1)]
        self.results = {}
        self.tutor_log = []  # 이전 문제 세트에 대한 질문은 문항 번호가 맞지 않으므로 초기화

    @staticmethod
    def public_question(q: dict) -> dict:
        """정답 정보를 제외한, 풀이 화면에 보낼 문항."""
        return {k: v for k, v in q.items() if k not in _PRIVATE_KEYS}

    def report(self) -> dict:
        return build_report(self.filename, self.questions, self.results)


def build_report(filename: str, questions: list[dict], results: dict[int, dict]) -> dict:
    """학습 통계 + 문제별 결과 (세션과 저장된 학습 기록에서 공통 사용)."""
    items = []
    for q in questions:
        r = results.get(q["id"])
        items.append(
            {
                "question_id": q["id"],
                "type": q["type"],
                "question": q["question"],
                "concept": q.get("concept", ""),
                "answered": r is not None,
                "is_correct": bool(r and r["is_correct"]),
                "score": r["score"] if r else 0,
                "user_answer": r["user_answer"] if r else "",
                "correct_answer": r["correct_answer"] if r else "",
            }
        )
    total = len(questions)
    answered = sum(1 for i in items if i["answered"])
    correct = sum(1 for i in items if i["is_correct"])
    graded_scores = [i["score"] for i in items if i["answered"]]
    return {
        "filename": filename,
        "total": total,
        "answered": answered,
        "correct": correct,
        "wrong": total - correct,
        "accuracy": round(correct / total * 100, 1) if total else 0.0,
        "average_score": round(sum(graded_scores) / len(graded_scores), 1) if graded_scores else 0.0,
        "pass_score": settings.pass_score,
        "weak_concepts": sorted({i["concept"] for i in items if i["answered"] and not i["is_correct"]} - {""}),
        "items": items,
    }


def _chunks_to_json(chunks: list[Document]) -> list[dict]:
    return [{"text": c.page_content, **c.metadata} for c in chunks]


def _chunks_from_json(data: list[dict], filename: str) -> list[Document]:
    docs = []
    for i, item in enumerate(data):
        meta = {k: v for k, v in item.items() if k != "text"}
        meta.setdefault("source", filename)
        meta.setdefault("chunk_id", i)
        docs.append(Document(page_content=item["text"], metadata=meta))
    return docs


def _to_session(row: QuizSessionRow) -> QuizSession:
    return QuizSession(
        id=row.id,
        user_id=row.user_id,
        filename=row.filename,
        num_pages=row.num_pages,
        num_text_pages=row.num_text_pages,
        file_size=row.file_size,
        chunks=_chunks_from_json(row.chunks or [], row.filename),
        summary=row.summary,
        settings=row.settings,
        questions=row.questions or [],
        results={int(k): v for k, v in (row.results or {}).items()},
        tutor_log=row.tutor_log or [],
        created_at=row.created_at,
    )


class SessionStore:
    def __init__(self):
        self._retrievers: OrderedDict[str, LectureRetriever] = OrderedDict()
        self._lock = threading.Lock()

    # ----- 검색기 캐시 -----
    def retriever(self, session_id: str, chunks: list[Document]) -> LectureRetriever:
        with self._lock:
            if session_id in self._retrievers:
                self._retrievers.move_to_end(session_id)
                return self._retrievers[session_id]
        built = LectureRetriever(chunks)
        with self._lock:
            self._retrievers[session_id] = built
            while len(self._retrievers) > _RETRIEVER_CACHE_SIZE:
                self._retrievers.popitem(last=False)
        return built

    # ----- CRUD -----
    def create(
        self, user_id: int, filename: str, file_size: int, num_pages: int, num_text_pages: int, chunks: list[Document]
    ) -> QuizSession:
        session_id = uuid.uuid4().hex
        retriever = LectureRetriever(chunks)
        with SessionLocal() as db:
            row = QuizSessionRow(
                id=session_id,
                user_id=user_id,
                filename=filename,
                file_size=file_size,
                num_pages=num_pages,
                num_text_pages=num_text_pages,
                chunks=_chunks_to_json(chunks),
                questions=[],
                results={},
                tutor_log=[],
            )
            db.add(row)
            db.commit()
            db.refresh(row)
            session = _to_session(row)
        with self._lock:
            self._retrievers[session_id] = retriever
        return session

    def get(self, session_id: str, user_id: int | None = None) -> QuizSession:
        with SessionLocal() as db:
            row = db.get(QuizSessionRow, session_id)
            if row is None or (user_id is not None and row.user_id != user_id):
                raise SessionNotFound("학습 세션을 찾을 수 없습니다. PDF를 다시 업로드해주세요.")
            return _to_session(row)

    def save(self, session: QuizSession) -> None:
        with self._lock, SessionLocal() as db:
            row = db.get(QuizSessionRow, session.id)
            if row is None:
                raise SessionNotFound("학습 세션을 찾을 수 없습니다.")
            row.summary = session.summary
            row.settings = session.settings
            row.questions = session.questions
            row.results = {str(k): v for k, v in session.results.items()}
            row.tutor_log = session.tutor_log
            db.commit()

    def save_result(self, session_id: str, question_id: int, result: dict) -> None:
        """채점 결과 1건만 병합 저장 (동시에 들어온 다른 결과를 덮어쓰지 않도록)."""
        with self._lock, SessionLocal() as db:
            row = db.get(QuizSessionRow, session_id)
            if row is None:
                raise SessionNotFound("학습 세션을 찾을 수 없습니다.")
            row.results = {**(row.results or {}), str(question_id): result}
            db.commit()

    def append_tutor(self, session_id: str, entry: dict) -> None:
        """튜터 질문 · 답변 1건을 기록에 추가."""
        with self._lock, SessionLocal() as db:
            row = db.get(QuizSessionRow, session_id)
            if row is None:
                raise SessionNotFound("학습 세션을 찾을 수 없습니다.")
            row.tutor_log = [*(row.tutor_log or []), entry][-_TUTOR_LOG_LIMIT:]
            db.commit()


store = SessionStore()
