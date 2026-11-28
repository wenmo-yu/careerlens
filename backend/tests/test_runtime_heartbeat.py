"""Liveness is derived from explicit heartbeats, not process existence."""

from app.models.heartbeat import RuntimeHeartbeat
from app.runtime import heartbeat


async def test_heartbeat_upsert_and_staleness(session_factory):
    async with session_factory.begin() as session:
        await heartbeat.beat(session, "worker", "instance-a")
        status = await heartbeat.read_status(session, stale_after_seconds=30, now=1000)
        assert status["worker"]["healthy"] is True
        assert status["worker"]["instance_id"] == "instance-a"
        assert status["worker"]["age_seconds"] == 0
        assert status["scheduler"]["state"] == "not_started"

        await heartbeat.beat(session, "worker", "instance-b")
        record = await session.get(RuntimeHeartbeat, "worker")
        record.heartbeat_at = 900
        await session.flush()
        status = await heartbeat.read_status(session, stale_after_seconds=30, now=1000)
        assert status["worker"]["healthy"] is False
        assert status["worker"]["state"] == "stale"
        assert status["worker"]["age_seconds"] == 100
        assert status["worker"]["instance_id"] == "instance-b"


async def test_heartbeat_rejects_unknown_role(session_factory):
    async with session_factory.begin() as session:
        try:
            await heartbeat.beat(session, "api", "instance-a")
        except ValueError as exc:
            assert "Unknown heartbeat role" in str(exc)
        else:
            raise AssertionError("unknown heartbeat role must be rejected")
