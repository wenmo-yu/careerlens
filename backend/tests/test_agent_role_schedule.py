"""M8 role-schedule linkage: bound triggers inherit role prompt/tools/session."""

import pytest
from sqlalchemy import select
from sqlalchemy.orm import undefer

from app.models.run import AgentRun
from app.runtime.agent import roles as role_service
from app.runtime.agent import schedule as schedule_service


async def _load_run(session, run_id):
    # payload is deferred; load it explicitly in the async session.
    return await session.scalar(
        select(AgentRun).where(AgentRun.id == run_id).options(undefer(AgentRun.payload))
    )


@pytest.mark.asyncio
async def test_bound_schedule_trigger_uses_role_session_prompt_and_snapshot(session_factory):
    async with session_factory() as session:
        role = await role_service.create_role(
            session,
            user_id="u1",
            workspace_id="default",
            name="weekly-reviewer",
            template="career_coach",
            prompt="复盘本周学习进度",
            tool_allowlist=["search_evidence"],
            actor_token_id=None,
        )
        schedule = await schedule_service.create_schedule(
            session,
            user_id="u1",
            workspace_id="default",
            name="每周复盘",
            prompt="这条 prompt 应被角色覆盖",
            interval_seconds=3600,
            actor_token_id=None,
            role_id=role.id,
        )
        assert schedule.role_id == role.id

        occurrence = await schedule_service.trigger(
            session, user_id="u1", schedule_id=schedule.id, now=1000, manual=True
        )
        assert occurrence.status == "claimed"
        assert occurrence.role_version == role.version

        run = await _load_run(session, occurrence.run_id)
        assert run.session_id == role.session_id
        snapshot = (run.payload or {}).get("role") or {}
        assert snapshot["role_id"] == role.id
        assert snapshot["role_version"] == role.version
        assert snapshot["tool_allowlist"] == ["search_evidence"]


@pytest.mark.asyncio
async def test_unbound_schedule_keeps_its_own_prompt_and_session(session_factory):
    async with session_factory() as session:
        schedule = await schedule_service.create_schedule(
            session,
            user_id="u1",
            workspace_id="default",
            name="普通计划",
            prompt="使用我自己的 prompt",
            interval_seconds=3600,
            actor_token_id=None,
        )
        occurrence = await schedule_service.trigger(
            session, user_id="u1", schedule_id=schedule.id, now=1000, manual=True
        )
        assert occurrence.role_version is None
        run = await _load_run(session, occurrence.run_id)
        assert run.session_id != "" and (run.payload or {}).get("role") is None


@pytest.mark.asyncio
async def test_inactive_role_rejects_schedule_trigger(session_factory):
    async with session_factory() as session:
        role = await role_service.create_role(
            session,
            user_id="u1",
            workspace_id="default",
            name="paused-role",
            template="career_coach",
            prompt=None,
            tool_allowlist=None,
            actor_token_id=None,
        )
        schedule = await schedule_service.create_schedule(
            session,
            user_id="u1",
            workspace_id="default",
            name="绑定暂停角色",
            prompt="x",
            interval_seconds=3600,
            actor_token_id=None,
            role_id=role.id,
        )
        await role_service.set_state(session, user_id="u1", role_id=role.id, state="paused")
        with pytest.raises(schedule_service.ScheduleConflict) as exc:
            await schedule_service.trigger(
                session, user_id="u1", schedule_id=schedule.id, now=1000, manual=True
            )
        assert "role_not_found" in str(exc.value)


@pytest.mark.asyncio
async def test_create_schedule_rejects_foreign_role(session_factory):
    async with session_factory() as session:
        role = await role_service.create_role(
            session,
            user_id="owner",
            workspace_id="default",
            name="foreign",
            template="career_coach",
            prompt=None,
            tool_allowlist=None,
            actor_token_id=None,
        )
        with pytest.raises(schedule_service.ScheduleConflict):
            await schedule_service.create_schedule(
                session,
                user_id="attacker",
                workspace_id="default",
                name="x",
                prompt="y",
                interval_seconds=3600,
                actor_token_id=None,
                role_id=role.id,
            )
