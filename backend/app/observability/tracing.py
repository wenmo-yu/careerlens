from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from fastapi import FastAPI

from app.core.config import Settings, get_settings


class NoOpSpan:
    def set_attribute(self, _key: str, _value: Any) -> None:
        return None

    def record_exception(self, _exception: BaseException) -> None:
        return None


def _parse_headers(value: str) -> dict[str, str]:
    headers: dict[str, str] = {}
    for item in value.split(","):
        key, separator, header_value = item.strip().partition("=")
        if separator and key:
            headers[key] = header_value
    return headers


def configure_telemetry(application: FastAPI, settings: Settings | None = None) -> Any | None:
    settings = settings or get_settings()
    if not settings.otel_enabled:
        return None
    try:
        from opentelemetry import trace
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
    except ImportError as exc:
        raise RuntimeError(
            'OTEL_ENABLED=true requires: pip install -e ".[observability]"'
        ) from exc

    provider = TracerProvider(
        resource=Resource.create({"service.name": settings.otel_service_name})
    )
    exporter = OTLPSpanExporter(
        endpoint=settings.otel_exporter_otlp_traces_endpoint,
        headers=_parse_headers(settings.otel_exporter_otlp_headers),
    )
    provider.add_span_processor(BatchSpanProcessor(exporter))
    trace.set_tracer_provider(provider)
    FastAPIInstrumentor.instrument_app(application, tracer_provider=provider)
    return provider


@contextmanager
def trace_operation(name: str, attributes: dict[str, Any]) -> Iterator[Any]:
    if not get_settings().otel_enabled:
        yield NoOpSpan()
        return
    try:
        from opentelemetry import trace
    except ImportError:
        yield NoOpSpan()
        return
    with trace.get_tracer("careerlens").start_as_current_span(name) as span:
        for key, value in attributes.items():
            span.set_attribute(key, value)
        yield span
