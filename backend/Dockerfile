FROM python:3.12-slim
WORKDIR /app
COPY backend/requirements.txt backend/requirements.txt
# GPU용 PyTorch(수 GB) 대신 CPU 버전을 먼저 설치 → 이미지 크기 · 설치 시간 대폭 감소
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu
RUN pip install --no-cache-dir -r backend/requirements.txt
COPY backend backend
EXPOSE 8000
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
