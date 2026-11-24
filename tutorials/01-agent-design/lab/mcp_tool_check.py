"""Use the real CareerLens MCP tool, first by name and then through @tool."""

import json

from langchain_core.tools import tool
from mcp import Client
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.database import Base
from app.mcp import server
from app.models.audit import AuditEvent
from app.models.evidence import Evidence

CONTENT = "我用 Python 和 FastAPI 做过课程接口，用 Docker 在本机运行。"


def unpack(result):
    if result.is_error:
        raise ValueError(result.content[0].text)
    if result.structured_content is not None:
        return result.structured_content
    return json.loads(result.content[0].text)


def build_evidence_tool(client, user_id):
    @tool
    async def read_careerlens_evidence(evidence_id: str) -> str:
        """Read the original text of a CareerLens Evidence record by ID."""
        result = await client.call_tool(
            "get_evidence", {"user_id": user_id, "evidence_id": evidence_id}
        )
        return unpack(result)["content"]

    return read_careerlens_evidence


async def test_call_registered_evidence_tool(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    factory = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(server, "SessionFactory", factory)
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        async with factory.begin() as session:
            item = Evidence(
                user_id="agent-lesson",
                source_type="self_statement",
                source_name="agent-course-sample",
                content=CONTENT,
            )
            session.add(item)

        async with Client(server.mcp) as client:
            discovered = await client.list_tools()
            registered = next(
                candidate for candidate in discovered.tools if candidate.name == "get_evidence"
            )
            assert set(registered.input_schema["properties"]) == {"user_id", "evidence_id"}
            native = await client.call_tool(
                "get_evidence", {"user_id": "agent-lesson", "evidence_id": item.id}
            )
            assert unpack(native)["evidence_id"] == item.id
            assert unpack(native)["content"] == CONTENT

            adapter = build_evidence_tool(client, "agent-lesson")
            assert set(adapter.args) == {"evidence_id"}
            assert await adapter.ainvoke({"evidence_id": item.id}) == CONTENT

            for caller, evidence_id in (
                ("agent-lesson", "course-missing-evidence"),
                ("agent-other", item.id),
            ):
                unavailable = await client.call_tool(
                    "get_evidence",
                    {"user_id": caller, "evidence_id": evidence_id},
                )
                assert unavailable.is_error
                assert "Evidence not found for this user" in unavailable.content[0].text

        async with factory() as session:
            audit_actions = list(await session.scalars(select(AuditEvent.action)))
        assert audit_actions == ["mcp.evidence.read", "mcp.evidence.read"]
    finally:
        await engine.dispose()
