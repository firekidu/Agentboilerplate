from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    question: str = Field(min_length=1, max_length=2000)
    thread_id: UUID | None = None


class Source(BaseModel):
    citation: int
    document_id: str
    filename: str
    page: int | None = None
    chunk: int
    score: float
    excerpt: str


class ChatResponse(BaseModel):
    thread_id: UUID
    answer: str
    sources: list[Source]
    mode: str


class DocumentResponse(BaseModel):
    document_id: str
    filename: str
    status: str
    chunks: int
    duplicate: bool = False
