import hashlib
from typing import Literal

from pydantic import BaseModel, Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class KeyRecord(BaseModel):
    # Only a hash is needed by the API. The raw key stays with its owner.
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    tenant_id: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]{0,47}$")
    role: Literal["admin", "reader"] = "reader"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    environment: Literal["development", "production"] = "development"
    ai_backend: Literal["fake", "openai"] = "fake"
    database_url: SecretStr
    qdrant_url: str = "http://qdrant:6333"
    qdrant_api_key: SecretStr
    qdrant_collection: str = Field(default="knowledge", pattern=r"^[a-z][a-z0-9_-]{0,40}$")
    api_keys_json: list[KeyRecord]
    metrics_key: SecretStr
    openai_api_key: SecretStr = SecretStr("")
    chat_model: str = "gpt-4.1-mini"
    embedding_model: str = "text-embedding-3-small"
    embedding_dimensions: int = Field(default=1536, ge=256, le=3072)
    chunk_size: int = Field(default=1200, ge=300, le=2000)
    chunk_overlap: int = Field(default=200, ge=0)
    top_k: int = Field(default=5, ge=1, le=10)
    score_threshold: float = Field(default=0.30, ge=0, le=1)
    max_file_bytes: int = Field(default=5_000_000, ge=1000, le=10_000_000)
    max_document_chars: int = Field(default=250_000, ge=1000, le=1_000_000)
    max_chunks: int = Field(default=300, ge=1, le=1000)
    max_documents: int = Field(default=100, ge=1, le=500)
    max_pdf_pages: int = Field(default=100, ge=1, le=300)
    chat_per_minute: int = Field(default=20, ge=1)
    chat_per_day: int = Field(default=500, ge=1)
    uploads_per_day: int = Field(default=30, ge=1)
    max_output_tokens: int = Field(default=600, ge=100, le=2000)
    history_turns: int = Field(default=4, ge=0, le=10)

    @model_validator(mode="after")
    def validate_secrets(self):
        if not self.api_keys_json:
            raise ValueError("Generate tenant API keys with scripts/setup_env.py")
        hashes = [k.sha256 for k in self.api_keys_json]
        if len(hashes) != len(set(hashes)):
            raise ValueError("Each API key must be unique")
        if len(self.metrics_key.get_secret_value()) < 32:
            raise ValueError("METRICS_KEY must contain at least 32 characters")
        if len(self.qdrant_api_key.get_secret_value()) < 32:
            raise ValueError("QDRANT_API_KEY must contain at least 32 characters")
        if self.chunk_overlap >= self.chunk_size:
            raise ValueError("CHUNK_OVERLAP must be smaller than CHUNK_SIZE")
        if self.environment == "production" and self.ai_backend == "fake":
            raise ValueError("Production requires AI_BACKEND=openai")
        if self.ai_backend == "openai" and not self.openai_api_key.get_secret_value():
            raise ValueError("OPENAI_API_KEY is required in live mode")
        return self

    @property
    def dimensions(self) -> int:
        return 256 if self.ai_backend == "fake" else self.embedding_dimensions

    @property
    def collection_name(self) -> str:
        # Different embedding spaces NEVER share a collection, even if sizes match.
        signature = (
            f"v1:{self.ai_backend}:{self.embedding_model}:{self.dimensions}:"
            f"{self.chunk_size}:{self.chunk_overlap}"
        )
        suffix = hashlib.sha256(signature.encode()).hexdigest()[:12]
        return f"{self.qdrant_collection}_{suffix}"
