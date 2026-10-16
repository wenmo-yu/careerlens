import json
from pathlib import Path

import httpx

from app.evaluation import evaluate_regression
from app.evaluation.cli import main as regression_main
from app.llm.provider import OpenAICompatibleProvider
from app.observability import get_metrics_store
from app.observability.tracing import _parse_headers
from app.schemas.evaluation import RegressionThresholds
from app.services.evaluation import load_dev_benchmark, load_sample_dataset


async def test_sample_evaluation_is_persisted(client):
    response = await client.post("/api/v1/evaluation/sample")
    assert response.status_code == 200
    payload = response.json()
    assert payload["dataset_name"] == "careerlens-baseline-v1"
    assert payload["profile_extraction_f1"] == 1.0
    assert payload["evidence_recall_at_k"] == 1.0
    assert payload["supported_claim_rate"] == 1.0
    assert payload["requirement_matching_f1"] == 1.0

    runs = await client.get("/api/v1/evaluation/runs")
    assert runs.status_code == 200
    assert runs.json()[0]["id"] == payload["id"]


async def test_sample_regression_gate_passes_and_is_persisted(client):
    response = await client.post("/api/v1/evaluation/regression/sample")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "passed"
    assert payload["failures"] == []
    assert payload["run"]["details"]["regression"]["status"] == "passed"


async def test_dev_benchmark_covers_multiple_scenarios(client):
    response = await client.post("/api/v1/evaluation/regression/benchmark")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "passed"
    assert payload["run"]["dataset_name"] == "careerlens-dev-benchmark-v2"
    assert payload["run"]["metrics"]["case_count"] == 10
    assert payload["run"]["metrics"]["query_count"] == 20
    assert payload["run"]["metrics"]["claim_count"] >= 40


def test_regression_gate_reports_every_metric_below_threshold():
    minimums = RegressionThresholds()
    status, failures = evaluate_regression(
        {
            "profile_extraction_f1": 0.9,
            "evidence_recall_at_k": 1.0,
            "supported_claim_rate": 0.8,
            "requirement_matching_f1": 1.0,
        },
        minimums,
    )
    assert status == "failed"
    assert [item["metric"] for item in failures] == [
        "profile_extraction_f1",
        "supported_claim_rate",
    ]


def test_regression_cli_returns_success_for_frozen_sample(tmp_path):
    project = Path(__file__).parents[2]
    exit_code = regression_main(
        [
            "--dataset",
            str(project / "eval" / "datasets" / "careerlens-baseline-v1.json"),
            "--baseline",
            str(project / "eval" / "baselines" / "careerlens-baseline-v1.json"),
            "--output",
            str(tmp_path / "result.json"),
        ]
    )
    assert exit_code == 0
    assert (tmp_path / "result.json").exists()


def test_otlp_header_parser_ignores_invalid_items():
    assert _parse_headers("authorization=secret,tenant=career,invalid") == {
        "authorization": "secret",
        "tenant": "career",
    }


def test_sample_dataset_has_human_labels():
    dataset = load_sample_dataset()
    assert dataset.cases[0].expected_profile
    assert dataset.cases[0].retrieval_queries
    assert dataset.cases[0].expected_requirements


def test_dev_benchmark_has_unique_cases_and_evidence_ids():
    dataset = load_dev_benchmark()
    assert len(dataset.cases) == 10
    assert len({case.id for case in dataset.cases}) == len(dataset.cases)
    evidence_ids = [item.id for case in dataset.cases for item in case.evidence]
    assert len(evidence_ids) == 40
    assert len(set(evidence_ids)) == len(evidence_ids)
    project = Path(__file__).parents[2]
    public_baseline = json.loads(
        (project / "eval" / "baselines" / "careerlens-dev-benchmark-v2.json").read_text(
            encoding="utf-8"
        )
    )
    bundled_baseline = json.loads(
        (
            project
            / "backend"
            / "app"
            / "evaluation"
            / "dev_benchmark_baseline_v2.json"
        ).read_text(encoding="utf-8")
    )
    assert public_baseline == bundled_baseline


async def test_model_metrics_capture_latency_tokens_and_cost(monkeypatch):
    async def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": '{"answer":"ok"}'}}],
                "usage": {"prompt_tokens": 120, "completion_tokens": 30},
            },
        )

    monkeypatch.setenv("AI_INPUT_PRICE_PER_MILLION", "1")
    monkeypatch.setenv("AI_OUTPUT_PRICE_PER_MILLION", "2")
    from app.core.config import get_settings

    get_settings.cache_clear()
    before = get_metrics_store().summary()["request_count"]
    provider = OpenAICompatibleProvider(
        provider="test",
        base_url="https://example.test",
        api_key="secret",
        model="test-model",
        timeout=5,
        transport=httpx.MockTransport(handler),
    )
    await provider.generate_json(
        system_prompt="system",
        user_prompt="user",
        schema={"type": "object"},
        operation="evaluation_test",
    )
    summary = get_metrics_store().summary()
    assert summary["request_count"] == before + 1
    latest = get_metrics_store().calls(1)[0]
    assert latest["operation"] == "evaluation_test"
    assert latest["prompt_tokens"] == 120
    assert latest["completion_tokens"] == 30
    assert latest["estimated_cost_usd"] == 0.00018
    monkeypatch.delenv("AI_INPUT_PRICE_PER_MILLION")
    monkeypatch.delenv("AI_OUTPUT_PRICE_PER_MILLION")
    get_settings.cache_clear()


async def test_observability_api(client):
    response = await client.get("/api/v1/observability/summary")
    assert response.status_code == 200
    assert "success_rate" in response.json()
    calls = await client.get("/api/v1/observability/calls", params={"limit": 1})
    assert calls.status_code == 200
    assert calls.json()["count"] <= 1
