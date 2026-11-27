import os
from uuid import uuid4

import pytest
from sqlalchemy import event, select, update

from app.core.config import Settings, get_settings
from app.graph.career import build_career_graph
from app.models.account_deletion import AccountDeletionReceipt, DeletionWork
from app.models.conversation import ConversationThread
from app.runtime.deletion_work import process_deletion_work
from app.security import Principal
from app.services.privacy import delete_user_account, deletion_receipt


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
    assert payload["checkpoint_result"] == {"status": "deleted", "deleted": 0}
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
    assert registered_again.status_code == 410

    monkeypatch.setenv("AUTH_MODE", "disabled")
    monkeypatch.setenv("AUTH_TOKEN_PEPPER", "change-me-in-production")
    monkeypatch.delenv("AUTH_REGISTRATION_SECRET")
    get_settings.cache_clear()

async def test_deletion_receipt_without_registered_collections_is_completed(
    session_factory, monkeypatch,
):
    """Local/hash deployments have no external vector store to clean.

    The receipt must not stay stuck at "unknown" when there is no vector work
    and no postgres checkpoint to drain.
    """
    settings = Settings(checkpoint_backend="memory", retrieval_backend="local")
    monkeypatch.setattr("app.services.privacy.get_settings", lambda: settings)
    async def no_collections(_session):
        return ()

    monkeypatch.setattr(
        "app.services.privacy.cleanup_collections",
        no_collections,
    )

    principal = Principal("local-only-owner", None, ("*",))
    async with session_factory() as session:
        receipt = await delete_user_account(session, principal=principal)
        assert receipt["cleanup_status"] == "completed"
        assert receipt["vector_result"]["status"] == "deleted"
        assert receipt["checkpoint_result"]["status"] == "deleted"

    async with session_factory() as session:
        record = await session.get(
            AccountDeletionReceipt, receipt["receipt_id"]
        )
        assert record is not None
        after = await deletion_receipt(session, record)
        assert after["cleanup_status"] == "completed"


async def test_deletion_receipt_retries_after_commit_failure_and_vector_outage(
    session_factory, monkeypatch,
):
    import app.runtime.deletion_work as cleanup

    calls = []
    settings = Settings(checkpoint_backend="memory", retrieval_backend="local")
    monkeypatch.setattr("app.services.privacy.get_settings", lambda: settings)
    monkeypatch.setattr("app.retrieval.generations.get_settings", lambda: settings)

    async def delete_vectors(user_id, *, collection):
        calls.append((user_id, collection))
        return {"status": "deleted" if len(calls) > 1 else "fallback"}

    def stop_commit(_session):
        raise RuntimeError("Synthetic commit failure")

    principal = Principal("cleanup-owner", None, ("*",))
    async with session_factory() as session:
        event.listen(session.sync_session, "before_commit", stop_commit, once=True)
        with pytest.raises(RuntimeError, match="Synthetic commit failure"):
            await delete_user_account(session, principal=principal)
        await session.rollback()
        assert (await session.scalars(select(DeletionWork))).all() == []
        assert (await session.scalars(select(AccountDeletionReceipt))).all() == []
    assert not calls

    async with session_factory() as session:
        receipt = await delete_user_account(session, principal=principal)
        assert receipt["cleanup_status"] == "pending"
    monkeypatch.setattr(cleanup, "delete_user_index", delete_vectors)
    assert await process_deletion_work(session_factory)
    async with session_factory.begin() as session:
        work = await session.scalar(select(DeletionWork))
        assert work.attempts == 1 and work.status == "pending" and work.last_error
        await session.execute(update(DeletionWork).values(ready_at=0))
    assert await process_deletion_work(session_factory)
    async with session_factory() as session:
        record = await session.get(AccountDeletionReceipt, receipt["receipt_id"])
        after = await deletion_receipt(session, record)
        assert after["cleanup_status"] == "completed"
        assert (await session.scalar(select(DeletionWork))).subject is None
    assert calls == [(principal.user_id, settings.qdrant_collection)] * 2


async def test_real_postgres_legacy_checkpoint_cleanup(session_factory, monkeypatch):
    url = os.getenv("CAREERLENS_TEST_CHECKPOINT_URL")
    if not url:
        pytest.skip("Set CAREERLENS_TEST_CHECKPOINT_URL for the disposable checkpoint database")
    from langgraph.checkpoint.base import empty_checkpoint
    from langgraph.checkpoint.postgres import PostgresSaver

    import app.graph.checkpoint as checkpoint_runtime

    settings = Settings(checkpoint_backend="postgres", checkpoint_database_url=url)
    monkeypatch.setattr(checkpoint_runtime, "get_settings", lambda: settings)
    monkeypatch.setattr("app.services.privacy.get_settings", lambda: settings)
    runtime = build_career_graph()
    assert runtime.checkpointer is False
    thread = str(uuid4())
    prior_config = {"configurable": {"thread_id": thread, "checkpoint_ns": ""}}
    with PostgresSaver.from_conn_string(url) as saver:
        saver.setup()
        saved = saver.put(prior_config, empty_checkpoint(), {"step": 0}, {})
        saver.put_writes(saved, [("answer", "synthetic-private-marker")], "legacy-task")
        prior = saver.get_tuple(prior_config)
        assert any(row[-1] == "synthetic-private-marker" for row in prior.pending_writes)

    async with session_factory.begin() as session:
        session.add(ConversationThread(user_id="legacy-thread-owner", thread_id=thread))
    async with session_factory() as session:
        receipt = await delete_user_account(
            session, principal=Principal("legacy-thread-owner", None, ("*",)),
        )
        assert receipt["checkpoint_result"]["status"] == "queued"
    # Allow the vector cleanup target to remain pending in this checkpoint test.
    async with session_factory.begin() as session:
        await session.execute(update(DeletionWork).where(DeletionWork.kind == "vector_user")
            .values(ready_at=2**40))
    assert await process_deletion_work(session_factory)
    with PostgresSaver.from_conn_string(url) as saver:
        assert saver.get_tuple(prior_config) is None
    async with session_factory() as session:
        record = await session.get(AccountDeletionReceipt, receipt["receipt_id"])
        after = await deletion_receipt(session, record)
        assert after["checkpoint_result"] == {"status": "deleted", "deleted": 1}
