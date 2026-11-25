"""SQLAlchemy 엔진/세션. DATABASE_URL로 PostgreSQL(운영) 또는 SQLite(로컬 개발)를 사용합니다."""
from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from backend.config import settings

_is_sqlite = settings.database_url.startswith("sqlite")

engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,
    connect_args={"check_same_thread": False} if _is_sqlite else {},
)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def get_db() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    from backend import models  # noqa: F401  (테이블 등록)

    Base.metadata.create_all(bind=engine)
    _add_missing_columns()


# 기존 DB에 나중에 추가된 컬럼 (create_all은 이미 있는 테이블에 컬럼을 추가하지 않음)
_ADDED_COLUMNS = {
    "quiz_sessions": {"tutor_log": "JSON"},
    "study_records": {"tutor_log": "JSON"},
}


def _add_missing_columns() -> None:
    from sqlalchemy import inspect, text

    insp = inspect(engine)
    with engine.begin() as conn:
        for table, columns in _ADDED_COLUMNS.items():
            existing = {c["name"] for c in insp.get_columns(table)}
            for name, sql_type in columns.items():
                if name not in existing:
                    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {sql_type}"))


def as_utc(dt):
    """DB에서 읽은 시각을 timezone-aware(UTC)로. (SQLite는 시간대 정보를 저장하지 않음)"""
    from datetime import timezone

    if dt is None:
        return None
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt


def iso(dt) -> str | None:
    dt = as_utc(dt)
    return dt.isoformat() if dt else None
