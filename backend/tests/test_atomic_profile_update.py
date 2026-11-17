from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.database import Base
from app.models import Evidence, ProfileItem, ProfileUpdateProposal
from app.services.profile_updates import decide_proposal


async def test_approved_update_commits_evidence_and_profile_together(monkeypatch):
    """F07 regression: evidence and profile changes share one transaction.

    If the profile-write phase fails, no 'user_correction' evidence may be left
    committed behind. This test forces a failure mid-approval and checks the DB.
    """
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    proposal_id = "proposal-atomic-1"
    async with factory() as session:
        session.add(
            ProfileUpdateProposal(
                id=proposal_id,
                user_id="atomic-user",
                message="我现在也做 Rust 开发",
                changes=[
                    {
                        "action": "upsert",
                        "category": "skill",
                        "name": "Rust",
                        "level": 3,
                        "confidence": 0.9,
                    }
                ],
                status="pending",
            )
        )
        await session.commit()

    import app.services.profile_updates as pu

    real_create = pu.create_evidence_chunks

    async def failing_create(session, **kwargs):
        await real_create(session, **kwargs)
        assert kwargs.get("commit") is False, "evidence must not self-commit here"
        raise RuntimeError("simulated profile-write failure")

    monkeypatch.setattr(pu, "create_evidence_chunks", failing_create)

    async with factory() as session:
        try:
            await decide_proposal(session, proposal_id=proposal_id, approve=True)
        except RuntimeError:
            pass
        await session.rollback()

    async with factory() as session:
        leftover = list(
            await session.scalars(
                select(Evidence).where(Evidence.user_id == "atomic-user")
            )
        )
        assert leftover == [], "no user_correction evidence should remain after rollback"
        profiles = list(
            await session.scalars(
                select(ProfileItem).where(ProfileItem.user_id == "atomic-user")
            )
        )
        assert profiles == [], "no profile item should remain after rollback"

    await engine.dispose()
