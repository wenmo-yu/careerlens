import json

from httpx import ASGITransport, AsyncClient
from mcp import Client
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import Settings
from app.core.database import Base
from app.mcp import server as mcp_server
from app.models.audit import AuditEvent
from app.models.evidence import Evidence
from app.models.profile import ProfileItem
from app.security.auth import create_access_token


def _tool_value(result):
    if result.structured_content is not None:
        return result.structured_content
    return json.loads(result.content[0].text)


async def test_mcp_exposes_complete_contract():
    async with Client(mcp_server.mcp) as client:
        tools = await client.list_tools()
        resources = await client.list_resource_templates()
        prompts = await client.list_prompts()

    tool_names = {tool.name for tool in tools.tools}
    assert {
        "list_user_content",
        "get_evidence",
        "import_text_evidence",
        "search_evidence",
        "get_user_profile",
        "list_job_analyses",
        "analyze_job_description",
        "generate_career_report",
        "list_career_reports",
        "get_career_report",
    } <= tool_names
    assert {item.uri_template for item in resources.resource_templates} == {
        "profile://{user_id}",
        "evidence://{user_id}/{evidence_id}",
        "report://{user_id}/{report_id}",
    }
    assert {prompt.name for prompt in prompts.prompts} == {
        "explain_profile_claim",
        "review_job_match",
        "prepare_interview_pitch",
    }


async def test_mcp_job_report_flow_is_audited(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    async with session_factory() as session:
        evidence = Evidence(
            user_id="mcp-user",
            source_type="project",
            source_name="Recommendation Engine",
            content="Built a Python recommendation service and FastAPI endpoints.",
        )
        session.add(evidence)
        await session.flush()
        session.add(
            ProfileItem(
                user_id="mcp-user",
                category="skill",
                name="Python",
                level=3,
                confidence=0.9,
                evidence_ids=[evidence.id],
            )
        )
        await session.commit()

    monkeypatch.setattr(mcp_server, "SessionFactory", session_factory)
    async with Client(mcp_server.mcp) as client:
        analysis_result = await client.call_tool(
            "analyze_job_description",
            {
                "user_id": "mcp-user",
                "title": "Python Backend Engineer",
                "jd_text": "Required: Python. FastAPI preferred.",
                "weekly_hours": 8,
            },
        )
        assert not analysis_result.is_error
        analysis = _tool_value(analysis_result)
        assert analysis["score"] > 0

        report_result = await client.call_tool(
            "generate_career_report",
            {
                "user_id": "mcp-user",
                "job_analysis_id": analysis["job_analysis_id"],
            },
        )
        assert not report_result.is_error
        report = _tool_value(report_result)
        assert report["report_id"]
        assert "# Python Backend Engineer" in report["markdown"]

        read_result = await client.call_tool(
            "get_career_report",
            {"user_id": "mcp-user", "report_id": report["report_id"]},
        )
        assert _tool_value(read_result)["version"] == 1
        resource = await client.read_resource(
            f"report://mcp-user/{report['report_id']}"
        )
        resource_value = json.loads(resource.contents[0].text)
        assert resource_value["report_id"] == report["report_id"]

    async with session_factory() as session:
        actions = set(await session.scalars(select(AuditEvent.action)))
    assert {"mcp.job.analyze", "mcp.report.generate", "mcp.report.read"} <= actions
    await engine.dispose()


async def test_mcp_token_verifier_reuses_api_tokens(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    async with session_factory() as session:
        record, raw_token = await create_access_token(
            session,
            user_id="token-user",
            name="MCP client",
            scopes=["read", "write"],
        )

    monkeypatch.setattr(mcp_server, "SessionFactory", session_factory)
    verifier = mcp_server.CareerLensTokenVerifier(
        Settings(mcp_resource_server_url="http://localhost:8001/mcp")
    )
    verified = await verifier.verify_token(raw_token)
    assert verified is not None
    assert verified.client_id == record.id
    assert verified.subject == "token-user"
    assert verified.scopes == ["read", "write"]
    assert await verifier.verify_token("invalid") is None
    await engine.dispose()


async def test_streamable_http_requires_bearer_token():
    protected = mcp_server.build_mcp_server(
        Settings(
            mcp_auth_mode="required",
            mcp_auth_issuer_url="http://localhost:8000",
            mcp_resource_server_url="http://localhost:8001/mcp",
        )
    )
    app = protected.streamable_http_app(stateless_http=True, json_response=True)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://localhost:8001"
    ) as client:
        response = await client.post("/mcp", json={})
    assert response.status_code == 401
