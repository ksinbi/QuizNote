"""퀴즈 데이터 모델(LLM 출력 검증용)과 API 요청/응답 스키마."""
from typing import Annotated, Literal, Union

from pydantic import BaseModel, EmailStr, Field, model_validator

MAX_QUESTIONS = 20


# ---------- LLM이 생성한 퀴즈 검증용 ----------
class MCQuestion(BaseModel):
    type: Literal["mcq"]
    question: str = Field(min_length=5)
    options: list[str] = Field(min_length=4, max_length=4)
    answer_index: int = Field(ge=0, le=3)
    explanation: str
    concept: str = ""
    source_page: int | None = None
    source_quote: str = ""


class EssayQuestion(BaseModel):
    type: Literal["essay"]
    question: str = Field(min_length=5)
    model_answer: str
    key_points: list[str] = Field(min_length=1)
    explanation: str = ""
    concept: str = ""
    source_page: int | None = None
    source_quote: str = ""


Question = Annotated[Union[MCQuestion, EssayQuestion], Field(discriminator="type")]


class QuizPayload(BaseModel):
    questions: list[Question]


# ---------- 인증 ----------
class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    name: str = Field("", max_length=100)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class UserOut(BaseModel):
    id: int
    email: str
    name: str


class FlowStateBody(BaseModel):
    state: dict


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


# ---------- 문제 세션 ----------
class UploadResponse(BaseModel):
    session_id: str
    filename: str
    file_size: int
    num_pages: int
    num_text_pages: int
    num_chunks: int
    num_chars: int
    retriever_mode: str


class QuizSettings(BaseModel):
    """STEP 2. 문제 생성 조건"""

    num_questions: int = Field(5, ge=1, le=MAX_QUESTIONS)
    num_essay: int = Field(1, ge=0, le=MAX_QUESTIONS)
    difficulty: Literal["쉬움", "보통", "어려움"] = "보통"
    show_answer: bool = True
    show_explanation: bool = True
    show_source: bool = True
    focus_topic: str = Field("", max_length=200)
    use_web: bool = False

    @model_validator(mode="after")
    def _check_counts(self):
        if self.num_essay > self.num_questions:
            raise ValueError("서술형 문항 수는 전체 문제 수보다 많을 수 없습니다.")
        return self


class AnswerRequest(BaseModel):
    question_id: int
    answer: str = Field(min_length=1, max_length=5000)


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=3000)
    current_question_id: int | None = None
    use_web: bool = False
    label: str | None = Field(default=None, max_length=200)  # 화면에 보여줄 질문 문구 (힌트 버튼 등)


# ---------- 학습 기록 ----------
class SaveRecordRequest(BaseModel):
    session_id: str


# ---------- Notion ----------
ExportItem = Literal[
    "filename", "questions", "answers", "explanations", "user_answers", "results", "sources", "stats", "tutor"
]
ALL_EXPORT_ITEMS: list[str] = [
    "filename", "questions", "answers", "explanations", "user_answers", "results", "sources", "stats", "tutor"
]


class NotionExportRequest(BaseModel):
    session_id: str | None = None
    record_id: int | None = None
    connection_id: int
    parent_page_id: str = Field(min_length=1)
    title: str = Field("", max_length=200)
    items: list[ExportItem] = Field(default_factory=lambda: list(ALL_EXPORT_ITEMS), min_length=1)

    @model_validator(mode="after")
    def _check_source(self):
        if not (self.session_id or self.record_id):
            raise ValueError("내보낼 학습 세션 또는 학습 기록을 지정해주세요.")
        return self
