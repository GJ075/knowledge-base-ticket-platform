from functools import lru_cache

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_env: str = "local"
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    public_api_url: str = "http://localhost:8000"
    business_timezone: str = "Asia/Shanghai"

    database_url: str = "postgresql+asyncpg://kb:kb@localhost:5432/kb"
    redis_url: str = "redis://localhost:6379/0"

    minio_endpoint: str = "localhost:9000"
    minio_access_key: str = "minioadmin"
    minio_secret_key: str = "minioadmin"
    minio_secure: bool = False
    minio_document_bucket: str = "kb-documents"
    minio_ticket_bucket: str = "ticket-attachments"

    jwt_secret: str = "change-me-in-env"
    jwt_expire_minutes: int = 480
    cookie_secure: bool = False

    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_model: str = "deepseek-chat"
    llm_timeout_seconds: int = 120
    llm_provider: str = "auto"
    conversation_history_turns: int = 5
    embedding_service_url: str = "http://localhost:8001"
    embedding_batch_size: int = 16
    embedding_timeout_seconds: int = 600

    max_upload_mb: int = 50
    chunk_target: int = 450
    chunk_max: int = 700
    chunk_min: int = 150
    chunk_overlap: int = 60
    top_k: int = 5

    candidate_k: int = 30
    fused_k: int = 40
    final_k: int = 5
    hybrid_enabled: bool = True
    rerank_enabled: bool = False
    rerank_top_n: int = 40
    rerank_threshold: float = 0.0
    rewrite_enabled: bool = True
    context_token_budget: int = 3000
    rerank_timeout_seconds: float = 30.0

    cors_origins: str = "http://localhost:3000"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @model_validator(mode="after")
    def _validate_chunk_window(self) -> "Settings":
        if not self.chunk_min <= self.chunk_target <= self.chunk_max:
            raise ValueError(
                "需满足 CHUNK_MIN <= CHUNK_TARGET <= CHUNK_MAX，"
                f"当前为 {self.chunk_min} / {self.chunk_target} / {self.chunk_max}"
            )
        return self

    @property
    def cors_origin_list(self) -> list[str]:
        return [item.strip() for item in self.cors_origins.split(",") if item.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
