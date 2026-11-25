"""Metrics endpoint contract.

The point of these tests is not "the endpoint returns 200" but that the labels
stay bounded: one series per route template, never one per user id.
"""

from __future__ import annotations


async def test_metrics_exposes_counters_with_route_templates(client):
    created = await client.post(
        "/api/v1/evidence/text",
        json={"user_id": "metrics-user", "content": "使用 Python 与 FastAPI 做过检索服务。"},
    )
    assert created.status_code == 201, created.text

    # Same route, different user id: must not create a second label value.
    await client.post(
        "/api/v1/evidence/text",
        json={"user_id": "metrics-user-2", "content": "使用 Docker 部署过服务。"},
    )
    await client.get("/api/v1/profiles/metrics-user")

    response = await client.get("/metrics")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")

    body = response.text
    assert "careerlens_http_requests_total" in body
    assert 'path="/api/v1/evidence/text"' in body
    # Template, not the raw path.
    assert 'path="/api/v1/profiles/{user_id}"' in body
    assert 'path="/api/v1/profiles/metrics-user"' not in body
    assert "careerlens_http_request_duration_seconds_bucket" in body


async def test_metrics_can_be_disabled(client, monkeypatch):
    from app.core.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "metrics_enabled", False)
    response = await client.get("/metrics")
    assert response.status_code == 404


async def test_probes_are_not_counted(client):
    before = (await client.get("/metrics")).text
    await client.get("/health/live")
    await client.get("/health/ready")
    after = (await client.get("/metrics")).text
    assert 'path="/health/live"' not in after
    # The scrape itself must not inflate the series either.
    assert after.count("careerlens_http_requests_total{") == before.count(
        "careerlens_http_requests_total{"
    )
