"""M6 team trees and M8 durable schedule gates."""

from sqlalchemy import select

from app.models.evidence import Evidence
from app.models.multi import AgentTask
from app.models.run import AgentRun
from app.models.schedule import AgentScheduleOccurrence
from app.runtime.agent import multi, store
from app.runtime.agent import schedule as schedule_service
from app.runtime.agent.scheduler import AgentScheduler, SchedulerConfig


async def test_team_creates_isolated_child_sessions_and_runs(client):
    response = await client.post(
        "/api/v1/agent/teams",
        json={
            "user_id": "team-user",
            "title": "岗位材料复核",
            "children": [
                {"role": "researcher", "input": "检索 Docker 证据"},
                {"role": "reviewer", "input": "检查证据是否充分"},
                {"role": "synthesizer", "input": "汇总结论"},
            ],
        },
    )
    assert response.status_code == 201, response.text
    team_id = response.json()["team_id"]

    tasks = await client.get(
        f"/api/v1/agent/teams/{team_id}/tasks", params={"user_id": "team-user"}
    )
    assert tasks.status_code == 200
    rows = tasks.json()
    assert len(rows) == 4
    parent = next(row for row in rows if row["parent_id"] is None)
    children = [row for row in rows if row["parent_id"] == parent["id"]]
    assert len(children) == 3
    assert len({row["session_id"] for row in children}) == 3
    assert len({row["run_id"] for row in children}) == 3
    assert all(row["status"] == "queued" for row in children)
    assert parent["status"] == "waiting"


async def test_team_mail_is_idempotent_and_rejects_key_reuse(client):
    team = await client.post(
        "/api/v1/agent/teams",
        json={
            "user_id": "mail-user",
            "title": "团队邮箱",
            "children": [{"role": "researcher", "input": "查证据"}],
        },
    )
    team_id = team.json()["team_id"]
    body = {
        "user_id": "mail-user",
        "message_key": "finding-1",
        "payload": {"summary": "找到两条证据"},
        "citations": ["ev-1"],
    }
    first = await client.post(f"/api/v1/agent/teams/{team_id}/messages", json=body)
    assert first.status_code == 201
    second = await client.post(f"/api/v1/agent/teams/{team_id}/messages", json=body)
    assert second.status_code == 201
    assert first.json()["id"] == second.json()["id"]

    reused = await client.post(
        f"/api/v1/agent/teams/{team_id}/messages",
        json={**body, "payload": {"summary": "不同内容"}},
    )
    assert reused.status_code == 409

    mail = await client.get(
        f"/api/v1/agent/teams/{team_id}/messages", params={"user_id": "mail-user"}
    )
    assert len(mail.json()) == 1


async def test_cancel_parent_cancels_children_and_runs(client):
    team = await client.post(
        "/api/v1/agent/teams",
        json={
            "user_id": "cancel-user",
            "title": "取消整棵树",
            "children": [
                {"role": "researcher", "input": "A"},
                {"role": "reviewer", "input": "B"},
            ],
        },
    )
    parent_id = team.json()["parent_task_id"]
    cancelled = await client.post(
        f"/api/v1/agent/tasks/{parent_id}/cancel", params={"user_id": "cancel-user"}
    )
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "cancelled"

    tasks = await client.get(
        f"/api/v1/agent/teams/{team.json()['team_id']}/tasks",
        params={"user_id": "cancel-user"},
    )
    assert all(row["status"] == "cancelled" for row in tasks.json() if row["parent_id"])


async def test_result_projection_verifies_citations(session_factory):
    async with session_factory.begin() as session:
        parent, children = await multi.create_team(
            session,
            user_id="citation-user",
            workspace_id="default",
            title="引用校验",
            inputs=[{"role": "researcher", "input": "检索"}],
            token_id=None,
        )
        child = children[0]
        session.add(
            Evidence(
                id="ev-live",
                user_id="citation-user",
                source_type="self_statement",
                source_name="synthetic",
                content="有效证据",
            )
        )
        child.result = {
            "text": "结论 " * 1000,
            "citations": ["ev-live", "ev-deleted"],
        }
        await session.flush()
        projection = await multi.project_result(session, user_id="citation-user", task=child)
        assert projection["citations"] == ["ev-live"]
        assert projection["unverified_citations"] == ["ev-deleted"]
        assert projection["truncated"] is True
        assert len(projection["text"]) == 2000


