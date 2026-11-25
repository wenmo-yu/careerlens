"""Prometheus instrumentation.

``MetricsStore`` in ``metrics.py`` keeps model-call telemetry for the workbench
UI; it is in-process and only visible to whoever opens the page. These metrics
expose the same signals to a standard scraper (Prometheus, Grafana Agent,
Datadog agent), so latency and error budgets can be alerted on without a
custom integration.

Cardinality note: labels use the *route template* (``/api/v1/profiles/{user_id}``)
rather than the raw path. Labelling by URL would create one series per user id
and eventually kill the scrape target.
"""

from __future__ import annotations

import time

from prometheus_client import (
    CONTENT_TYPE_LATEST,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
)
from starlette.responses import Response
from starlette.types import ASGIApp, Message, Receive, Scope, Send

REQUEST_TOTAL = Counter(
    "careerlens_http_requests_total",
    "HTTP requests handled by the API, labelled by route template.",
    ["method", "path", "status"],
)
REQUEST_DURATION = Histogram(
    "careerlens_http_request_duration_seconds",
    "End-to-end request duration, excluding probes and the metrics endpoint.",
    ["method", "path"],
    buckets=(.01, .025, .05, .1, .25, .5, 1, 2.5, 5, 10, 30, 60),
)
INFLIGHT = Gauge(
    "careerlens_http_requests_in_flight",
    "Requests currently being served.",
)

_EXEMPT_PATHS = frozenset({"/metrics", "/health/live", "/health/ready"})


def _route_template(scope: Scope) -> str:
    """Return a low-cardinality label for the request path.

    Unknown paths collapse to ``unmatched`` so a 404 scanner cannot add one
    series per guessed URL. Known paths keep their real segments with path
    parameters replaced by their names.
    """
    if scope.get("route") is None:
        return "unmatched"
    raw = scope.get("path", "/")
    params = {
        str(value): name
        for name, value in (scope.get("path_params") or {}).items()
        if str(value)
    }
    if not params:
        return raw
    segments = raw.split("/")
    return "/".join(
        f"{{{params[segment]}}}" if segment in params else segment for segment in segments
    )


class PrometheusMiddleware:
    """Pure ASGI middleware.

    ``BaseHTTPMiddleware`` buffers streaming responses, which would break the
    server-sent events used by the run progress stream. Wrapping the ASGI app
    directly keeps streaming intact.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope["path"] in _EXEMPT_PATHS:
            await self.app(scope, receive, send)
            return

        started = time.perf_counter()
        status_code = {"value": 500}

        async def send_wrapper(message: Message) -> None:
            if message["type"] == "http.response.start":
                status_code["value"] = int(message["status"])
            await send(message)

        INFLIGHT.inc()
        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            INFLIGHT.dec()
            # FastAPI wraps included routers, so scope["route"].path is the
            # path relative to its own router ("/text", not "/api/v1/evidence
            # /text"). Rebuild the template from the request path instead and
            # substitute path parameters by segment.
            path = _route_template(scope)
            method = scope.get("method", "GET")
            REQUEST_TOTAL.labels(
                method=method, path=path, status=str(status_code["value"])
            ).inc()
            REQUEST_DURATION.labels(method=method, path=path).observe(
                time.perf_counter() - started
            )


def render_metrics() -> Response:
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)
