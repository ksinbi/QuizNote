"""RAG 검색기: BM25(키워드) + 벡터(의미) 하이브리드 검색, Reciprocal Rank Fusion으로 결합.

- 임베딩 모델(sentence-transformers)이 설치되어 있으면 hybrid 모드
- 설치되지 않았거나 로드 실패 시 BM25 단독 모드로 자동 전환 (외부 API 없이 동작)
"""
import logging
import re
from functools import lru_cache

from langchain_core.documents import Document
from rank_bm25 import BM25Okapi

from backend.config import settings

logger = logging.getLogger(__name__)

_TOKEN_RE = re.compile(r"[가-힣]+|[A-Za-z]+|\d+")
_RRF_K = 60


def tokenize(text: str) -> list[str]:
    """한국어/영어 혼합 토크나이저. 한글 어절은 조사 영향을 줄이기 위해 2-gram도 함께 사용."""
    tokens: list[str] = []
    for tok in _TOKEN_RE.findall(text.lower()):
        tokens.append(tok)
        if "가" <= tok[0] <= "힣" and len(tok) > 2:
            tokens.extend(tok[i : i + 2] for i in range(len(tok) - 1))
    return tokens


@lru_cache(maxsize=1)
def _load_embeddings():
    from langchain_huggingface import HuggingFaceEmbeddings

    return HuggingFaceEmbeddings(
        model_name=settings.embedding_model,
        model_kwargs={"device": settings.embedding_device},
        encode_kwargs={"normalize_embeddings": True},
    )


def format_docs(docs: list[Document], max_chars: int | None = None) -> str:
    """검색 결과를 '[p.3] 본문' 형식의 문자열로 변환 (LLM 프롬프트/도구 출력용)."""
    parts = [f"[p.{d.metadata.get('page', '?')}] {d.page_content}" for d in docs]
    text = "\n\n---\n\n".join(parts)
    return text[:max_chars] if max_chars else text


class LectureRetriever:
    def __init__(self, chunks: list[Document]):
        if not chunks:
            raise ValueError("검색할 청크가 없습니다.")
        self.chunks = chunks
        self._bm25 = BM25Okapi([tokenize(c.page_content) or ["_"] for c in chunks])
        self._vector_store = None
        self.mode = "bm25"

        if settings.use_embeddings:
            try:
                from langchain_core.vectorstores import InMemoryVectorStore

                self._vector_store = InMemoryVectorStore.from_documents(chunks, _load_embeddings())
                self.mode = "hybrid"
            except Exception as e:  # 패키지 미설치, 모델 다운로드 실패 등
                logger.warning("임베딩 검색 비활성화 → BM25 키워드 검색만 사용합니다: %s", e)

    def search(self, query: str, k: int = 4) -> list[Document]:
        k = max(1, min(k, len(self.chunks)))
        scores = self._bm25.get_scores(tokenize(query))
        bm25_ranked = sorted(range(len(self.chunks)), key=lambda i: scores[i], reverse=True)[: k * 2]
        if self._vector_store is None:
            return [self.chunks[i] for i in bm25_ranked[:k]]

        vector_docs = self._vector_store.similarity_search(query, k=k * 2)
        fused: dict[int, float] = {}
        for rank, idx in enumerate(bm25_ranked):
            fused[idx] = fused.get(idx, 0.0) + 1 / (_RRF_K + rank)
        for rank, doc in enumerate(vector_docs):
            idx = doc.metadata["chunk_id"]
            fused[idx] = fused.get(idx, 0.0) + 1 / (_RRF_K + rank)
        best = sorted(fused, key=fused.get, reverse=True)[:k]
        return [self.chunks[i] for i in best]

    def sample_diverse(self, n: int) -> list[Document]:
        """문서 전체를 고르게 커버하도록 균등 간격으로 청크를 뽑습니다. (주제 미지정 출제용)"""
        total = len(self.chunks)
        if n >= total:
            return list(self.chunks)
        if n == 1:
            return [self.chunks[total // 2]]
        idxs = sorted({round(i * (total - 1) / (n - 1)) for i in range(n)})
        return [self.chunks[i] for i in idxs]
