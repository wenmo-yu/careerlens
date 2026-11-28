"""M8 MCP connector admission: default deny, namespace, config digest, revoke."""

import pytest

from app.runtime.agent import mcp_connectors as connector_service


@pytest.mark.asyncio
async def test_register_is_disabled_by_default_and_digest_is_stable(session_factory):
    async with session_factory() as session:
        record = await connector_service.register(
            session,
            user_id="u1",
            workspace_id="default",
            namespace="docs",
            allowed_tools=["search", "read"],
            required_scope="read",
        )
        assert record.state == "registered"
        assert record.revoked is False
        expected = connector_service.config_digest(
            namespace="docs", allowed_tools=["search", "read"], required_scope="read"
        )
        assert record.config_digest == expected
        # Name order does not change the digest.
        assert connector_service.config_digest(
            namespace="docs", allowed_tools=["read", "search"], required_scope="read"
        ) == expected

        allowed, reason = connector_service.admit(
            record, qualified_name="docs.search", caller_scopes={"read"}
        )
        assert allowed is False
        assert reason == "connector_disabled"


@pytest.mark.asyncio
async def test_admission_default_deny_matrix(session_factory):
    async with session_factory() as session:
        record = await connector_service.register(
            session,
            user_id="u1",
            workspace_id="default",
            namespace="docs",
            allowed_tools=["search"],
            required_scope="write",
        )
        await connector_service.set_state(
            session, user_id="u1", connector_id=record.id, state="enabled"
        )

        cases = [
            ("docs.search", {"write"}, None, True, "admitted"),
            ("docs.search", {"manage"}, None, True, "admitted"),
            ("other.search", {"write"}, None, False, "namespace_mismatch"),
            ("docs.read", {"write"}, None, False, "tool_not_allowed"),
            ("docs.search", {"read"}, None, False, "scope_insufficient"),
            ("docs.search", {"write"}, "stale-digest", False, "config_digest_mismatch"),
        ]
        for name, scopes, digest, expected, reason in cases:
            allowed, got = connector_service.admit(
                record,
                qualified_name=name,
                caller_scopes=scopes,
                config_digest_supplied=digest,
            )
            assert (allowed, got) == (expected, reason)


@pytest.mark.asyncio
async def test_model_supplied_identity_is_not_an_authority(session_factory):
    async with session_factory() as session:
        record = await connector_service.register(
            session,
            user_id="u1",
            workspace_id="default",
            namespace="docs",
            allowed_tools=["search"],
            required_scope="manage",
        )
        await connector_service.set_state(
            session, user_id="u1", connector_id=record.id, state="enabled"
        )
        # A caller with only read must not pass even if it claims manage.
        allowed, reason = connector_service.admit(
            record, qualified_name="docs.search", caller_scopes={"read"}
        )
        assert allowed is False
        assert reason == "scope_insufficient"


@pytest.mark.asyncio
async def test_revoke_is_explicit_deny_and_permanent(session_factory):
    async with session_factory() as session:
        record = await connector_service.register(
            session,
            user_id="u1",
            workspace_id="default",
            namespace="docs",
            allowed_tools=["search"],
            required_scope="read",
        )
        await connector_service.set_state(
            session, user_id="u1", connector_id=record.id, state="enabled"
        )
        revoked = await connector_service.revoke(
            session, user_id="u1", connector_id=record.id
        )
        assert revoked.state == "disabled"
        assert revoked.revoked is True
        allowed, reason = connector_service.admit(
            revoked, qualified_name="docs.search", caller_scopes={"read"}
        )
        assert allowed is False
        assert reason == "connector_disabled"
        with pytest.raises(connector_service.ConnectorConflict):
            await connector_service.set_state(
                session, user_id="u1", connector_id=record.id, state="enabled"
            )


@pytest.mark.asyncio
async def test_connector_is_user_scoped(session_factory):
    async with session_factory() as session:
        await connector_service.register(
            session,
            user_id="u1",
            workspace_id="default",
            namespace="docs",
            allowed_tools=["search"],
            required_scope="read",
        )
        assert await connector_service.list_connectors(session, user_id="u1")
        assert await connector_service.list_connectors(session, user_id="u2") == []
