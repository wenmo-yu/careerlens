"""HY4-B: profile overview is a read-only descriptor of stored data."""

from datetime import UTC, datetime

from app.models.evidence import Evidence
from app.models.profile import ProfileItem
from app.models.profile_suppression import ProfileSuppression
from app.models.source_document import SourceDocument
from app.services.profile_overview import build_agent_manifest, build_profile_overview


def _evidence(evidence_id: str, user_id: str, content: str = "Python 项目经验") -> Evidence:
    return Evidence(
        id=evidence_id,
        user_id=user_id,
        source_type="self_statement",
        source_name="test",
        content=content,
        content_hash=evidence_id,
        created_at=datetime.now(UTC),
    )


async def test_overview_empty_user(session_factory):
    async with session_factory() as session:
        overview = await build_profile_overview(session, "empty-user")
    assert overview.evidence_count == 0
    assert overview.profile_item_count == 0
    assert overview.coverage.supported == 0
    assert "methodology" in overview.model_dump()


async def test_overview_counts_evidence_documents_and_coverage(session_factory):
    user_id = "overview-user"
    async with session_factory() as session:
        session.add_all([
            _evidence("e1", user_id, "Python 项目经验"),
            _evidence("e2", user_id, "FastAPI 服务部署"),
            SourceDocument(
                id="doc1", user_id=user_id, source_hash="hash1", filename="cv.pdf",
                source_type="resume", file_size=100, parse_status="parsed",
            ),
            ProfileItem(
                id="p1", user_id=user_id, category="skill", name="Python", level=4,
                confidence=0.9, evidence_ids=["e1", "e2"], details={},
            ),
            ProfileItem(
                id="p2", user_id=user_id, category="skill", name="FastAPI", level=2,
                confidence=0.6, evidence_ids=["e2"], details={},
            ),
            ProfileItem(
                id="p3", user_id=user_id, category="target_role", name="AI Agent 开发",
                level=3, confidence=0.8, evidence_ids=["deleted-id"],
                details={"source": "confirmed_user_update"},
            ),
        ])
        await session.commit()
        overview = await build_profile_overview(session, user_id)

    assert overview.evidence_count == 2
    assert overview.source_document_count == 1
    assert overview.readable_evidence_count == 2
    assert overview.profile_item_count == 3
    assert overview.confirmed_item_count == 1
    assert overview.unconfirmed_item_count == 2
    assert overview.coverage.supported == 1
    assert overview.coverage.weak == 1
    assert overview.coverage.missing == 1
    assert overview.by_category == {"skill": 2, "target_role": 1}


async def test_overview_excludes_ocr_pending_from_readable(session_factory):
    user_id = "overview-ocr"
    record = _evidence("e-ocr", user_id)
    record.content = ""
    record.source_metadata = {"ocr_pending": True}
    async with session_factory() as session:
        session.add(record)
        await session.commit()
        overview = await build_profile_overview(session, user_id)
    assert overview.evidence_count == 1
    assert overview.readable_evidence_count == 0


async def test_coverage_changes_when_evidence_is_removed(session_factory):
    user_id = "overview-delete"
    async with session_factory() as session:
        session.add_all([
            _evidence("e-keep", user_id),
            _evidence("e-drop", user_id),
            ProfileItem(
                id="p-two", user_id=user_id, category="skill", name="Python", level=4,
                confidence=0.9, evidence_ids=["e-keep", "e-drop"], details={},
            ),
        ])
        await session.commit()
        before = await build_profile_overview(session, user_id)
        assert before.coverage.supported == 1

        await session.delete(await session.get(Evidence, "e-drop"))
        await session.commit()
        after = await build_profile_overview(session, user_id)

    assert after.coverage.supported == 0
    assert after.coverage.weak == 1
    assert after.evidence_count == 1


async def test_profile_id_is_not_a_long_term_anchor(client, session_factory):
    """A rebuild rewrites ProfileItem ids; overview must not depend on them."""
    user_id = "overview-rebuild"
    response = await client.post(
        "/api/v1/evidence/text",
        json={"user_id": user_id, "content": "我用 Python 与 FastAPI 构建过 Agent 服务。"},
    )
    assert response.status_code == 201
    first = await client.post(f"/api/v1/profiles/{user_id}/rebuild")
    assert first.status_code == 200
    old_ids = {item["id"] for item in first.json()["items"]}
    second = await client.post(f"/api/v1/profiles/{user_id}/rebuild")
    assert second.status_code == 200
    new_ids = {item["id"] for item in second.json()["items"]}
    assert old_ids != new_ids
    overview = await client.get(f"/api/v1/profiles/{user_id}/overview")
    assert overview.status_code == 200
    assert overview.json()["profile_item_count"] == len(new_ids)


async def test_overview_and_manifest_endpoints(client):
    user_id = "manifest-user"
    response = await client.post(
        "/api/v1/evidence/text",
        json={"user_id": user_id, "content": "我熟悉 Python 并做过 RAG 检索项目。"},
    )
    assert response.status_code == 201
    await client.post(f"/api/v1/profiles/{user_id}/rebuild")

    overview = await client.get(f"/api/v1/profiles/{user_id}/overview")
    assert overview.status_code == 200
    assert overview.json()["coverage"]["supported"] + overview.json()["coverage"]["weak"] > 0

    manifest = await client.get(f"/api/v1/profiles/{user_id}/agent-manifest")
    assert manifest.status_code == 200
    payload = manifest.json()
    assert payload["writable_policy"] == "agent_can_propose_only"
    capabilities = {item["name"]: item for item in payload["capabilities"]}
    assert capabilities["propose_profile_update"]["evidence_policy"] == "draft_only"
    assert capabilities["query_profile"]["requires_scope"] == "read"
    assert any("ProfileItem.id" in note for note in payload["notes"])


async def test_manifest_reports_enabled_dimensions_without_creating_facts(session_factory):
    user_id = "manifest-readonly"
    async with session_factory() as session:
        session.add_all([
            _evidence("e1", user_id),
            ProfileItem(
                id="p1", user_id=user_id, category="skill", name="Python", level=3,
                confidence=0.8, evidence_ids=["e1"], details={},
            ),
            ProfileSuppression(id="s1", user_id=user_id, category="skill", name="React"),
        ])
        await session.commit()
        overview = await build_profile_overview(session, user_id)
    manifest = build_agent_manifest(user_id, overview)
    assert set(manifest["enabled_dimensions"]) == {"evidence_health", "skill"}
    assert manifest["writable_policy"] == "agent_can_propose_only"
