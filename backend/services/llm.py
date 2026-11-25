"""LangChain ChatOpenAI 래퍼와 JSON 응답 파싱 유틸."""
import json
import re
from functools import lru_cache

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from backend.config import settings


class LLMOutputError(Exception):
    """LLM 응답을 해석할 수 없을 때 발생."""


@lru_cache(maxsize=4)
def get_llm(max_tokens: int | None = None) -> ChatOpenAI:
    return ChatOpenAI(
        model=settings.llm_model,
        api_key=settings.openai_api_key or None,
        temperature=settings.llm_temperature,
        max_tokens=max_tokens or settings.llm_max_tokens,
        timeout=120,
        max_retries=2,
    )


def message_text(message) -> str:
    """AIMessage에서 텍스트만 추출. (list 형태 content도 처리)"""
    content = getattr(message, "content", message)
    if isinstance(content, str):
        return content
    parts = []
    for block in content:
        if isinstance(block, str):
            parts.append(block)
        elif isinstance(block, dict) and block.get("type") == "text":
            parts.append(block.get("text", ""))
    return "".join(parts)


def extract_json(text: str) -> dict:
    fenced = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    candidate = fenced.group(1) if fenced else text
    start, end = candidate.find("{"), candidate.rfind("}")
    if start == -1 or end == -1:
        raise LLMOutputError("응답에서 JSON을 찾을 수 없습니다.")
    try:
        return json.loads(candidate[start : end + 1])
    except json.JSONDecodeError as e:
        raise LLMOutputError(f"JSON 파싱 실패: {e}") from e


def _check_finish(response) -> None:
    reason = response.response_metadata.get("finish_reason")
    if reason == "content_filter":
        raise LLMOutputError("콘텐츠 필터에 의해 응답이 차단되었습니다.")
    if getattr(response, "additional_kwargs", {}).get("refusal"):
        raise LLMOutputError("모델이 요청 처리를 거절했습니다.")


def invoke_text(system: str, user: str, max_tokens: int | None = None) -> str:
    response = get_llm(max_tokens).invoke([SystemMessage(content=system), HumanMessage(content=user)])
    _check_finish(response)
    return message_text(response)


def invoke_json(system: str, user: str, max_tokens: int | None = None) -> dict:
    # OpenAI JSON 모드: 항상 유효한 JSON 객체만 출력하도록 강제 (프롬프트에 'JSON' 단어 포함 필요)
    llm = get_llm(max_tokens).bind(response_format={"type": "json_object"})
    response = llm.invoke([SystemMessage(content=system), HumanMessage(content=user)])
    _check_finish(response)
    if response.response_metadata.get("finish_reason") == "length":
        raise LLMOutputError("응답이 너무 길어 잘렸습니다. LLM_MAX_TOKENS를 늘려주세요.")
    return extract_json(message_text(response))
