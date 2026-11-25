"""Quiz Note 백엔드 (FastAPI)

실행: 프로젝트 루트에서  uvicorn backend.main:app --reload --port 8000
API 문서: http://localhost:8000/docs
"""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from backend.config import settings
from backend.db import init_db
from backend.routers import auth, notion, records, sessions
from backend.services import notion_oauth
from backend.services.session_store import SessionNotFound
from backend.services.web_search import search_provider

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    yield


app = FastAPI(
    title="Quiz Note API",
    version="2.0.0",
    description="PDF 기반 AI 문제 생성 · 채팅형 풀이 · 학습 기록 저장 · Notion 내보내기",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(SessionNotFound)
async def _not_found(_: Request, exc: SessionNotFound):
    return JSONResponse(status_code=404, content={"detail": str(exc.args[0]) if exc.args else "찾을 수 없습니다."})


@app.get("/health")
def health():
    return {
        "status": "ok",
        "model": settings.llm_model,
        "llm_key_configured": bool(settings.openai_api_key),
        "web_search": search_provider(),
        "notion_oauth": notion_oauth.is_configured(),
        "database": settings.database_url.split(":", 1)[0],
    }


app.include_router(auth.router)
app.include_router(sessions.router)
app.include_router(records.router)
app.include_router(notion.router)
