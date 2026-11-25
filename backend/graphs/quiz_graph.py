"""LangGraph: 퀴즈 생성 워크플로우

START → retrieve_context ─┬─(use_web)→ web_enrich ─┐
                          └────────────────────────┴→ generate_quiz → validate_quiz ─┬→ END
                                                          ↑______(검증 실패, 재시도)___┘
"""
import random
from typing import TypedDict

from langgraph.graph import END, START, StateGraph
from pydantic import ValidationError

from backend.prompts.templates import QUIZ_SYSTEM, QUIZ_USER
from backend.schemas import QuizPayload
from backend.services import progress
from backend.services.llm import LLMOutputError, invoke_json
from backend.services.session_store import store
from backend.services.vector_store import format_docs
from backend.services.web_search import format_web_results, search_web

MAX_ATTEMPTS = 3


class QuizGenerationError(Exception):
    pass


class QuizState(TypedDict, total=False):
    session_id: str
    num_mcq: int
    num_essay: int
    difficulty: str
    focus_topic: str
    use_web: bool
    context: str
    web_context: str
    raw_quiz: dict | None
    questions: list[dict]
    validation_error: str
    attempts: int


def retrieve_context(state: QuizState) -> dict:
    """집중 주제가 있으면 RAG 검색, 없으면 문서 전체에서 고르게 청크를 샘플링."""
    session = store.get(state["session_id"])
    total = state["num_mcq"] + state["num_essay"]
    n_chunks = min(len(session.chunks), max(6, total * 2))
    focus = state.get("focus_topic", "").strip()
    docs = session.retriever.search(focus, k=n_chunks) if focus else session.retriever.sample_diverse(n_chunks)
    return {"context": format_docs(docs, max_chars=24000), "attempts": 0}


def web_enrich(state: QuizState) -> dict:
    session = store.get(state["session_id"])
    keywords = (session.summary or {}).get("keywords", [])[:3]
    query = state.get("focus_topic") or " ".join(keywords) or session.filename.rsplit(".", 1)[0]
    return {"web_context": format_web_results(search_web(f"{query} 개념 사례", max_results=3), max_chars=400)}


def generate_quiz(state: QuizState) -> dict:
    attempts = state.get("attempts", 0) + 1
    progress.set_stage(state["session_id"], "generate", "" if attempts == 1 else f"형식을 보완해 다시 생성 중 ({attempts}/{MAX_ATTEMPTS})")
    feedback = ""
    if state.get("validation_error"):
        feedback = f"\n[이전 출력 오류 — 반드시 수정하세요]\n{state['validation_error']}"
    prompt = QUIZ_USER.format(
        context=state["context"],
        web_context=state.get("web_context") or "(없음)",
        num_mcq=state["num_mcq"],
        num_essay=state["num_essay"],
        total=state["num_mcq"] + state["num_essay"],
        difficulty=state["difficulty"],
        focus=state.get("focus_topic") or "자료 전체에서 고르게",
        feedback=feedback,
    )
    try:
        return {"raw_quiz": invoke_json(QUIZ_SYSTEM, prompt), "attempts": attempts, "validation_error": ""}
    except LLMOutputError as e:
        return {"raw_quiz": None, "attempts": attempts, "validation_error": str(e)}


def _shuffle_options(q: dict) -> dict:
    """LLM이 정답을 특정 위치에 몰아두는 편향을 없애기 위해 보기 순서를 섞습니다."""
    order = list(range(4))
    random.shuffle(order)
    return {**q, "options": [q["options"][i] for i in order], "answer_index": order.index(q["answer_index"])}


def validate_quiz(state: QuizState) -> dict:
    progress.set_stage(state["session_id"], "answers")
    if state.get("raw_quiz") is None:
        return {"questions": []}
    try:
        payload = QuizPayload.model_validate(state["raw_quiz"])
    except ValidationError as e:
        return {"questions": [], "validation_error": f"JSON 스키마 오류: {e.errors()[:3]}"}

    mcq = [q.model_dump() for q in payload.questions if q.type == "mcq"]
    essay = [q.model_dump() for q in payload.questions if q.type == "essay"]
    need_mcq, need_essay = state["num_mcq"], state["num_essay"]
    last_try = state["attempts"] >= MAX_ATTEMPTS

    if (len(mcq) < need_mcq or len(essay) < need_essay) and not last_try:
        return {
            "questions": [],
            "validation_error": f"객관식 {need_mcq}개/서술형 {need_essay}개가 필요한데 "
            f"객관식 {len(mcq)}개/서술형 {len(essay)}개가 생성되었습니다.",
        }
    questions = [_shuffle_options(q) for q in mcq[:need_mcq]] + essay[:need_essay]
    return {"questions": questions}


def route_after_validation(state: QuizState) -> str:
    if state.get("questions"):
        return END
    return "generate_quiz" if state.get("attempts", 0) < MAX_ATTEMPTS else END


def _build_graph():
    g = StateGraph(QuizState)
    g.add_node("retrieve_context", retrieve_context)
    g.add_node("web_enrich", web_enrich)
    g.add_node("generate_quiz", generate_quiz)
    g.add_node("validate_quiz", validate_quiz)

    g.add_edge(START, "retrieve_context")
    g.add_conditional_edges(
        "retrieve_context",
        lambda s: "web_enrich" if s.get("use_web") else "generate_quiz",
        ["web_enrich", "generate_quiz"],
    )
    g.add_edge("web_enrich", "generate_quiz")
    g.add_edge("generate_quiz", "validate_quiz")
    g.add_conditional_edges("validate_quiz", route_after_validation, ["generate_quiz", END])
    return g.compile()


quiz_graph = _build_graph()


def run_quiz_generation(
    session_id: str, num_questions: int, num_essay: int, difficulty: str, focus_topic: str, use_web: bool
) -> list[dict]:
    num_essay = min(num_essay, num_questions)
    final = quiz_graph.invoke(
        {
            "session_id": session_id,
            "num_mcq": num_questions - num_essay,
            "num_essay": num_essay,
            "difficulty": difficulty,
            "focus_topic": focus_topic,
            "use_web": use_web,
        }
    )
    if not final.get("questions"):
        raise QuizGenerationError(f"퀴즈 생성에 실패했습니다: {final.get('validation_error', '알 수 없는 오류')}")
    return final["questions"]
