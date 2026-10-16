from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import router
from app.api.routes.health import router as health_router
from app.core.config import get_settings
from app.core.database import create_schema, engine
from app.graph.checkpoint import configure_checkpoint
from app.observability.tracing import configure_telemetry


@asynccontextmanager
async def lifespan(application: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    if settings.auth_mode == "required" and (
        settings.auth_token_pepper == "change-me-in-production"
        or not settings.auth_registration_secret
    ):
        raise RuntimeError(
            "AUTH_MODE=required needs a non-default AUTH_TOKEN_PEPPER and AUTH_REGISTRATION_SECRET"
        )
    if settings.auto_create_schema:
        await create_schema()
    try:
        async with configure_checkpoint():
            yield
    finally:
        provider = getattr(application.state, "telemetry_provider", None)
        if provider is not None:
            provider.shutdown()
        await engine.dispose()


def create_app() -> FastAPI:
    settings = get_settings()
    application = FastAPI(title=settings.app_name, version="0.1.0", lifespan=lifespan)
    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    application.include_router(health_router, tags=["health"])
    application.include_router(router, prefix=settings.api_prefix)
    application.state.telemetry_provider = configure_telemetry(application, settings)
    return application


app = create_app()

