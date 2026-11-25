"""인터넷 검색. TAVILY_API_KEY가 있으면 Tavily, 없으면 DuckDuckGo(무료, 키 불필요)를 사용합니다."""
import logging

from backend.config import settings

logger = logging.getLogger(__name__)


def search_provider() -> str:
    return "tavily" if settings.tavily_api_key else "duckduckgo"


def search_web(query: str, max_results: int = 4) -> list[dict]:
    """[{title, url, content}] 형식의 결과를 반환합니다. 실패하면 빈 리스트."""
    try:
        if settings.tavily_api_key:
            from tavily import TavilyClient

            response = TavilyClient(api_key=settings.tavily_api_key).search(query=query, max_results=max_results)
            return [
                {"title": r.get("title", ""), "url": r.get("url", ""), "content": r.get("content", "")}
                for r in response.get("results", [])
            ]

        from ddgs import DDGS

        results = DDGS().text(query, max_results=max_results, region="kr-kr")
        return [
            {"title": r.get("title", ""), "url": r.get("href", ""), "content": r.get("body", "")}
            for r in results or []
        ]
    except Exception as e:  # 네트워크/쿼터 오류가 퀴즈 흐름 전체를 막지 않도록
        logger.warning("웹 검색 실패(%s): %s", search_provider(), e)
        return []


def format_web_results(results: list[dict], max_chars: int = 600) -> str:
    if not results:
        return ""
    return "\n\n".join(
        f"[웹{i}] {r['title']} ({r['url']})\n{r['content'][:max_chars]}" for i, r in enumerate(results, start=1)
    )
