"""자체 구현 Tool 모음 (LangChain @tool).

| Tool                     | 역할                                         |
|--------------------------|----------------------------------------------|
| search_lecture_notes     | 업로드한 PDF에서 관련 내용 검색 (RAG)        |
| web_search               | 인터넷 검색으로 최신/보충 정보 수집          |
| grade_multiple_choice    | 객관식 답안 판정 (번호·기호·보기 텍스트 인식) |
| get_quiz_progress        | 현재 점수 · 오답 · 약점 개념 조회            |

세션에 의존하는 Tool은 make_* 팩토리로 세션을 바인딩해서 생성합니다.
"""
import json
import re

from langchain_core.tools import BaseTool, tool

from backend.services.session_store import QuizSession
from backend.services.vector_store import format_docs
from backend.services.web_search import format_web_results, search_web

_CIRCLED = {"①": 1, "②": 2, "③": 3, "④": 4}


# ---------- 세션 독립 Tool ----------
@tool
def web_search(query: str) -> str:
    """인터넷에서 정보를 검색합니다. 강의 자료에 없는 최신 동향, 실제 사례, 추가 예시가 필요할 때 사용하세요."""
    results = search_web(query, max_results=4)
    return format_web_results(results) or "검색 결과가 없습니다."


def parse_choice(user_answer: str, options: list[str]) -> int | None:
    """'2', '2번', '②', 'B', 보기 텍스트 등을 0-based 인덱스로 변환. 해석 불가하면 None."""
    text = user_answer.strip()
    for sym, num in _CIRCLED.items():
        if sym in text:
            return num - 1
    m = re.search(r"\b([1-4])\b|^([1-4])번?", text)
    if m:
        return int(m.group(1) or m.group(2)) - 1
    m = re.fullmatch(r"\(?([A-Da-d])\)?\.?", text)
    if m:
        return ord(m.group(1).upper()) - ord("A")
    normalized = re.sub(r"\s+", "", text)
    for i, opt in enumerate(options):
        if normalized and normalized == re.sub(r"\s+", "", opt):
            return i
    return None


@tool
def grade_multiple_choice(user_answer: str, options: list[str], answer_index: int) -> str:
    """객관식 답안을 판정합니다. user_answer는 번호(1~4), 기호(①~④), 보기 텍스트 모두 가능합니다.
    answer_index는 0부터 시작하는 정답 보기 인덱스입니다. 결과를 JSON 문자열로 반환합니다."""
    idx = parse_choice(user_answer, options)
    return json.dumps(
        {
            "user_choice": idx,
            "is_valid": idx is not None,
            "is_correct": idx == answer_index,
            "correct_answer": f"{answer_index + 1}번. {options[answer_index]}",
        },
        ensure_ascii=False,
    )


# ---------- 세션 바인딩 Tool ----------
def make_search_lecture_notes(session: QuizSession) -> BaseTool:
    @tool("search_lecture_notes")
    def search_lecture_notes(query: str) -> str:
        """업로드한 강의 PDF에서 질문과 관련된 내용을 검색합니다(RAG).
        강의 개념·정의·설명·문제 근거를 찾을 때 가장 먼저 사용하세요. 결과에는 [p.페이지] 표시가 붙습니다."""
        docs = session.retriever.search(query, k=4)
        return format_docs(docs) or "관련 내용을 찾지 못했습니다."

    return search_lecture_notes


def make_get_quiz_progress(session: QuizSession) -> BaseTool:
    @tool("get_quiz_progress")
    def get_quiz_progress() -> str:
        """현재 퀴즈 진행 상황(점수, 맞힌/틀린 문항, 복습이 필요한 개념)을 조회합니다."""
        rep = session.report()
        wrong = [
            {"문항": i["question_id"], "문제": i["question"], "개념": i["concept"], "점수": i["score"], "정답": i["correct_answer"]}
            for i in rep["items"]
            if i["answered"] and not i["is_correct"]
        ]
        summary = {k: rep[k] for k in ("total", "answered", "correct", "average_score", "weak_concepts")}
        return json.dumps({**summary, "wrong": wrong}, ensure_ascii=False)

    return get_quiz_progress


def build_tutor_tools(session: QuizSession, use_web: bool = True) -> list[BaseTool]:
    tools: list[BaseTool] = [
        make_search_lecture_notes(session),
        make_get_quiz_progress(session),
    ]
    if use_web:
        tools.append(web_search)
    return tools
