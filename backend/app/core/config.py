from datetime import datetime
from functools import lru_cache

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "CareerLens API"
    app_env: str = "development"
    api_prefix: str = "/api/v1"
    # /metrics exposes request counts and latency. Keep it enabled for local
    # and container scrapes; put it behind the gateway if the API is public.
    metrics_enabled: bool | None = None
    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"
    database_url: str = "postgresql+asyncpg://career:career@localhost:5432/career"
    auto_create_schema: bool = True
    qdrant_url: str = "http://localhost:6333"
    qdrant_api_key: str = Field(default="", repr=False)
    qdrant_collection: str = "career_evidence"
    qdrant_cleanup_collections: str = ""
    upload_max_bytes: int = 10 * 1024 * 1024
    media_upload_max_bytes: int = 200 * 1024 * 1024
    media_provider: str = "auto"
    whisper_model: str = "small"
    whisper_device: str = "cpu"
    whisper_compute_type: str = "int8"
    ocr_language: str = "ch"
    retrieval_backend: str = "auto"
    retrieval_provider: str = "hash"
    embedding_dimension: int = Field(default=384, ge=16, le=1024)
    qwen_embedding_model: str = "Qwen/Qwen3-Embedding-0.6B"
    qwen_embedding_revision: str = "97b0c614be4d77ee51c0cef4e5f07c00f9eb65b3"
    qwen_reranker_model: str = "Qwen/Qwen3-Reranker-0.6B"
    retrieval_prefetch_limit: int = 20
    retrieval_local_row_limit: int = Field(default=2000, ge=20, le=20_000)
    retrieval_query_instruction: str = (
        "Retrieve personal career evidence that supports the user's claim or job requirement."
    )
    ai_provider: str = "demo"
    ai_failure_policy: str = "allow_fallback"
    ai_base_url: str = "https://api.deepseek.com"
    ai_api_key: str = Field(default="", repr=False)
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
    ai_timeout_seconds: float = Field(default=60, gt=0, le=300)
    ai_max_prompt_chars: int = Field(default=120_000, ge=2000, le=250_000)
    ai_max_output_tokens: int = Field(default=2000, ge=128, le=8192)
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
    # Agent plane (M3/M4). Disabled by default so existing deployments keep
    # running only the workflow worker until the scheduler is started.
    agent_runtime_enabled: bool = False
    agent_max_running: int = Field(default=2, ge=1, le=8)
    agent_warm_target: int = Field(default=1, ge=0, le=4)
    agent_warm_max: int = Field(default=2, ge=0, le=6)
    agent_total_cap: int = Field(default=6, ge=1, le=16)
    agent_lease_seconds: int = Field(default=30, ge=5, le=300)
    agent_warm_ttl_seconds: int = Field(default=600, ge=30, le=3600)
    agent_idle_bound_seconds: int = Field(default=300, ge=30, le=3600)
    agent_turn_timeout_seconds: int = Field(default=180, ge=5, le=900)
    agent_max_turns: int = Field(default=6, ge=1, le=12)
    agent_pending_per_user: int = Field(default=6, ge=1, le=50)
    agent_cli_module: str = "app.runtime.agent.cli"
    agent_model_provider: str = "demo"
    agent_capability_ttl_seconds: int = Field(default=120, ge=10, le=900)
    agent_api_base: str = "http://127.0.0.1:8000"
    agent_scheduler_poll_seconds: float = Field(default=0.25, gt=0, le=5)
    auth_mode: str = "disabled"
    auth_token_pepper: str = Field(default="change-me-in-production", repr=False)
    auth_token_key_version: int = Field(default=1, ge=1)
    auth_token_previous_pepper: str = Field(default="", repr=False)
    auth_token_previous_until: datetime | None = None
    auth_token_lifetime_hours: int = Field(default=24, ge=1, le=720)
    auth_registration_enabled: bool | None = None
    auth_registration_secret: str = Field(default="", repr=False)
    ops_access_token: str = Field(default="", repr=False)
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
    mcp_stdio_user_id: str = "demo-user"
    mcp_stdio_token: str = Field(default="", repr=False)

    @field_validator(
        "app_env", "auth_mode", "mcp_auth_mode", "retrieval_backend", "ai_provider",
        "ai_failure_policy", "retrieval_provider", "checkpoint_backend", mode="before",
    )
    @classmethod
    def normalize_mode(cls, value):
        return value.strip().lower() if isinstance(value, str) else value

    @field_validator("auth_token_previous_until", mode="before")
    @classmethod
    def ignore_empty_previous_until(cls, value):
        return None if value == "" else value

    @property
    def registration_enabled(self) -> bool:
        if self.auth_registration_enabled is not None:
            return self.auth_registration_enabled
        return self.app_env != "production"

    @property
    def metrics_available(self) -> bool:
        if self.metrics_enabled is not None:
            return self.metrics_enabled
        return self.app_env != "production"

    @property
    def cleanup_collections(self) -> tuple[str, ...]:
        return tuple(dict.fromkeys((
            self.qdrant_collection,
            *(part.strip() for part in self.qdrant_cleanup_collections.split(",") if part.strip()),
        )))

    def validate_security(self, role: str) -> None:
        self.validate_generation()
        if self.app_env == "production":
            if self.auth_mode != "required" or not _strong_secret(self.auth_token_pepper):
                raise RuntimeError("Production requires AUTH_MODE=required and a strong pepper")
            if self.auto_create_schema:
                raise RuntimeError("Production requires migrations and AUTO_CREATE_SCHEMA=false")
            if self.retrieval_backend != "local" and not _strong_secret(self.qdrant_api_key):
                raise RuntimeError("Production vector retrieval requires a strong QDRANT_API_KEY")
            if role == "api" and (
                not self.cors_origin_list
                or any(not origin.startswith("https://") for origin in self.cors_origin_list)
            ):
                raise RuntimeError("Production requires explicit HTTPS CORS origins")
            if role == "mcp" and self.mcp_auth_mode != "required":
                raise RuntimeError("Production requires MCP_AUTH_MODE=required")
            if self.ops_access_token and not _strong_secret(self.ops_access_token):
                raise RuntimeError("Production requires a strong OPS_ACCESS_TOKEN when configured")
            if self.auth_token_previous_pepper and not _strong_secret(
                self.auth_token_previous_pepper
            ):
                raise RuntimeError("Production requires a strong previous token pepper")
        if role == "api" and self.auth_mode == "required":
            if not self.auth_token_pepper or self.auth_token_pepper == "change-me-in-production":
                raise RuntimeError("AUTH_MODE=required needs a non-default AUTH_TOKEN_PEPPER")
            if self.registration_enabled and (
                not self.auth_registration_secret
                or self.app_env == "production"
                and not _strong_secret(self.auth_registration_secret)
            ):
                raise RuntimeError("Enabled registration requires a valid AUTH_REGISTRATION_SECRET")

    def validate_generation(self) -> None:
        if self.ai_provider == "demo":
            return
        if self.ai_provider == "deepseek" and (
            not self.ai_api_key.strip() or self.ai_api_key.startswith("replace-with")
        ):
            raise RuntimeError("AI_PROVIDER=deepseek requires a configured AI_API_KEY")
        if not self.ai_model.strip() or not self.ai_base_url.startswith(("https://", "http://")):
            raise RuntimeError("Model configuration requires an HTTP(S) AI_BASE_URL and AI_MODEL")

    @property
    def checkpoint_url(self) -> str:
        url = self.checkpoint_database_url or self.database_url
        return url.replace("postgresql+asyncpg://", "postgresql://", 1)

    @property
    def uses_postgres_checkpoint(self) -> bool:
        return self.checkpoint_backend == "postgres" or (
            self.checkpoint_backend == "auto"
            and self.checkpoint_url.startswith(("postgresql://", "postgres://"))
        )

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
    def validate_modes_and_rerank_limits(self):
        for name, allowed in (
            ("app_env", {"development", "test", "production"}),
            ("auth_mode", {"disabled", "optional", "required"}),
            ("mcp_auth_mode", {"disabled", "required"}),
            ("retrieval_backend", {"local", "auto", "qdrant"}),
            ("retrieval_provider", {"hash", "qwen"}),
            ("checkpoint_backend", {"auto", "memory", "postgres"}),
            ("ai_provider", {"demo", "deepseek", "openai_compatible", "local"}),
            ("ai_failure_policy", {"allow_fallback", "strict"}),
        ):
            if getattr(self, name) not in allowed:
                raise ValueError(f"{name.upper()} must be one of {', '.join(sorted(allowed))}")
        if self.rerank_fine_top_k > self.rerank_coarse_top_k:
            raise ValueError("RERANK_FINE_TOP_K cannot exceed RERANK_COARSE_TOP_K")
        if self.auth_token_previous_pepper and (
            self.auth_token_key_version == 1
            or self.auth_token_previous_until is None
            or self.auth_token_previous_until.utcoffset() is None
            or self.auth_token_previous_pepper == self.auth_token_pepper
        ):
            raise ValueError("Previous token pepper requires a new key version and UTC deadline")
        return self

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


def _strong_secret(secret: str) -> bool:
    value = secret.strip()
    return (
        len(value) >= 32
        and len(set(value)) >= 12
        and not value.lower().startswith(("change-me", "replace-with"))
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()

