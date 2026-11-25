"""LangChain Agent(LangGraph 기반 ReAct 루프): 자유 질문 · 힌트 · 노션 저장 요청을 처리하는 AI 튜터.

사용자 입력에 따라 에이전트가 스스로 도구를 고릅니다.
  "이 개념 다시 설명해줘"  → search_lecture_notes
  "요즘 실제로 어디에 쓰여?" → web_search
  "내가 뭘 많이 틀렸어?"    → get_quiz_progress
"""
from langchain.agents import create_agent
from langchain_core.messages import AIMessage, HumanMessage

from backend.prompts.templates import TUTOR_SYSTEM
from backend.services.llm import get_llm, message_text
from backend.services.session_store import QuizSession
from backend.tools import build_tutor_tools

HISTORY_TURNS = 6  # 최근 6턴(질문+답변)만 맥락으로 전달 (대화 기록은 세션 DB의 tutor_log)


def _describe_current_question(session: QuizSession, question_id: int | None) -> str:
    if question_id is None:
        return "현재 풀고 있는 문제 없음"
    try:
        q = session.get_question(question_id)
    except KeyError:
        return "현재 풀고 있는 문제 없음"
    lines = [f"Q{q['id']} ({'객관식' if q['type'] == 'mcq' else '서술형'}): {q['question']}"]
    if q["type"] == "mcq":
        lines += [f"  {i + 1}. {opt}" for i, opt in enumerate(q["options"])]
    result = session.results.get(question_id)
    if result is None:
        lines.append("상태: 아직 채점 전 → 정답을 알려주지 말고 힌트만 주세요.")
    else:
        lines.append(f"상태: 채점 완료 ({result['score']}점). 정답: {result['correct_answer']}")
    return "\n".join(lines)


def chat_with_tutor(
    session: QuizSession,
    message: str,
    current_question_id: int | None = None,
    use_web: bool = False,
) -> dict:
    tools = build_tutor_tools(session, use_web)
    agent = create_agent(
        model=get_llm(),
        tools=tools,
        system_prompt=TUTOR_SYSTEM.format(
            filename=session.filename,
            current_question=_describe_current_question(session, current_question_id),
        ),
    )

    history = []
    for e in session.tutor_log[-HISTORY_TURNS:]:
        history += [HumanMessage(content=e["message"]), AIMessage(content=e["reply"])]
    inputs = history + [HumanMessage(content=message)]

    state = agent.invoke({"messages": inputs})
    new_messages = state["messages"][len(inputs) :]
    reply = message_text(state["messages"][-1]).strip() or "죄송해요, 답변을 만들지 못했어요. 다시 질문해주세요."
    tools_used = [
        call["name"] for m in new_messages if isinstance(m, AIMessage) for call in (m.tool_calls or [])
    ]
    return {"reply": reply, "tools_used": tools_used}
