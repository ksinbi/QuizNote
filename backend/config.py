"""환경 변수 기반 설정. 프로젝트 루트의 .env 파일을 읽습니다."""
import logging
import os
from pathlib import Path

from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parent.parent
load_dotenv(ROOT_DIR / ".env")

logger = logging.getLogger(__name__)


def _bool(name: str, default: str = "true") -> bool:
    return os.getenv(name, default).strip().lower() in {"1", "true", "yes", "y"}


class Settings:
    # LLM
    # OpenAI 키: OPENAI_API_KEY 또는 API_KEY 중 설정된 것을 사용
    openai_api_key: str = os.getenv("OPENAI_API_KEY") or os.getenv("API_KEY", "")
    llm_model: str = os.getenv("LLM_MODEL", "gpt-4o-mini")
    llm_max_tokens: int = int(os.getenv("LLM_MAX_TOKENS", "6000"))
    llm_temperature: float = float(os.getenv("LLM_TEMPERATURE", "0.3"))

    # 문서 처리 / RAG
    chunk_size: int = int(os.getenv("CHUNK_SIZE", "1000"))
    chunk_overlap: int = int(os.getenv("CHUNK_OVERLAP", "150"))
    use_embeddings: bool = _bool("USE_EMBEDDINGS", "true")
    embedding_model: str = os.getenv("EMBEDDING_MODEL", "jhgan/ko-sroberta-multitask")
    # macOS 일부 버전에서 MPS(애플 GPU) 사용 시 PyTorch가 강제 종료되므로 기본은 CPU
    embedding_device: str = os.getenv("EMBEDDING_DEVICE", "cpu")
    max_upload_mb: int = int(os.getenv("MAX_UPLOAD_MB", "30"))

    # 인터넷 검색 (TAVILY_API_KEY가 없으면 DuckDuckGo로 대체)
    tavily_api_key: str = os.getenv("TAVILY_API_KEY", "")

    # 데이터베이스: Docker에서는 PostgreSQL, 로컬 개발 시 미설정이면 SQLite 파일 사용
    database_url: str = os.getenv("DATABASE_URL", f"sqlite:///{ROOT_DIR / 'quiznote.db'}")

    # 인증(JWT)
    jwt_secret_key: str = os.getenv("JWT_SECRET_KEY", "")
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = int(os.getenv("JWT_EXPIRE_MINUTES", str(60 * 24 * 7)))

    # Notion 토큰 암호화 키(Fernet). 미설정 시 JWT_SECRET_KEY에서 파생
    encryption_key: str = os.getenv("ENCRYPTION_KEY", "")

    # Notion 로그인(OAuth, Public Integration)
    notion_client_id: str = os.getenv("NOTION_CLIENT_ID", "")
    notion_client_secret: str = os.getenv("NOTION_CLIENT_SECRET", "")
    notion_redirect_uri: str = os.getenv("NOTION_REDIRECT_URI", "http://localhost:8000/notion/oauth/callback")
    frontend_url: str = os.getenv("FRONTEND_URL", "http://localhost:8501")
    cors_origins: list[str] = [
        o.strip() for o in os.getenv("CORS_ORIGINS", "http://localhost:8501").split(",") if o.strip()
    ]

    # 채점 기준: 서술형 점수가 이 값 이상이면 정답 처리
    pass_score: int = int(os.getenv("PASS_SCORE", "70"))


settings = Settings()

if not settings.jwt_secret_key:
    # 개발 편의를 위한 기본값. 운영 환경에서는 반드시 .env에 JWT_SECRET_KEY를 설정하세요.
    logger.warning("JWT_SECRET_KEY가 설정되지 않아 개발용 기본 키를 사용합니다. 운영 환경에서는 반드시 설정하세요.")
    settings.jwt_secret_key = "dev-only-insecure-secret-change-me"
