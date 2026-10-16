from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "CareerLens API"
    app_env: str = "development"
    api_prefix: str = "/api/v1"
    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"
    database_url: str = "postgresql+asyncpg://career:career@localhost:5432/career"
    auto_create_schema: bool = True
    qdrant_url: str = "http://localhost:6333"
    qdrant_collection: str = "career_evidence"
    upload_max_bytes: int = 10 * 1024 * 1024
    media_upload_max_bytes: int = 200 * 1024 * 1024
    media_provider: str = "auto"
    whisper_model: str = "small"
    whisper_device: str = "cpu"
    whisper_compute_type: str = "int8"
    ocr_language: str = "ch"
    retrieval_backend: str = "auto"
    retrieval_provider: str = "hash"
    embedding_dimension: int = 384
    qwen_embedding_model: str = "Qwen/Qwen3-Embedding-0.6B"
    qwen_reranker_model: str = "Qwen/Qwen3-Reranker-0.6B"
    retrieval_prefetch_limit: int = 20
    retrieval_query_instruction: str = (
        "Retrieve personal career evidence that supports the user's claim or job requirement."
    )
    ai_provider: str = "demo"
    ai_base_url: str = "https://api.deepseek.com"
    ai_api_key: str = ""
    ai_model: str = "deepseek-flash"
    ai_timeout_seconds: float = 60
    ai_input_price_per_million: float = 0
    ai_output_price_per_million: float = 0
    checkpoint_backend: str = "auto"
    checkpoint_database_url: str = ""
    auth_mode: str = "disabled"
    auth_token_pepper: str = "change-me-in-production"
    auth_registration_secret: str = ""
    otel_enabled: bool = False
    otel_service_name: str = "careerlens-api"
    otel_exporter_otlp_traces_endpoint: str = "http://localhost:4318/v1/traces"
    otel_exporter_otlp_headers: str = ""
    mcp_transport: str = "stdio"
    mcp_host: str = "127.0.0.1"
    mcp_port: int = 8001
    mcp_streamable_http_path: str = "/mcp"
    mcp_auth_mode: str = "disabled"
    mcp_auth_issuer_url: str = "http://localhost:8000"
    mcp_resource_server_url: str = "http://localhost:8001/mcp"

    @property
    def checkpoint_url(self) -> str:
        url = self.checkpoint_database_url or self.database_url
        return url.replace("postgresql+asyncpg://", "postgresql://", 1)

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()

