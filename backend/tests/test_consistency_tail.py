"""Phase 1/D: report version atomicity, remove suppression, stale propagation."""

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.database import Base
from app.models.career_report import CareerReport
from app.models.profile import ProfileItem
from app.models.profile_suppression import ProfileSuppression
from app.services.profile import rebuild_profile
from app.services.profile_updates import decide_proposal


@pytest.mark.asyncio
async def test_remove_survives_rebuild():
    """A removed profile item stays removed after rebuilding from old evidence."""
    from app.models.evidence import Evidence
    from app.models.profile_update import ProfileUpdateProposal

    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async with factory() as session:
        session.add(
            Evidence(
                user_id="u",
                source_type="self_statement",
                source_name="goal",
                content="我的目标是从事 AI Agent 应用开发工作。",
                source_metadata={},
            )
        )
        await session.commit()
        built = await rebuild_profile(session, "u")
        agent_items = [item for item in built if "Agent" in item.name]
        assert agent_items
        target = agent_items[0]

        proposal = ProfileUpdateProposal(
            user_id="u",
            message="remove target",
            changes=[
                {
                    "action": "remove",
                    "category": target.category,
                    "name": target.name,
                    "level": 1,
                    "confidence": 1.0,
                }
            ],
        )
        session.add(proposal)
        await session.commit()
        await decide_proposal(session, proposal_id=proposal.id, approve=True)

        remaining = (
            await session.scalars(select(ProfileItem).where(ProfileItem.user_id == "u"))
        ).all()
        assert not any(item.name == target.name for item in remaining)

        # Rebuild again from the same evidence — the tombstone must hold.
        rebuilt = await rebuild_profile(session, "u")
        assert not any(item.name == target.name for item in rebuilt)
    await engine.dispose()


async def test_rebuild_marks_reports_stale(client):
    await client.post(
        "/api/v1/evidence/text",
        json={
            "user_id": "stale-user",
            "source_type": "self_statement",
            "content": "我熟悉 Python 和 LangGraph 职业检索。",
        },
    )
    await client.post("/api/v1/profiles/stale-user/rebuild")
    # Directly insert a fresh report for this user via the service's model.
    from app.core.database import get_session
    from app.main import app

    session_factory = app.dependency_overrides[get_session]
    gen = session_factory()
    session = await gen.__anext__()
    report = CareerReport(
        user_id="stale-user",
        job_analysis_id="n/a",
        version=1,
        title="t",
        content={},
        markdown="",
        is_stale=False,
    )
    session.add(report)
    await session.commit()
    await session.close()
    await gen.aclose()

    # Rebuild again — existing report must be marked stale.
    await client.post("/api/v1/profiles/stale-user/rebuild")
    gen = session_factory()
    session = await gen.__anext__()
    fresh = (
        await session.scalars(
            select(CareerReport).where(CareerReport.user_id == "stale-user")
        )
    ).all()
    assert fresh and all(item.is_stale for item in fresh)
    await session.close()
    await gen.aclose()


@pytest.mark.asyncio
async def test_report_version_unique_constraint_rejects_duplicate():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        session.add_all(
            [
                CareerReport(
                    user_id="u", job_analysis_id="j", version=1, title="a", content={}, markdown=""
                ),
                CareerReport(
                    user_id="u", job_analysis_id="j", version=1, title="b", content={}, markdown=""
                ),
            ]
        )
        with pytest.raises(IntegrityError):
            await session.commit()
    await engine.dispose()


@pytest.mark.asyncio
async def test_suppression_is_unique_and_persisted():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        session.add(
            ProfileSuppression(user_id="u", category="target_role", name="AI Agent")
        )
        await session.commit()
        count = await session.scalar(
            select(func.count()).select_from(ProfileSuppression)
        )
        assert count == 1
    await engine.dispose()
