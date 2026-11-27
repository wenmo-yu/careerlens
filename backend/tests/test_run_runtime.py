import asyncio
import json
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.orm import undefer

from app.core.config import Settings
from app.core.database import Base, get_session
from app.main import create_app
from app.models.career_report import CareerReport
from app.models.evidence import Evidence
from app.models.job_analysis import JobAnalysis
from app.models.run import AgentRun, EvidenceIndexWork, RunEvent, RunScope, RunStep
from app.models.wiki import WikiPage
from app.runtime import index_outbox, store, worker
from app.runtime.operations import parse_in_process
from app.security.auth import DELETED_ACCOUNT

JOB = {
    "operation": "job_analysis",
    "input": {"title": "Backend", "jd_text": "Python and Docker required."},
}
OWNER = "runtime-user"


@pytest.fixture
async def runtime(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{(tmp_path / 'runs.db').as_posix()}")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    application = create_app()

    async def session_override():
        async with factory() as session:
            yield session

    application.dependency_overrides[get_session] = session_override
    try:
        async with AsyncClient(
            transport=ASGITransport(app=application), base_url="http://test"
        ) as http:
            yield http, factory
    finally:
        await engine.dispose()


async def submit(http, payload=JOB, *, user=OWNER, key=None):
    return await http.post(
        "/api/v1/runs",
        json={"user_id": user, **payload},
        headers={"Idempotency-Key": key or str(uuid4())},
    )


async def snapshot(http, run_id, user=OWNER):
    response = await http.get(f"/api/v1/runs/{run_id}", params={"user_id": user})
    assert response.is_success, response.text
    return response.json()


async def action(http, run_id, operation, body=None):
    return await http.post(
        f"/api/v1/runs/{run_id}/{operation}", params={"user_id": OWNER}, json=body
    )


async def process(factory, owner="worker-one"):
    claim = await worker.tick(factory, owner)
    assert claim is not None
    await worker.perform(factory, claim)
    return claim


async def seed(http):
    response = await http.post("/api/v1/evidence/text", json={
        "user_id": OWNER, "content": "Built Python services using Docker.",
    })
    assert response.status_code == 201
    assert (await http.post(f"/api/v1/profiles/{OWNER}/rebuild")).status_code == 200
    return response.json()["items"][0]["id"]


async def count(factory, model):
    async with factory() as session:
        return await session.scalar(select(func.count()).select_from(model))


async def test_run_idempotency_and_conflicting_input(runtime):
    http, factory = runtime
    first, second = await asyncio.gather(
        submit(http, key="same-request"), submit(http, key="same-request")
    )
    assert {first.status_code, second.status_code} == {200, 202}
    assert first.json()["id"] == second.json()["id"]
    other = {**JOB, "input": {**JOB["input"], "title": "Other"}}
    assert (await submit(http, other, key="same-request")).status_code == 409
    assert await count(factory, AgentRun) == 1
    assert await count(factory, RunEvent) == 1


async def test_idempotency_keys_are_scoped_to_user(runtime):
    http, _ = runtime
    first = await submit(http, key="same")
    second = await submit(http, user="other-user", key="same")
    assert first.json()["id"] != second.json()["id"]
    assert await snapshot(http, second.json()["id"], user="other-user")


async def test_two_workers_only_claim_one_run_once(runtime):
    http, factory = runtime
    run_id = (await submit(http)).json()["id"]
    results = await asyncio.gather(worker.tick(factory, "first"), worker.tick(factory, "second"))
    claims = [claim for claim in results if claim]
    assert len(claims) == 1 and claims[0].run_id == run_id
    assert (await snapshot(http, run_id))["attempts"] == 1


async def test_dispatcher_serializes_each_user_but_allows_another(runtime):
    http, factory = runtime
    await submit(http)
    await submit(http)
    await submit(http, user="other-user")
    first = await worker.tick(factory, "first")
    second = await worker.tick(factory, "second")
    assert {first.user_id, second.user_id} == {OWNER, "other-user"}
    assert await worker.tick(factory, "third") is None


async def test_queue_limit_does_not_block_replay(runtime, monkeypatch):
    http, _ = runtime
    monkeypatch.setattr(store, "get_settings", lambda: Settings(run_pending_per_user=1))
    assert (await submit(http, key="first")).status_code == 202
    assert (await submit(http, key="first")).status_code == 200
    assert (await submit(http, key="second")).status_code == 429


async def test_approval_is_idempotent_releases_slot_and_conflicts_on_reversal(runtime):
    http, factory = runtime
    payload = {**JOB, "requires_confirmation": True}
    run_id = (await submit(http, payload)).json()["id"]
    assert (await snapshot(http, run_id))["status"] == "waiting_confirmation"
    assert await worker.tick(factory, "worker") is None
    for _ in range(2):
        allowed = await action(http, run_id, "decision", {"approve": True})
        assert allowed.status_code == 200
        assert allowed.json()["status"] == "queued"
    assert (await action(http, run_id, "decision", {"approve": False})).status_code == 409
    assert await count(factory, RunEvent) == 2


async def test_rejected_task_never_claimed(runtime):
    http, factory = runtime
    run_id = (await submit(http, {**JOB, "requires_confirmation": True})).json()["id"]
    rejected = await action(http, run_id, "decision", {"approve": False})
    assert rejected.json()["status"] == "cancelled"
    assert await worker.tick(factory, "worker") is None


async def test_expired_lease_restarts_with_new_fence(runtime, monkeypatch):
    http, factory = runtime
    await seed(http)
    run_id = (await submit(http)).json()["id"]
    clock = [100]
    monkeypatch.setattr(store, "now_seconds", lambda: clock[0])
    old = await worker.tick(factory, "old")
    clock[0] += 120
    new = await worker.tick(factory, "new")
    assert old.run_id == new.run_id == run_id
    assert new.token > old.token
    with pytest.raises(store.LeaseLost):
        await worker.execute(factory, old)
    await worker.perform(factory, new)
    row = await snapshot(http, run_id)
    assert row["status"] == "succeeded" and row["attempts"] == 2
    assert await count(factory, JobAnalysis) == 1


async def test_cancel_while_computing_fences_off_late_result(runtime, monkeypatch):
    http, factory = runtime
    run_id = (await submit(http)).json()["id"]
    ready = asyncio.Event()
    finish = asyncio.Event()
    writes = []

    async def prepare(*args, **kwargs):
        await kwargs["progress"]("report_writer", "running")
        ready.set()
        await finish.wait()

        async def saved(session):
            writes.append(session)
            return {}

        return saved

    monkeypatch.setattr(worker, "prepare_operation", prepare)
    task = asyncio.create_task(process(factory))
    await asyncio.wait_for(ready.wait(), 5)
    assert (await action(http, run_id, "cancel")).json()["status"] == "cancelled"
    finish.set()
    await task
    assert not writes
    assert (await snapshot(http, run_id))["status"] == "cancelled"
    steps = await http.get(f"/api/v1/runs/{run_id}/steps", params={"user_id": OWNER})
    assert steps.json()[0]["status"] == "cancelled"


async def test_browser_can_replay_sse_after_cursor(runtime):
    http, factory = runtime
    await seed(http)
    run_id = (await submit(http)).json()["id"]
    await process(factory)
    response = await http.get(f"/api/v1/runs/{run_id}/stream", params={"user_id": OWNER},
                              headers={"Last-Event-ID": "2"})
    assert response.headers["content-type"].startswith("text/event-stream")
    data = [
        json.loads(line[6:]) for line in response.text.splitlines() if line.startswith("data: ")
    ]
    assert data[0]["seq"] == 3
    assert [item["seq"] for item in data] == list(range(3, data[-1]["seq"] + 1))
    assert data[-1]["event_type"] == "run.succeeded"
    assert "Built Python" not in response.text


async def test_events_list_and_invalid_cursor(runtime):
    http, _ = runtime
    run_id = (await submit(http)).json()["id"]
    path = f"/api/v1/runs/{run_id}"
    event_list = await http.get(f"{path}/events", params={"user_id": OWNER, "after_seq": 1})
    assert event_list.json() == []
    ahead = await http.get(f"{path}/stream", params={"user_id": OWNER, "after_seq": 9})
    assert ahead.status_code == 409
    assert (await http.get(f"{path}/stream", params={"user_id": OWNER},
                           headers={"Last-Event-ID": "abc"})).status_code == 400


async def test_run_ids_do_not_allow_cross_user_access(runtime):
    http, _ = runtime
    run_id = (await submit(http)).json()["id"]
    for suffix in ("", "/steps", "/events", "/stream"):
        response = await http.get(
            f"/api/v1/runs/{run_id}{suffix}", params={"user_id": "other-user"}
        )
        assert response.status_code == 404
    assert (await http.post(f"/api/v1/runs/{run_id}/cancel",
                            params={"user_id": "other-user"})).status_code == 404


async def test_revoked_actor_cannot_commit_a_run(runtime, monkeypatch):
    from app.core.config import get_settings

    http, factory = runtime
    monkeypatch.setenv("AUTH_MODE", "required")
    monkeypatch.setenv("AUTH_REGISTRATION_SECRET", "test-registration")
    get_settings.cache_clear()
    try:
        registered = await http.post(
            "/api/v1/auth/register", json={"user_id": OWNER, "name": "test"},
            headers={"X-Registration-Secret": "test-registration"},
        )
        assert registered.is_success, registered.text
        http.headers["Authorization"] = f"Bearer {registered.json()['token']}"
        scoped = await http.post("/api/v1/auth/tokens", json={
            "user_id": OWNER, "name": "writer", "scopes": ["read", "write"],
        })
        assert scoped.is_success, scoped.text
        manager = http.headers["Authorization"]
        http.headers["Authorization"] = f"Bearer {scoped.json()['token']}"
        run_id = (await submit(http)).json()["id"]
        http.headers["Authorization"] = manager
        tokens = await http.get(f"/api/v1/auth/{OWNER}/tokens")
        token_id = next(row["id"] for row in tokens.json() if row["name"] == "writer")
        assert (await http.delete(f"/api/v1/auth/{OWNER}/tokens/{token_id}")).is_success
        await process(factory)
        assert (await snapshot(http, run_id))["error_code"] == "permission_revoked"
    finally:
        get_settings.cache_clear()


async def test_upload_parses_outside_worker_and_drops_raw_bytes(runtime):
    http, factory = runtime
    response = await http.post("/api/v1/runs/uploads", data={"user_id": OWNER},
                               files={"upload": ("skills.csv", b"Skill,Level\nPython,Advanced")})
    assert response.status_code == 202, response.text
    run_id = response.json()["id"]
    assert response.json()["result"] is None
    await process(factory)
    row = await snapshot(http, run_id)
    assert row["status"] == "succeeded" and row["result"]["count"] == 1
    async with factory() as session:
        run = await session.scalar(select(AgentRun).options(undefer(AgentRun.upload_bytes)))
        assert run.upload_bytes is None
    exported = (await http.get(f"/api/v1/privacy/{OWNER}/export")).json()
    assert exported["parsed_blocks"][0]["block_type"] == "table"


async def test_invalid_file_is_a_safe_terminal_failure(runtime):
    http, factory = runtime
    response = await http.post("/api/v1/runs/uploads", data={"user_id": OWNER},
                               files={"upload": ("unsupported.bin", b"not a format")})
    await process(factory)
    row = await snapshot(http, response.json()["id"])
    assert (row["status"], row["error_code"]) == ("failed", "invalid_input")
    assert await count(factory, Evidence) == 0


async def test_parser_preserves_utf8_and_table_content():
    result = await parse_in_process("file_import", "课程.csv", "课程,等级\n数据库,熟练".encode())
    assert "数据库" in result.blocks[0].content


async def test_newer_wiki_request_supersedes_uncommitted_work(runtime):
    http, factory = runtime
    evidence_id = await seed(http)
    wiki = {"operation": "wiki_compile", "input": {
        "slug": "skills", "title": "Skills", "evidence_ids": [evidence_id],
    }}
    original = (await submit(http, wiki)).json()["id"]
    stale = await worker.tick(factory, "worker")
    next_run = (await submit(http, wiki)).json()["id"]
    await worker.perform(factory, stale)
    assert (await snapshot(http, original))["error_code"] == "stale_input"
    await process(factory)
    assert (await snapshot(http, next_run))["result"]["wiki_slug"] == "skills"
    assert await count(factory, WikiPage) == 1


async def test_deleting_evidence_invalidates_queued_snapshot(runtime):
    http, factory = runtime
    evidence_id = await seed(http)
    run_id = (await submit(http)).json()["id"]
    await http.delete(f"/api/v1/evidence/{evidence_id}")
    await process(factory)
    assert (await snapshot(http, run_id))["status"] == "failed"
    assert await count(factory, JobAnalysis) == 0


async def test_account_deletion_erases_runs_steps_events_and_fences_worker(runtime):
    http, factory = runtime
    await seed(http)
    await submit(http)
    await process(factory)
    await submit(http)
    old = await worker.tick(factory, "late")
    deleted = await http.delete(f"/api/v1/privacy/{OWNER}")
    assert deleted.is_success
    assert deleted.json()["deleted_counts"]["runs"] == 2
    for model in (AgentRun, RunEvent, RunStep):
        assert await count(factory, model) == 0
    async with factory() as session:
        keys = set(await session.scalars(
            select(RunScope.key).where(RunScope.user_id == OWNER)
        ))
        assert keys == {store.INPUT, store.DELETION, DELETED_ACCOUNT}
    with pytest.raises(store.LeaseLost):
        await worker.execute(factory, old)


async def test_report_result_and_business_write_commit_once(runtime):
    http, factory = runtime
    await seed(http)
    job_id = (await submit(http)).json()["id"]
    await process(factory)
    analysis = (await snapshot(http, job_id))["result"]["job_analysis_id"]
    body = {"operation": "report", "input": {"job_analysis_id": analysis}}
    run_id = (await submit(http, body, key="report")).json()["id"]
    claim = await process(factory)
    await worker.perform(factory, claim)
    assert (await submit(http, body, key="report")).json()["id"] == run_id
    row = await snapshot(http, run_id)
    assert row["result"]["version"] == 1
    assert await count(factory, CareerReport) == 1
    assert (await http.get(f"/api/v1/reports/{row['result']['report_id']}")).is_success


async def test_failure_after_domain_flush_rolls_back_and_replays_once(runtime, monkeypatch):
    http, factory = runtime
    run_id = (await submit(http)).json()["id"]
    crashes = [True, False]

    async def prepare(*args, **kwargs):
        async def write_then_interrupt(session):
            record = JobAnalysis(
                user_id=OWNER, title="Backend", jd_text="Python required", score=0,
                requirements=[], matches=[], gaps=[], learning_path=[], report={},
            )
            session.add(record)
            await session.flush()
            if crashes.pop(0):
                raise RuntimeError("simulated worker fault after flush")
            return {"job_analysis_id": record.id}
        return write_then_interrupt

    monkeypatch.setattr(worker, "prepare_operation", prepare)
    await process(factory)
    assert (await snapshot(http, run_id))["status"] == "interrupted"
    assert await count(factory, JobAnalysis) == 0
    await process(factory)
    assert (await snapshot(http, run_id))["status"] == "succeeded"
    assert await count(factory, JobAnalysis) == 1


async def test_expired_waiting_upload_is_removed_without_running_parser(runtime):
    http, factory = runtime
    response = await http.post(
        "/api/v1/runs/uploads", data={"user_id": OWNER, "requires_confirmation": "true"},
        files={"upload": ("sample.csv", b"Skill,Level\nPython,Advanced")},
    )
    run_id = response.json()["id"]
    async with factory.begin() as session:
        await session.execute(
            update(AgentRun).where(AgentRun.id == run_id)
            .values(created_at=datetime.now(UTC) - timedelta(days=2))
        )
    assert await worker.tick(factory, "worker") is None
    assert (await snapshot(http, run_id))["error_code"] == "run_expired"
    async with factory() as session:
        row = await session.scalar(select(AgentRun).options(undefer(AgentRun.upload_bytes)))
        assert row.upload_bytes is None


async def test_coordinator_projects_context_and_rejects_foreign_citations(monkeypatch):
    from app.runtime import agents

    progress = []
    inherited = []

    async def event(name, state, **data):
        progress.append((name, state, data))

    async def inspect_projection(projected):
        inherited.append(projected)
        return {"requirements": [], "diagnostics": {}}

    project, _ = agents.SPECIALISTS["requirement_analyst"]
    monkeypatch.setitem(
        agents.SPECIALISTS, "requirement_analyst", (project, agents.specialist(inspect_projection))
    )
    coordinator = agents.Coordinator(event)
    await coordinator.delegate(
        "requirement_analyst", {"jd_text": "Python required", "user_secret": "do not forward"}
    )
    assert inherited == [{"jd_text": "Python required"}]
    with pytest.raises(ValueError, match="outside"):
        await coordinator.verify({"mine"}, ["not-in-scope"])
    assert all("not-in-scope" not in repr(info) for info in progress)
    with pytest.raises(ValueError, match="budget"):
        await coordinator.verify({"mine"}, ["mine"])


async def test_index_outbox_retries_and_delete_supersedes_upsert(runtime, monkeypatch):
    http, factory = runtime
    monkeypatch.setattr(index_outbox, "get_settings", lambda: Settings(retrieval_backend="qdrant"))
    attempted = []

    async def unavailable(records, *, strict=False):
        attempted.append(("upsert", records[0].id))
        raise RuntimeError

    async def deleted(evidence_id, *, strict=False, collections=None):
        attempted.append(("delete", evidence_id))
        return {"status": "deleted"}

    monkeypatch.setattr(index_outbox, "index_evidence", unavailable)
    monkeypatch.setattr(index_outbox, "delete_evidence_index", deleted)
    evidence_id = await seed(http)
    async with factory() as session:
        work = await session.get(EvidenceIndexWork, evidence_id)
        assert work.attempts == 1 and work.ready_at > 0
    response = await http.delete(f"/api/v1/evidence/{evidence_id}")
    assert response.is_success
    assert attempted == [("upsert", evidence_id), ("delete", evidence_id)]
    assert await count(factory, EvidenceIndexWork) == 0


async def test_index_outbox_replays_when_vector_store_recovers(runtime, monkeypatch):
    http, factory = runtime
    monkeypatch.setattr(index_outbox, "get_settings", lambda: Settings(retrieval_backend="qdrant"))
    ready = False

    async def fake_index(records, *, strict=False):
        if not ready:
            raise RuntimeError
        return {"status": "ok"}

    monkeypatch.setattr(index_outbox, "index_evidence", fake_index)
    await seed(http)
    ready = True
    async with factory.begin() as session:
        await session.execute(update(EvidenceIndexWork).values(ready_at=0))
        assert await index_outbox.process_index_work(session)
    assert await count(factory, EvidenceIndexWork) == 0
