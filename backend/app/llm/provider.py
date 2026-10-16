import json
import re
import time
from functools import lru_cache
from typing import Any, Protocol

import httpx

from app.core.config import get_settings
from app.observability.metrics import ModelCallMetric, get_metrics_store, now_iso
from app.observability.tracing import trace_operation


class LLMProvider(Protocol):
    @property
    def diagnostics(self) -> dict[str, Any]: ...

    async def generate_json(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        schema: dict[str, Any],
        operation: str = "generation",
    ) -> dict[str, Any]: ...


class DemoProvider:
    @property
    def diagnostics(self) -> dict[str, Any]:
        return {"provider": "demo", "model": "deterministic", "fallback": True}

    async def generate_json(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        schema: dict[str, Any],
        operation: str = "generation",
    ) -> dict[str, Any]:
        raise RuntimeError("No remote or local language model is configured")


class OpenAICompatibleProvider:
    def __init__(
        self,
        *,
        provider: str,
        base_url: str,
        api_key: str,
        model: str,
        timeout: float,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.provider = provider
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.timeout = timeout
        self.transport = transport

    @property
    def diagnostics(self) -> dict[str, Any]:
        return {"provider": self.provider, "model": self.model, "fallback": False}

    async def generate_json(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        schema: dict[str, Any],
        operation: str = "generation",
    ) -> dict[str, Any]:
        started = time.perf_counter()
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        schema_text = json.dumps(schema, ensure_ascii=False)
        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        f"{system_prompt}\n只输出一个 JSON 对象，不要 Markdown。"
                        f"JSON Schema: {schema_text}"
                    ),
                },
                {"role": "user", "content": user_prompt},
            ],
            "response_format": {"type": "json_object"},
            "temperature": 0.1,
        }
        with trace_operation(
            "llm.generate_json",
            {
                "gen_ai.operation.name": operation,
                "gen_ai.provider.name": self.provider,
                "gen_ai.request.model": self.model,
            },
        ) as span:
            try:
                async with httpx.AsyncClient(
                    timeout=self.timeout, transport=self.transport
                ) as client:
                    response = await client.post(
                        f"{self.base_url}/chat/completions", headers=headers, json=payload
                    )
                    response.raise_for_status()
                body = response.json()
                content = body["choices"][0]["message"]["content"].strip()
                content = re.sub(
                    r"^```(?:json)?\s*|\s*```$", "", content, flags=re.IGNORECASE
                )
                value = json.loads(content)
                if not isinstance(value, dict):
                    raise ValueError("The model response must be a JSON object")
            except Exception as exc:
                self._record(operation, started, "error", {}, type(exc).__name__)
                span.set_attribute("careerlens.status", "error")
                span.set_attribute("error.type", type(exc).__name__)
                span.record_exception(exc)
                raise
            metric = self._record(operation, started, "success", body.get("usage", {}), None)
            span.set_attribute("careerlens.status", "success")
            span.set_attribute("gen_ai.usage.input_tokens", metric.prompt_tokens)
            span.set_attribute("gen_ai.usage.output_tokens", metric.completion_tokens)
            span.set_attribute("careerlens.estimated_cost_usd", metric.estimated_cost_usd)
            return value

    def _record(
        self,
        operation: str,
        started: float,
        status: str,
        usage: dict[str, Any],
        error_type: str | None,
    ) -> ModelCallMetric:
        settings = get_settings()
        prompt_tokens = int(usage.get("prompt_tokens", 0) or 0)
        completion_tokens = int(usage.get("completion_tokens", 0) or 0)
        cost = (
            prompt_tokens * settings.ai_input_price_per_million
            + completion_tokens * settings.ai_output_price_per_million
        ) / 1_000_000
        metric = ModelCallMetric(
            operation=operation,
            provider=self.provider,
            model=self.model,
            status=status,
            latency_ms=round((time.perf_counter() - started) * 1000, 2),
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            estimated_cost_usd=round(cost, 8),
            error_type=error_type,
            created_at=now_iso(),
        )
        get_metrics_store().record(metric)
        return metric


@lru_cache
def get_llm_provider() -> LLMProvider:
    settings = get_settings()
    provider = settings.ai_provider.lower().strip()
    if provider == "demo":
        return DemoProvider()
    if provider == "deepseek" and not settings.ai_api_key:
        return DemoProvider()
    if provider not in {"deepseek", "openai_compatible", "local"}:
        return DemoProvider()
    return OpenAICompatibleProvider(
        provider=provider,
        base_url=settings.ai_base_url,
        api_key=settings.ai_api_key,
        model=settings.ai_model,
        timeout=settings.ai_timeout_seconds,
    )
