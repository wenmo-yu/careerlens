import tomllib
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.router import router
from app.api.routes.agent_internal import router as agent_internal_router
from app.api.routes.health import router as health_router
from app.api.routes.runs import SUBMISSION_REJECTED
from app.core.config import get_settings
from app.core.database import create_schema, engine
from app.graph.career import build_career_graph
from app.llm.provider import ModelUnavailable
from app.observability.prometheus import PrometheusMiddleware
from app.observability.tracing import configure_telemetry
from app.retrieval.service import RetrievalUnavailable
from app.runtime.store import StaleInput


@asynccontextmanager
async def lifespan(application: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    settings.validate_security("api")
    if settings.auto_create_schema:
        await create_schema()
    try:
        application.state.career_graph = build_career_graph()
        yield
    finally:
        provider = getattr(application.state, "telemetry_provider", None)
        if provider is not None:
            provider.shutdown()
        await engine.dispose()


def _app_version() -> str:
    """Read the version from pyproject.toml so it never drifts from the source.

    importlib.metadata would report a stale version in editable installs until
    the package is reinstalled; reading the manifest is always current.
    """
    manifest = Path(__file__).parents[1] / "pyproject.toml"
    try:
        with manifest.open("rb") as file:
            return str(tomllib.load(file)["project"]["version"])
    except (OSError, KeyError):
        return "0.0.0"


def create_app() -> FastAPI:
    settings = get_settings()
    application = FastAPI(title=settings.app_name, version=_app_version(), lifespan=lifespan)

    @application.exception_handler(ModelUnavailable)
    async def model_unavailable(_request: Request, exc: ModelUnavailable) -> JSONResponse:
        return JSONResponse(status_code=503, content={"detail": str(exc), "code": exc.reason})

    @application.exception_handler(RetrievalUnavailable)
    async def retrieval_unavailable(_request: Request, exc: RetrievalUnavailable) -> JSONResponse:
        return JSONResponse(status_code=503, content={"detail": str(exc)})

    @application.exception_handler(StaleInput)
    async def stale_input(_request: Request, _exc: StaleInput) -> JSONResponse:
        return JSONResponse(status_code=409, content={"detail": "Inputs or account state changed"})

    @application.exception_handler(RequestValidationError)
    async def request_validation_error(
        request: Request, exc: RequestValidationError,
    ) -> JSONResponse:
        # Validation input/context may contain a credential or an entire uploaded form.
        errors = [
            {key: error[key] for key in ("type", "loc", "msg") if key in error}
            for error in exc.errors()
        ]
        headers = None
        if request.method == "POST" and request.url.path in (
            f"{settings.api_prefix}/runs", f"{settings.api_prefix}/runs/uploads",
        ):
            headers = SUBMISSION_REJECTED
        return JSONResponse(status_code=422, content={"detail": errors}, headers=headers)

    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Submission-Outcome"],
    )
    application.add_middleware(PrometheusMiddleware)
    application.include_router(health_router, tags=["health"])
    application.include_router(router, prefix=settings.api_prefix)
    application.include_router(agent_internal_router, include_in_schema=False)
    application.state.telemetry_provider = configure_telemetry(application, settings)
    return application


app = create_app()

