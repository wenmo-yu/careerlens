"""M8 in-app inbox and search: derived facts, idempotent reads, user isolation."""

import pytest

from app.models.agent import AgentApproval, AgentSession
from app.models.multi import AgentTask
from app.models.role import AgentRole
from app.models.run import AgentRun
from app.models.schedule import AgentSchedule, AgentScheduleOccurrence
from app.runtime.agent import inbox as inbox_service


@pytest.mark.asyncio
async def test_inbox_derives_pending_approval_and_read_is_idempotent(session_factory):
    async with session_factory() as session:
        approval = AgentApproval(
            run_id="r1",
            user_id="u1",
            invocation_id="inv-1",
            tool="save_career_note",
            args_digest="d",
            status="pending",
        )
        session.add(approval)
        await session.flush()

        items = await inbox_service.list_notifications(session, user_id="u1")
        assert any(item["kind"] == "approval_pending" for item in items)
        assert all(item["read"] is False for item in items)

        key = f"approval:{approval.id}"
        assert await inbox_service.mark_read(session, user_id="u1", fact_keys=[key]) == 1
        assert await inbox_service.mark_read(session, user_id="u1", fact_keys=[key]) == 0
        items = await inbox_service.list_notifications(session, user_id="u1")
        target = next(item for item in items if item["fact_key"] == key)
        assert target["read"] is True


@pytest.mark.asyncio
async def test_inbox_derives_failed_run_task_and_skipped_occurrence(session_factory):
    async with session_factory() as session:
        session.add(
            AgentRun(
                user_id="u1",
                operation="agent_turn",
                request_key="k1",
                request_hash="h1",
                executor_kind="agent",
                status="failed",
                error_code="model_unavailable",
            )
        )
        session.add(
            AgentTask(
                user_id="u1",
                workspace_id="default",
                team_id="t1",
                role="researcher",
                title="子任务",
                input="x",
                status="failed",
                error="boom",
            )
        )
        schedule = AgentSchedule(
            user_id="u1",
            workspace_id="default",
            name="复盘",
            prompt="p",
            interval_seconds=3600,
            next_due=100,
        )
        session.add(schedule)
        await session.flush()
        session.add(
            AgentScheduleOccurrence(
                schedule_id=schedule.id,
                user_id="u1",
                due_at=100,
                status="skipped",
                reason="misfire_skipped",
            )
        )
        await session.flush()

        kinds = {
            item["kind"]
            for item in await inbox_service.list_notifications(session, user_id="u1")
        }
        assert "run_failed" in kinds
        assert "task_failed" in kinds
        assert "schedule_skipped" in kinds


@pytest.mark.asyncio
async def test_inbox_is_user_isolated(session_factory):
    async with session_factory() as session:
        session.add(
            AgentRun(
                user_id="u1",
                operation="agent_turn",
                request_key="k1",
                request_hash="h1",
                executor_kind="agent",
                status="failed",
            )
        )
        await session.flush()
        u1_items = await inbox_service.list_notifications(session, user_id="u1")
        u2_items = await inbox_service.list_notifications(session, user_id="u2")
        assert len(u1_items) == 1
        assert u2_items == []


@pytest.mark.asyncio
async def test_search_is_read_only_and_user_scoped(session_factory):
    async with session_factory() as session:
        session.add(AgentSession(user_id="u1", title="Docker 学习会话", workspace_id="default"))
        session.add(
            AgentTask(
                user_id="u1", workspace_id="default", team_id="t1", role="researcher",
                title="分析 JD", input="x", status="succeeded",
            )
        )
        session.add(
            AgentRole(
                user_id="u1", workspace_id="default", name="职业教练", template="career_coach",
                version=1, prompt="p", tool_allowlist=[], state="active",
            )
        )
        session.add(
            AgentSchedule(
                user_id="u1", workspace_id="default", name="每周复盘", prompt="p",
                interval_seconds=3600, next_due=100,
            )
        )
        # Another user's session must never leak.
        session.add(AgentSession(user_id="u2", title="Docker 私密", workspace_id="default"))
        await session.flush()

        result = await inbox_service.search(session, user_id="u1", query="Docker")
        assert len(result["sessions"]) == 1
        assert result["sessions"][0]["title"] == "Docker 学习会话"

        jd = await inbox_service.search(session, user_id="u1", query="JD")
        assert len(jd["tasks"]) == 1

        with pytest.raises(ValueError):
            await inbox_service.search(session, user_id="u1", query="")
