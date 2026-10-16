from app.core.config import get_settings


async def test_required_auth_scopes_export_delete_and_audit(client, monkeypatch):
    monkeypatch.setenv("AUTH_MODE", "required")
    monkeypatch.setenv("AUTH_TOKEN_PEPPER", "test-pepper-with-enough-entropy")
    monkeypatch.setenv("AUTH_REGISTRATION_SECRET", "registration-secret")
    get_settings.cache_clear()

    missing_secret = await client.post(
        "/api/v1/auth/register", json={"user_id": "secure-user", "name": "owner"}
    )
    assert missing_secret.status_code == 403
    registered = await client.post(
        "/api/v1/auth/register",
        headers={"X-Registration-Secret": "registration-secret"},
        json={"user_id": "secure-user", "name": "owner"},
    )
    assert registered.status_code == 200
    owner_token = registered.json()["token"]
    owner_headers = {"Authorization": f"Bearer {owner_token}"}

    unauthenticated = await client.get(
        "/api/v1/evidence", params={"user_id": "secure-user"}
    )
    assert unauthenticated.status_code == 401

    imported = await client.post(
        "/api/v1/evidence/text",
        headers=owner_headers,
        json={"user_id": "secure-user", "content": "使用 Python 开发项目"},
    )
    assert imported.status_code == 201
    evidence_id = imported.json()["items"][0]["id"]

    limited = await client.post(
        "/api/v1/auth/tokens",
        headers=owner_headers,
        json={"user_id": "secure-user", "name": "reader", "scopes": ["read"]},
    )
    assert limited.status_code == 200
    reader_headers = {"Authorization": f"Bearer {limited.json()['token']}"}
    readable = await client.get(
        "/api/v1/evidence",
        headers=reader_headers,
        params={"user_id": "secure-user"},
    )
    assert readable.status_code == 200
    forbidden_delete = await client.delete(
        f"/api/v1/evidence/{evidence_id}", headers=reader_headers
    )
    assert forbidden_delete.status_code == 403

    exported = await client.get(
        "/api/v1/privacy/secure-user/export", headers=owner_headers
    )
    assert exported.status_code == 200
    assert exported.json()["evidence"][0]["id"] == evidence_id
    assert owner_token not in str(exported.json())
    assert "token_hash" not in str(exported.json())

    deleted = await client.delete(
        f"/api/v1/evidence/{evidence_id}", headers=owner_headers
    )
    assert deleted.status_code == 200
    assert deleted.json()["deleted"] is True
    assert (
        await client.get(f"/api/v1/evidence/{evidence_id}", headers=owner_headers)
    ).status_code == 404

    audit = await client.get(
        "/api/v1/privacy/secure-user/audit", headers=owner_headers
    )
    assert audit.status_code == 200
    assert {item["action"] for item in audit.json()} >= {
        "user_data.exported",
        "evidence.deleted",
    }

    monkeypatch.setenv("AUTH_MODE", "disabled")
    monkeypatch.setenv("AUTH_TOKEN_PEPPER", "change-me-in-production")
    monkeypatch.delenv("AUTH_REGISTRATION_SECRET")
    get_settings.cache_clear()


async def test_account_deletion_removes_tokens_evidence_and_threads(client, monkeypatch):
    monkeypatch.setenv("AUTH_MODE", "required")
    monkeypatch.setenv("AUTH_TOKEN_PEPPER", "account-delete-test-pepper")
    monkeypatch.setenv("AUTH_REGISTRATION_SECRET", "registration-secret")
    get_settings.cache_clear()

    registered = await client.post(
        "/api/v1/auth/register",
        headers={"X-Registration-Secret": "registration-secret"},
        json={"user_id": "delete-user", "name": "owner"},
    )
    token = registered.json()["token"]
    headers = {"Authorization": f"Bearer {token}"}
    imported = await client.post(
        "/api/v1/evidence/text",
        headers=headers,
        json={"user_id": "delete-user", "content": "使用 Python 和 FastAPI 开发项目"},
    )
    assert imported.status_code == 201
    assert (
        await client.post("/api/v1/profiles/delete-user/rebuild", headers=headers)
    ).status_code == 200
    chat = await client.post(
        "/api/v1/chat",
        headers=headers,
        json={"user_id": "delete-user", "message": "我的 Python 能力有哪些证据？"},
    )
    assert chat.status_code == 200

    deleted = await client.delete("/api/v1/privacy/delete-user", headers=headers)
    assert deleted.status_code == 200
    payload = deleted.json()
    assert payload["deleted"] is True
    assert payload["receipt_id"]
    assert payload["deleted_counts"]["evidence"] == 1
    assert payload["deleted_counts"]["profile_items"] >= 2
    assert payload["deleted_counts"]["conversation_threads"] == 1
    assert payload["deleted_counts"]["access_tokens"] == 1
    assert payload["checkpoint_result"] == {"status": "deleted", "deleted": 1}
    assert "delete-user" not in str(payload)
    assert "Python" not in str(payload)

    rejected = await client.get(
        "/api/v1/evidence", headers=headers, params={"user_id": "delete-user"}
    )
    assert rejected.status_code == 401
    registered_again = await client.post(
        "/api/v1/auth/register",
        headers={"X-Registration-Secret": "registration-secret"},
        json={"user_id": "delete-user", "name": "new-owner"},
    )
    assert registered_again.status_code == 200

    monkeypatch.setenv("AUTH_MODE", "disabled")
    monkeypatch.setenv("AUTH_TOKEN_PEPPER", "change-me-in-production")
    monkeypatch.delenv("AUTH_REGISTRATION_SECRET")
    get_settings.cache_clear()
