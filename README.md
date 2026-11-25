# 🎓 Quiz Note
**PDF 기반 AI 문제 생성 및 채팅형 학습 서비스**

PDF를 업로드하면 AI가 문서를 분석해 원하는 조건(문제 수 · 서술형 수 · 난이도 · 정답/해설/출처 표시)에 맞는 문제를 만들고,
채팅 화면에서 한 문제씩 풀며 즉시 채점과 해설을 확인합니다. 학습 결과는 **웹 계정(DB)** 에 저장하거나 **개인 Notion** 으로 내보낼 수 있습니다.

---

## 1. 사용자 플로우

| STEP | 화면 | 구현 |
|---|---|---|
| 1 | PDF 업로드 | 드래그 앤 드롭, 파일 정보, 미리보기, 삭제/재업로드, PyMuPDF 텍스트 추출 |
| 2 | 조건 설정 | 전체/서술형 문항 수(유효성 검사), 난이도, 정답 표시 · 해설 · 원문 출처 토글 |
| 3 | 문제 생성 | 백그라운드 작업 + 단계별 진행 화면 (추출 → 분석 → 생성 → 정답·해설 검증 → 출처 연결) |
| 4 | 채팅형 풀이 | AI 말풍선으로 1문제씩, 객관식 버튼 / 서술형 입력창, 진행 바, 💡 힌트 |
| 5 | 정답/오답 | 초록/빨강 구분, 내 답변 vs 정답 비교, 해설, PDF 페이지 + 원문 발췌, 다음 문제 버튼 |
| 6 | 학습 완료 | 전체 · 정답 · 오답 · 정답률, 문제별 결과, 복습 개념 |
| 7 | 저장 | **A. Notion** (OAuth 팝업 → 워크스페이스/페이지 선택 → 제목 · 항목 선택 → 내보내기) / **B. 웹 계정** |
| 8 | 다음 | 새로운 문제 생성(업로드 화면으로) / 종료 |

새로고침해도 로그인과 진행 단계가 유지됩니다 (로그인 토큰은 쿠키, 학습 진행 단계·문제·채점 결과는 DB).

---

## 2. 기술 스택 & 구조

| 영역 | 기술 |
|---|---|
| Frontend | **Streamlit** (Python) — `st.chat_message` 채팅 UI, `st.dialog` 단계별 모달, `st.fragment` 실시간 진행 표시 |
| Backend | Python + FastAPI |
| PDF | PyMuPDF |
| AI | OpenAI LLM + LangChain/LangGraph (출제 · 채점 그래프, 튜터 에이전트), BM25 + 벡터 하이브리드 RAG |
| DB | PostgreSQL (로컬 개발 시 SQLite 자동 대체) + SQLAlchemy |
| 인증 | JWT(이메일/비밀번호) · Notion OAuth |
| 배포 | Docker Compose (db · backend · frontend/nginx) |

```
AI_PROJECT/
├── backend/
│   ├── main.py                 # 앱 생성 · 라우터 등록
│   ├── config.py · db.py       # 설정 · DB 엔진
│   ├── models.py               # users / quiz_sessions / study_records / notion_connections
│   ├── security.py             # JWT · bcrypt · Notion 토큰 암호화(Fernet)
│   ├── schemas.py              # 요청/응답 · LLM 출력 검증
│   ├── routers/                # auth · sessions · records · notion
│   ├── graphs/                 # LangGraph 출제/채점, 튜터 에이전트
│   ├── services/               # pdf_processor(PyMuPDF) · session_store(DB) · progress · notion_* · vector_store · llm
│   ├── prompts/templates.py
│   └── Dockerfile
├── frontend/                   # Streamlit
│   ├── app.py                  # 진입점: 로그인 확인 · 상단 바 · 단계별 화면 전환
│   ├── api_client.py           # 백엔드 호출 (UI와 분리)
│   ├── state.py                # 세션 상태 · 로그인 쿠키 · 학습 진행 단계(DB 저장)
│   ├── views/                  # auth · setup(업로드+설정) · generating · quiz · summary · notion_dialog · notion_page · done · history
│   ├── components/ui.py        # 단계 표시 · 문제/채점 카드 · 통계 카드
│   ├── assets/style.css · .streamlit/config.toml
│   └── Dockerfile
├── docker-compose.yml
├── .env.example
└── run.sh                      # 로컬 개발: 백엔드 + 프런트 동시 실행
```

