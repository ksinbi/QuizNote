"""LangGraph: 채점 & 피드백 워크플로우

START → retrieve_evidence ─┬─(객관식)→ check_mcq ──┐
                           └─(서술형)→ grade_essay ─┤
                                                    ├─(정답)──────────────────────→ END
                                                    ├─(오답 & use_web)→ web_supplement → supplement → END
                                                    └─(오답)──────────────────────→ supplement → END
"""
import json
from typing import TypedDict

from langgraph.graph import END, START, StateGraph

from backend.config import settings
from backend.prompts.templates import GRADE_SYSTEM, GRADE_USER, SUPPLEMENT_SYSTEM, SUPPLEMENT_USER
from backend.services.llm import LLMOutputError, invoke_json, invoke_text
from backend.services.session_store import store
from backend.services.vector_store import format_docs
from backend.services.web_search import format_web_results, search_web
from backend.tools import grade_multiple_choice


class GradeState(TypedDict, total=False):
    session_id: str
    question: dict
    user_answer: str
    use_web: bool
    evidence: str
    evidence_pages: list[int]
    web_context: str
    web_refs: list[str]
    result: dict


def retrieve_evidence(state: GradeState) -> dict:
    session = store.get(state["session_id"])
    q = state["question"]
    docs = session.retriever.search(f"{q.get('concept', '')} {q['question']}", k=3)
    pages = sorted({d.metadata.get("page") for d in docs if d.metadata.get("page")})
    return {"evidence": format_docs(docs, max_chars=6000), "evidence_pages": pages}


def route_by_type(state: GradeState) -> str:
    return "check_mcq" if state["question"]["type"] == "mcq" else "grade_essay"


def check_mcq(state: GradeState) -> dict:
    q = state["question"]
    verdict = json.loads(
        grade_multiple_choice.invoke(
            {"user_answer": state["user_answer"], "options": q["options"], "answer_index": q["answer_index"]}
        )
    )
    if not verdict["is_valid"]:
        feedback = "답을 해석하지 못했어요. 1~4 중 번호로 답해주세요. 이번 문항은 오답으로 처리했어요."
    else:
        feedback = "정답이에요! 🎉" if verdict["is_correct"] else "아쉽지만 오답이에요."
    return {
        "result": {
            "is_correct": verdict["is_correct"],
            "score": 100 if verdict["is_correct"] else 0,
            "verdict": "correct" if verdict["is_correct"] else "incorrect",
            "user_answer": state["user_answer"],
            "correct_answer": verdict["correct_answer"],
            "feedback": feedback,
            "missing_points": [],
            "explanation": q.get("explanation", ""),
        }
    }


def grade_essay(state: GradeState) -> dict:
    q = state["question"]
    prompt = GRADE_USER.format(
        question=q["question"],
        model_answer=q["model_answer"],
        key_points="\n".join(f"- {p}" for p in q["key_points"]),
        evidence=state["evidence"],
        user_answer=state["user_answer"],
    )
    try:
        graded = invoke_json(GRADE_SYSTEM, prompt, max_tokens=4000)
        score = max(0, min(100, int(graded.get("score", 0))))
    except (LLMOutputError, ValueError, TypeError):
        graded, score = {"feedback": "채점 중 오류가 발생해 모범 답안을 함께 보여드려요."}, 0
    return {
        "result": {
            "is_correct": score >= settings.pass_score,
            "score": score,
            "verdict": graded.get("verdict", "incorrect"),
            "user_answer": state["user_answer"],
            "correct_answer": q["model_answer"],
            "matched_points": graded.get("matched_points", []),
            "missing_points": graded.get("missing_points", []),
            "feedback": graded.get("feedback", ""),
            "improved_answer": graded.get("improved_answer", ""),
            "explanation": q.get("explanation") or q["model_answer"],
        }
    }


def route_after_grading(state: GradeState) -> str:
    if state["result"]["is_correct"]:
        return END
    return "web_supplement" if state.get("use_web") else "supplement"


def web_supplement(state: GradeState) -> dict:
    q = state["question"]
    results = search_web(f"{q.get('concept') or q['question'][:40]} 설명", max_results=3)
    return {
        "web_context": format_web_results(results, max_chars=500),
        "web_refs": [f"{r['title']} - {r['url']}" for r in results if r.get("url")],
    }


def supplement(state: GradeState) -> dict:
    q, r = state["question"], state["result"]
    prompt = SUPPLEMENT_USER.format(
        question=q["question"],
        correct_answer=r["correct_answer"],
        user_answer=r["user_answer"],
        missing=", ".join(r.get("missing_points", [])) or "정답 선택 실패",
        evidence=state["evidence"],
        web_context=state.get("web_context") or "(없음)",
    )
    try:
        text = invoke_text(SUPPLEMENT_SYSTEM, prompt, max_tokens=3000)
    except LLMOutputError:
        text = ""
    return {"result": {**r, "supplement": text}}


def _build_graph():
    g = StateGraph(GradeState)
    g.add_node("retrieve_evidence", retrieve_evidence)
    g.add_node("check_mcq", check_mcq)
    g.add_node("grade_essay", grade_essay)
    g.add_node("web_supplement", web_supplement)
    g.add_node("supplement", supplement)

    g.add_edge(START, "retrieve_evidence")
    g.add_conditional_edges("retrieve_evidence", route_by_type, ["check_mcq", "grade_essay"])
    for node in ("check_mcq", "grade_essay"):
        g.add_conditional_edges(node, route_after_grading, ["web_supplement", "supplement", END])
    g.add_edge("web_supplement", "supplement")
    g.add_edge("supplement", END)
    return g.compile()


grading_graph = _build_graph()


def run_grading(session, question_id: int, user_answer: str, use_web: bool) -> dict:
    question = session.get_question(question_id)
    final = grading_graph.invoke(
        {"session_id": session.id, "question": question, "user_answer": user_answer, "use_web": use_web}
    )
    result = {
        **final["result"],
        "question_id": question_id,
        "source_page": question.get("source_page"),
        "source_quote": question.get("source_quote", ""),
        "evidence_pages": final.get("evidence_pages", []),
        "references": final.get("web_refs", []),
    }
    store.save_result(session.id, question_id, result)
    return result
