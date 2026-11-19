from functools import lru_cache

from pydantic import Field, model_validator
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
    # Optional per-role model overrides: "answer=model-a,wiki=model-b,...".
    # Empty means every role uses ai_model. Kept as a string so it can be set
    # with a single env var (MODEL_ROLE_BINDINGS) in Compose/CI.
    model_role_bindings: str = ""
    # Two-stage cascading rerank: coarse cross-encoder narrows to top_k, then a
    # fine reranker produces the final top_k. Disabled by default (single stage).
    rerank_stages_enabled: bool = False
    rerank_coarse_top_k: int = Field(default=15, ge=1)
    rerank_fine_top_k: int = Field(default=5, ge=1)
    ai_timeout_seconds: float = 60
    ai_input_price_per_million: float = 0
    ai_output_price_per_million: float = 0
    checkpoint_backend: str = "auto"
    checkpoint_database_url: str = ""
    run_worker_concurrency: int = Field(default=2, ge=1, le=8)
    run_global_concurrency: int = Field(default=4, ge=1, le=32)
    run_pending_per_user: int = Field(default=12, ge=1, le=100)
    run_lease_seconds: int = Field(default=30, ge=3, le=300)
    run_timeout_seconds: int = Field(default=300, ge=5, le=1800)
    run_upload_max_bytes: int = Field(default=20 * 1024 * 1024, ge=1, le=200 * 1024 * 1024)
    run_pending_hours: int = Field(default=24, ge=1, le=168)
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

    @property
    def role_models(self) -> dict[str, str]:
        """Parse MODEL_ROLE_BINDINGS into a role -> model map."""
        bindings: dict[str, str] = {}
        for part in self.model_role_bindings.split(","):
            if "=" not in part:
                continue
            role, model = part.split("=", 1)
            role, model = role.strip(), model.strip()
            if role and model:
                bindings[role] = model
        return bindings

    def model_for_role(self, role: str) -> str:
        return self.role_models.get(role, self.ai_model)

    @model_validator(mode="after")
    def validate_rerank_limits(self):
        if self.rerank_fine_top_k > self.rerank_coarse_top_k:
            raise ValueError("RERANK_FINE_TOP_K cannot exceed RERANK_COARSE_TOP_K")
        return self

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()