---

## 3. 실행 방법

### 3-1. 환경 변수
`.env.example`을 참고해 `.env`를 작성합니다. 필수: `API_KEY`, `JWT_SECRET_KEY`, `ENCRYPTION_KEY`
(Notion 저장을 쓰려면 `NOTION_CLIENT_ID` / `NOTION_CLIENT_SECRET`도 필요)

### 3-2. 로컬 개발
```bash
python3 -m venv .venv && .venv/bin/python -m pip install -r requirements.txt
./run.sh
```
- 앱: http://localhost:8501
- API 문서: http://localhost:8000/docs
- `DATABASE_URL`이 없으면 `quiznote.db`(SQLite)를 사용합니다.

> 벡터 검색용 `sentence-transformers`는 용량이 큽니다. 부담되면 `.env`에 `USE_EMBEDDINGS=false` → BM25 키워드 검색만 사용합니다.

### 3-3. Docker (PostgreSQL 포함)
```bash
docker compose up --build
```
- 앱: http://localhost:8501 · API: http://localhost:8000

---

## 4. Notion 연동 (OAuth)

1. https://www.notion.so/profile/integrations 에서 **Public** 통합 생성
2. Redirect URI: `http://localhost:8000/notion/oauth/callback`
3. Capabilities: 콘텐츠 읽기 · 콘텐츠 삽입
4. 발급된 **OAuth client ID(UUID 형식) / client secret**을 `.env`의 `NOTION_CLIENT_ID` / `NOTION_CLIENT_SECRET`에 입력

사용자 흐름: 결과 화면 → **Notion으로 저장**(모달) → **Notion 연결** → 새 창에서 로그인 · 권한 승인 · 페이지 공유 → 앱으로 돌아와 **연결 확인** → 워크스페이스/페이지 선택 → 제목 입력 · 항목 선택 → 내보내기

- 액세스 토큰은 프런트엔드로 전달되지 않고, 서버 DB에 **Fernet 암호화**되어 사용자 계정에 연결됩니다.
- `state` 값으로 CSRF를 방지하며, 대기 중인 연결 요청은 10분 후 만료됩니다.
- 내보내기 항목: PDF 파일명 · 전체 문제 · 정답 · 해설 · 사용자 답변 · 정답/오답 결과 · 원문 출처 · 최종 학습 통계 · AI 튜터 질문 기록

---

## 5. API 요약

| Method | Path | 설명 |
|---|---|---|
| POST | `/auth/register` · `/auth/login` | 회원가입 · 로그인 (JWT 발급) |
| GET | `/auth/me` | 내 정보 |
| GET/PUT | `/auth/me/flow` | 학습 진행 단계 저장 · 복원 (새로고침 대응) |
| POST | `/sessions` | PDF 업로드 → 추출 · 청킹 · 인덱싱 |
| GET | `/sessions/{id}` | 세션 상태 (새로고침 복원용, 정답 제외) |
| POST | `/sessions/{id}/quiz` | 문제 생성 작업 시작 (202) |
| POST | `/sessions/{id}/quiz/cancel` | 문제 생성 취소 (결과 저장 안 함, 바로 다시 생성 가능) |
| GET | `/sessions/{id}/progress` | 생성 진행 단계 |
| POST | `/sessions/{id}/answer` | 채점 (객관식 판정 / 서술형 의미 기반 AI 채점) |
| POST | `/sessions/{id}/chat` | AI 튜터 (힌트) |
| GET | `/sessions/{id}/report` | 학습 통계 · 문제별 결과 |
| POST/GET/DELETE | `/records` · `/records/{id}` | 웹 계정 학습 기록 저장 · 조회 · 삭제 |
| GET | `/notion/status` | OAuth 설정 여부 · 연결된 워크스페이스 |
| POST | `/notion/oauth/start` | Notion 인증 URL 발급 |
| GET | `/notion/oauth/callback` | Notion 리다이렉트 (토큰 암호화 저장) |
| GET | `/notion/connections/{id}/pages` | 공유된 페이지 목록 |
| DELETE | `/notion/connections/{id}` | 연결 해제 |
| POST | `/notion/export` | 세션 또는 학습 기록을 Notion 페이지로 내보내기 |

모든 학습 데이터는 `user_id`로 분리되며, 다른 사용자의 세션/기록에 접근하면 404를 반환합니다.
