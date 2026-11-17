FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS builder

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/app/.venv

WORKDIR /app
COPY pyproject.toml uv.lock ./
COPY app ./app

ARG INSTALL_ML=false
ARG INSTALL_MULTIMODAL=false
ARG INSTALL_OBSERVABILITY=false
RUN set --; \
    if [ "$INSTALL_ML" = "true" ]; then set -- "$@" --extra ml; fi; \
    if [ "$INSTALL_MULTIMODAL" = "true" ]; then set -- "$@" --extra multimodal; fi; \
    if [ "$INSTALL_OBSERVABILITY" = "true" ]; then set -- "$@" --extra observability; fi; \
    uv sync --frozen --no-dev --no-editable "$@"

FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH"

WORKDIR /app
COPY --from=builder /app/.venv /app/.venv
COPY app ./app
COPY alembic.ini ./
COPY migrations ./migrations

EXPOSE 8000 8001
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
