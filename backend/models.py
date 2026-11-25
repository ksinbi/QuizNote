"""DB 테이블 정의.

- users              : 회원
- quiz_sessions      : 업로드한 PDF와 진행 중인 문제 세션 (새로고침/서버 재시작 후에도 이어서 풀기)
- study_records      : '웹 계정에 저장'한 학습 결과
- notion_connections : 사용자별 Notion OAuth 연결 (액세스 토큰은 암호화 저장)
"""
from datetime import datetime

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from backend.db import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(100), default="")
    password_hash: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class QuizSessionRow(Base):
    __tablename__ = "quiz_sessions"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    filename: Mapped[str] = mapped_column(String(255))
    file_size: Mapped[int] = mapped_column(Integer, default=0)
    num_pages: Mapped[int] = mapped_column(Integer)
    num_text_pages: Mapped[int] = mapped_column(Integer, default=0)
    chunks: Mapped[list] = mapped_column(JSON, default=list)  # [{"text", "page", "chunk_id"}]
    summary: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    settings: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # 문제 생성 설정
    questions: Mapped[list] = mapped_column(JSON, default=list)  # 정답 포함 전체 문항
    results: Mapped[dict] = mapped_column(JSON, default=dict)  # {"문항id": 채점 결과}
    tutor_log: Mapped[list] = mapped_column(JSON, default=list)  # AI 튜터 질문 · 답변 기록
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class StudyRecord(Base):
    __tablename__ = "study_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    session_id: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    filename: Mapped[str] = mapped_column(String(255))
    settings: Mapped[dict] = mapped_column(JSON, default=dict)
    questions: Mapped[list] = mapped_column(JSON, default=list)  # 문제 · 정답 · 해설 · 출처
    results: Mapped[dict] = mapped_column(JSON, default=dict)  # 사용자 답변 · 정오 결과
    tutor_log: Mapped[list] = mapped_column(JSON, default=list)  # AI 튜터 질문 · 답변 기록
    total: Mapped[int] = mapped_column(Integer, default=0)
    correct: Mapped[int] = mapped_column(Integer, default=0)
    wrong: Mapped[int] = mapped_column(Integer, default=0)
    accuracy: Mapped[float] = mapped_column(Float, default=0.0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class NotionConnection(Base):
    __tablename__ = "notion_connections"
    __table_args__ = (UniqueConstraint("user_id", "workspace_id", name="uq_notion_user_workspace"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    workspace_id: Mapped[str] = mapped_column(String(64))
    workspace_name: Mapped[str] = mapped_column(String(255), default="")
    workspace_icon: Mapped[str] = mapped_column(Text, default="")
    owner_name: Mapped[str] = mapped_column(String(255), default="")
    access_token_enc: Mapped[str] = mapped_column(Text)  # Fernet 암호화된 토큰
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class UserFlowState(Base):
    """프런트엔드 학습 진행 단계(업로드/설정/풀이 위치 등). 새로고침 후 이어서 진행하기 위해 저장."""

    __tablename__ = "user_flow_states"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    state: Mapped[dict] = mapped_column(JSON, default=dict)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
