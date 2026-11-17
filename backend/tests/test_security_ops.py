import pytest

from app.core.config import get_settings


@pytest.fixture(autouse=True)
def _reset_settings(monkeypatch):
    """Keep auth settings isolated and restored for every test in this module."""
    original_mode = get_settings().auth_mode
    yield
    monkeypatch.setenv("AUTH_MODE", original_mode)
    get_settings.cache_clear()


def _enable_required_auth(monkeypatch):
    monkeypatch.setenv("AUTH_MODE", "required")
    monkeypatch.setenv("AUTH_TOKEN_PEPPER", "security-ops-test-pepper-with-entropy")
    monkeypatch.setenv("AUTH_REGISTRATION_SECRET", "registration-secret")
    get_settings.cache_clear()


async def _owner_token(client, user_id: str) -> str:
    response = await client.post(
        "/api/v1/auth/register",
        json={"user_id": user_id, "name": "owner"},
        headers={"X-Registration-Secret": "registration-secret"},
    )
    assert response.status_code == 200
    return response.json()["token"]


async def test_ready_returns_503_when_a_dependency_is_unavailable(client, monkeypatch):
    """A degraded readiness probe must be an HTTP 503, not a 200 body flag."""
    monkeypatch.setenv("QDRANT_URL", "http://127.0.0.1:1")
    monkeypatch.setenv("RETRIEVAL_BACKEND", "local")
    get_settings.cache_clear()

    response = await client.get("/health/ready")

    assert response.status_code == 503
    assert response.json()["status"] == "degraded"


async def test_ops_endpoints_require_token_in_required_mode(client, monkeypatch):
    _enable_required_auth(monkeypatch)

    assert (await client.get("/api/v1/observability/summary")).status_code == 401
    assert (await client.get("/api/v1/observability/calls")).status_code == 401
    assert (await client.get("/api/v1/evaluation/runs")).status_code == 401
    assert (await client.post("/api/v1/evaluation/sample")).status_code == 401


async def test_ops_endpoints_reject_non_manage_token(client, monkeypatch):
    _enable_required_auth(monkeypatch)
    owner = await _owner_token(client, "viewer-owner")
    created = await client.post(
        "/api/v1/auth/tokens",
        json={"user_id": "viewer-owner", "name": "reader", "scopes": ["read"]},
        headers={"Authorization": f"Bearer {owner}"},
    )
    assert created.status_code == 200
    headers = {"Authorization": f"Bearer {created.json()['token']}"}

    assert (await client.get("/api/v1/observability/summary", headers=headers)).status_code == 403
    assert (await client.get("/api/v1/evaluation/runs", headers=headers)).status_code == 403


async def test_ops_endpoints_accept_manage_token(client, monkeypatch):
    _enable_required_auth(monkeypatch)
    owner = await _owner_token(client, "admin-owner")
    headers = {"Authorization": f"Bearer {owner}"}

    assert (await client.get("/api/v1/observability/summary", headers=headers)).status_code == 200
    assert (await client.get("/api/v1/evaluation/runs", headers=headers)).status_code == 200
    assert (await client.post("/api/v1/evaluation/sample", headers=headers)).status_code == 200


async def test_ops_endpoints_open_in_disabled_mode(client, monkeypatch):
    monkeypatch.setenv("AUTH_MODE", "disabled")
    get_settings.cache_clear()

    assert (await client.get("/api/v1/observability/summary")).status_code == 200
    assert (await client.get("/api/v1/evaluation/runs")).status_code == 200
