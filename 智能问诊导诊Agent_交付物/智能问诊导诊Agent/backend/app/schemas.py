"""Pydantic 请求模型（FastAPI）。"""
from pydantic import BaseModel, Field


class RegisterIn(BaseModel):
    username: str = Field(min_length=2, max_length=32)
    password: str = Field(min_length=6, max_length=64)
    phone: str | None = None


class LoginIn(BaseModel):
    account: str = Field(min_length=1, max_length=32)
    password: str = Field(min_length=1, max_length=64)


class ConversationCreate(BaseModel):
    title: str | None = Field(default=None, max_length=50)


class ChatIn(BaseModel):
    conversation_id: int
    content: str = Field(min_length=1, max_length=1024)


class EvaluationIn(BaseModel):
    conversation_id: int | None = None
    case_id: str | None = Field(default=None, max_length=64)
    judge_result: str | None = Field(default=None, max_length=255)
    score: float | None = Field(default=None, ge=0, le=1)
    detail: str | None = Field(default=None, max_length=2000)