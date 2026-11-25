"""사용자에게 보여줄 오류 메시지 변환."""
import openai

from backend.services.llm import LLMOutputError


def friendly_llm_error(exc: Exception) -> str:
    if isinstance(exc, openai.AuthenticationError):
        return "AI 서비스 키가 올바르지 않습니다. 관리자에게 문의하세요. (.env의 API_KEY 확인)"
    if isinstance(exc, openai.RateLimitError):
        if "insufficient_quota" in str(exc):
            return "AI 서비스 사용 한도가 부족합니다. 잠시 후 다시 시도하거나 관리자에게 문의하세요."
        return "요청이 많아 잠시 후 다시 시도해주세요."
    if isinstance(exc, openai.APITimeoutError):
        return "AI 응답 시간이 초과되었습니다. 문제 수를 줄이거나 다시 시도해주세요."
    if isinstance(exc, openai.APIError):
        return "AI 서비스 호출 중 오류가 발생했습니다. 잠시 후 다시 시도해주세요."
    if isinstance(exc, LLMOutputError):
        return f"AI 응답을 처리하지 못했습니다: {exc}"
    return f"처리 중 오류가 발생했습니다: {exc}"