async def test_schedule_trigger_is_idempotent_and_disable_stops_it(client):
    created = await client.post(
        "/api/v1/agent/schedules",
        json={
            "user_id": "plan-user",
            "name": "每小时复盘",
            "prompt": "回顾今天的证据缺口",
            "interval_seconds": 3600,
            "start_at": 1000,
        },
    )
    assert created.status_code == 201, created.text
    schedule_id = created.json()["id"]

    first = await client.post(
        f"/api/v1/agent/schedules/{schedule_id}/trigger",
        params={"user_id": "plan-user", "now": 1000},
    )
    second = await client.post(
        f"/api/v1/agent/schedules/{schedule_id}/trigger",
        params={"user_id": "plan-user", "now": 1000},
    )
    assert first.status_code == 200 and second.status_code == 200
    assert first.json()["id"] == second.json()["id"]
    assert first.json()["status"] == "claimed"

    listed = await client.get(
        "/api/v1/agent/schedules", params={"user_id": "plan-user"}
    )
    assert listed.status_code == 200
    assert listed.json()[0]["next_due"] > 1000

    paused = await client.post(
        f"/api/v1/agent/schedules/{schedule_id}/state",
        json={"user_id": "plan-user", "state": "paused"},
    )
    assert paused.status_code == 200
    blocked = await client.post(
        f"/api/v1/agent/schedules/{schedule_id}/trigger",
        params={"user_id": "plan-user", "now": 5000},
    )
    assert blocked.status_code == 409


async def test_scheduler_syncs_child_result_and_projects_parent(session_factory):
    async with session_factory.begin() as session:
        parent, children = await multi.create_team(
            session,
            user_id="sync-user",
            workspace_id="default",
            title="自动投影",
            inputs=[{"role": "researcher", "input": "查证据"}],
            token_id=None,
        )
        child = children[0]
        session.add(
            Evidence(
                id="ev-1",
                user_id="sync-user",
                source_type="self_statement",
                source_name="synthetic",
                content="有效证据",
            )
        )
        run = await session.get(AgentRun, child.run_id)
        run.status = "succeeded"
        run.result = {
            "message": "找到一条证据",
            "citations": [{"evidence_id": "ev-1"}],
            "usage": {"output_tokens": 2},
        }
        claim = store.AgentClaim(
            run_id=run.id,
            user_id="sync-user",
            session_id=child.session_id,
            owner="scheduler",
            attempt=1,
            fencing_token=1,
            text="查证据",
        )
    scheduler = AgentScheduler(session_factory, config=SchedulerConfig())
    await scheduler._sync_task(claim)
    async with session_factory() as session:
        refreshed = await session.get(AgentTask, parent.id)
        assert refreshed.status == "succeeded"
        assert refreshed.result["children"][0]["text"] == "找到一条证据"
        assert refreshed.result["children"][0]["citations"] == ["ev-1"]


async def test_scheduler_tick_triggers_due_schedules(session_factory):
    async with session_factory.begin() as session:
        await schedule_service.create_schedule(
            session,
            user_id="tick-user",
            workspace_id="default",
            name="周期触发",
            prompt="检查任务",
            interval_seconds=3600,
            actor_token_id=None,
            start_at=schedule_service.now_seconds() - 10,
        )
    scheduler = AgentScheduler(
        session_factory,
        config=SchedulerConfig(max_running=0, warm_target=0, warm_max=0, total_cap=1),
    )
    await scheduler.tick()
    async with session_factory() as session:
        occurrences = list(
            await session.scalars(
                select(AgentScheduleOccurrence).where(
                    AgentScheduleOccurrence.user_id == "tick-user"
                )
            )
        )
    assert len(occurrences) == 1
    assert occurrences[0].status == "claimed"


async def test_misfire_policy_skips_stale_occurrences(session_factory):
    async with session_factory.begin() as session:
        record = await schedule_service.create_schedule(
            session,
            user_id="miss-user",
            workspace_id="default",
            name="错过策略",
            prompt="检查计划",
            interval_seconds=60,
            misfire_policy="skip",
            actor_token_id=None,
            start_at=1000,
        )
        occurrence = await schedule_service.trigger(
            session, user_id="miss-user", schedule_id=record.id, now=10_000
        )
        assert occurrence is not None
        assert occurrence.status == "skipped"
        assert occurrence.reason == "misfire_skipped"
        assert record.next_due > 10_000
        assert record.last_occurrence == 1000
