FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app
ARG INSTALL_ML=false
ARG INSTALL_MULTIMODAL=false
COPY pyproject.toml ./
COPY app ./app
COPY alembic.ini ./
COPY migrations ./migrations
RUN if [ "$INSTALL_ML" = "true" ] && [ "$INSTALL_MULTIMODAL" = "true" ]; then \
      pip install --no-cache-dir ".[ml,multimodal]"; \
    elif [ "$INSTALL_ML" = "true" ]; then \
      pip install --no-cache-dir ".[ml]"; \
    elif [ "$INSTALL_MULTIMODAL" = "true" ]; then \
      pip install --no-cache-dir ".[multimodal]"; \
    else \
      pip install --no-cache-dir .; \
    fi

EXPOSE 8000 8001
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
