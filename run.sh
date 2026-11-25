#!/usr/bin/env bash
# 로컬 개발: 백엔드(FastAPI :8000)와 프런트엔드(Streamlit :8501)를 함께 실행합니다.
# DATABASE_URL이 없으면 SQLite(quiznote.db)를 사용합니다. PostgreSQL은 docker compose로 실행하세요.
set -e
cd "$(dirname "$0")"
ROOT="$(pwd)"
PY="$ROOT/.venv/bin/python"

if [ ! -x "$PY" ]; then
  echo "❌ .venv가 없습니다. 먼저 설치하세요:"
  echo "   python3 -m venv .venv && .venv/bin/python -m pip install -r requirements.txt"
  exit 1
fi

"$PY" -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 --reload --reload-dir backend &
BACKEND_PID=$!
trap 'kill $BACKEND_PID 2>/dev/null' EXIT

cd frontend
"$PY" -m streamlit run app.py --server.port 8501
