import math
from collections import Counter, deque
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from threading import Lock
from typing import Any


@dataclass(frozen=True)
class ModelCallMetric:
    operation: str
    provider: str
    model: str
    status: str
    latency_ms: float
    prompt_tokens: int
    completion_tokens: int
    estimated_cost_usd: float
    error_type: str | None
    created_at: str


class MetricsStore:
    def __init__(self, max_size: int = 1000) -> None:
        self._calls: deque[ModelCallMetric] = deque(maxlen=max_size)
        self._lock = Lock()

    def record(self, metric: ModelCallMetric) -> None:
        with self._lock:
            self._calls.append(metric)

    def calls(self, limit: int = 50) -> list[dict[str, Any]]:
        with self._lock:
            values = list(self._calls)[-limit:]
        return [asdict(item) for item in reversed(values)]

    def summary(self) -> dict[str, Any]:
        with self._lock:
            values = list(self._calls)
        if not values:
            return {
                "request_count": 0,
                "success_rate": 0.0,
                "average_latency_ms": 0.0,
                "p95_latency_ms": 0.0,
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "estimated_cost_usd": 0.0,
                "status_counts": {},
                "providers": {},
            }
        latencies = sorted(item.latency_ms for item in values)
        p95_index = min(len(latencies) - 1, max(0, math.ceil(len(latencies) * 0.95) - 1))
        statuses = Counter(item.status for item in values)
        providers = Counter(f"{item.provider}/{item.model}" for item in values)
        success_count = statuses.get("success", 0)
        return {
            "request_count": len(values),
            "success_rate": round(success_count / len(values), 4),
            "average_latency_ms": round(sum(latencies) / len(latencies), 2),
            "p95_latency_ms": round(latencies[p95_index], 2),
            "prompt_tokens": sum(item.prompt_tokens for item in values),
            "completion_tokens": sum(item.completion_tokens for item in values),
            "estimated_cost_usd": round(sum(item.estimated_cost_usd for item in values), 6),
            "status_counts": dict(statuses),
            "providers": dict(providers),
        }


_store = MetricsStore()


def get_metrics_store() -> MetricsStore:
    return _store


def now_iso() -> str:
    return datetime.now(UTC).isoformat()
