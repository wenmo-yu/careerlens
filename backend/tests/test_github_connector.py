"""GitHub import: user-supplied read-only token, never persisted."""

import httpx
import pytest

from app.api.routes import connectors as connectors_route
from app.connectors.base import ConnectorItem
from app.connectors.github import (
    GitHubImportError,
    fetch_github_items,
    normalise_repo_refs,
)

TOKEN = "github_pat_" + "a" * 30


def _transport(handler):
    return httpx.MockTransport(handler)


def _repo_payload(**overrides):
    payload = {
        "full_name": "octo/demo",
        "description": "一个用于演示的 RAG 项目",
        "html_url": "https://github.com/octo/demo",
        "language": "Python",
        "topics": ["rag", "fastapi"],
        "stargazers_count": 12,
        "forks_count": 3,
        "visibility": "public",
        "pushed_at": "2026-11-01T10:00:00Z",
    }
    payload.update(overrides)
    return payload


def test_normalise_repo_refs_accepts_urls_and_deduplicates():
    refs = normalise_repo_refs([
        "https://github.com/octo/demo.git",
        "octo/demo",
        "github.com/octo/demo/tree/main",
        "https://github.com/octo/other?tab=readme#install",
        "  ",
    ])
    assert refs == ["octo/demo", "octo/other"]
    with pytest.raises(GitHubImportError, match="owner/name"):
        normalise_repo_refs(["not-a-repo"])
    with pytest.raises(GitHubImportError, match="最多导入"):
        normalise_repo_refs([f"octo/repo{index}" for index in range(11)])


async def test_fetch_builds_items_without_leaking_token():
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if request.url.path == "/user":
            return httpx.Response(200, json={"login": "octo"})
        if request.url.path == "/repos/octo/demo":
            return httpx.Response(200, json=_repo_payload())
        if request.url.path == "/repos/octo/demo/readme":
            assert request.headers["accept"] == "application/vnd.github.raw"
            return httpx.Response(200, text="# Demo\n\n用 FastAPI 做 RAG 检索。")
        return httpx.Response(404)

    items, skipped = await fetch_github_items(
        token=TOKEN, repos=["octo/demo"], transport=_transport(handler)
    )
    assert skipped == 0
    assert len(items) == 1
    item = items[0]
    assert item.external_id == "github:octo/demo@2026-11-01T10:00:00Z"
    assert "README 摘录" in item.content
    assert "FastAPI" in item.content
    assert item.metadata["claim_strength"] == "self_reported_published"
    assert item.metadata["account_login"] == "octo"
    assert item.metadata["stars"] == 12
    assert TOKEN not in str(item.metadata)
    assert TOKEN not in item.content
    assert len(seen) == 3


async def test_fetch_uses_recent_repos_when_none_given():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/user":
            return httpx.Response(200, json={"login": "octo"})
        if request.url.path == "/user/repos":
            assert request.url.params["affiliation"] == "owner"
            return httpx.Response(200, json=[{"full_name": "octo/demo"}])
        if request.url.path == "/repos/octo/demo":
            return httpx.Response(200, json=_repo_payload())
        if request.url.path == "/repos/octo/demo/readme":
            return httpx.Response(200, text="README")
        return httpx.Response(404)

    items, skipped = await fetch_github_items(token=TOKEN, transport=_transport(handler))
    assert len(items) == 1 and skipped == 0


async def test_fetch_skips_repo_without_readme_or_description():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/user":
            return httpx.Response(200, json={"login": "octo"})
        if request.url.path == "/repos/octo/empty":
            return httpx.Response(200, json=_repo_payload(description=None))
        if request.url.path == "/repos/octo/empty/readme":
            return httpx.Response(404)
        return httpx.Response(404)

    items, skipped = await fetch_github_items(
        token=TOKEN, repos=["octo/empty"], transport=_transport(handler)
    )
    assert items == []
    assert skipped == 1


async def test_fetch_reports_bad_token_and_rate_limit():
    def unauthorized(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"message": "Bad credentials"})

    with pytest.raises(GitHubImportError, match="令牌无效"):
        await fetch_github_items(token=TOKEN, transport=_transport(unauthorized))

    def limited(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            403, headers={"x-ratelimit-remaining": "0"}, json={"message": "rate limit"}
        )

    with pytest.raises(GitHubImportError, match="限流"):
        await fetch_github_items(token=TOKEN, transport=_transport(limited))

    with pytest.raises(GitHubImportError, match="令牌格式"):
        await fetch_github_items(token="short", transport=_transport(unauthorized))


async def test_registry_lists_token_source_as_available(client):
    response = await client.get("/api/v1/connectors/registry")
    assert response.status_code == 200
    rows = {row["key"]: row for row in response.json()["sources"]}
    assert rows["github_token"]["available"] is True
    assert rows["github_token"]["auth_level"] == "T"
    assert "不落库" in rows["github_token"]["note"]
    assert rows["official_oauth"]["available"] is False


async def test_import_endpoint_stores_evidence_and_handles_errors(client, monkeypatch):
    token = TOKEN

    async def fake_fetch(*, token: str, repos: list[str] | None = None):
        assert token == TOKEN
        assert repos == ["octo/demo"]
        return [
            ConnectorItem(
                external_id="github:octo/demo@1",
                source_name="octo/demo",
                content="项目：octo/demo\nREADME 摘录：用 FastAPI 做 RAG。",
                metadata={
                    "connector": "github_token",
                    "connector_item_id": "github:octo/demo@1",
                    "claim_strength": "self_reported_published",
                },
            )
        ], 0

    monkeypatch.setattr(connectors_route, "fetch_github_items", fake_fetch)
    response = await client.post(
        "/api/v1/connectors/github/import",
        json={"user_id": "gh-user", "token": token, "repos": ["octo/demo"]},
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["created_count"] == 1
    assert body["connector"] == "github_token"
    assert token not in response.text

    async def failing_fetch(*, token: str, repos: list[str] | None = None):
        raise GitHubImportError("令牌无效或已过期")

    monkeypatch.setattr(connectors_route, "fetch_github_items", failing_fetch)
    failed = await client.post(
        "/api/v1/connectors/github/import",
        json={"user_id": "gh-user", "token": token, "repos": []},
    )
    assert failed.status_code == 422
    assert "令牌无效" in failed.json()["detail"]
