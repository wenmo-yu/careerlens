import argparse
import json
from datetime import UTC, datetime
from typing import Any

from mcp.server import MCPServer
from mcp.server.auth.middleware.auth_context import get_access_token
from mcp.server.auth.provider import AccessToken as MCPAccessToken
from mcp.server.auth.provider import TokenVerifier
from mcp.server.auth.settings import AuthSettings
from mcp.server.mcpserver import Context
from mcp.server.mcpserver.exceptions import ResourceError, ToolError
from sqlalchemy import select

from app.core.config import Settings, get_settings
from app.core.database import SessionFactory
from app.models.career_report import CareerReport
from app.models.evidence import Evidence
from app.models.job_analysis import JobAnalysis
from app.retrieval.service import search_evidence as run_evidence_search
from app.security import Principal
from app.security.auth import verify_access_token
from app.services.audit import add_audit_event
from app.services.evidence import create_evidence_chunks
from app.services.jobs import analyze_job
from app.services.profile import read_profile
from app.services.reports import generate_report, list_reports


class CareerLensTokenVerifier(TokenVerifier):
    """Verify MCP Bearer tokens against the existing CareerLens token table."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    async def verify_token(self, token: str) -> MCPAccessToken | None:
        async with SessionFactory() as session:
            record = await verify_access_token(session, token)
            if record is None:
                return None
            record.last_used_at = datetime.now(UTC)
            await session.commit()
            return MCPAccessToken(
                token=token,
                client_id=record.id,
                scopes=list(record.scopes),
                subject=record.user_id,
                resource=self.settings.mcp_resource_server_url,
            )


def build_mcp_server(settings: Settings | None = None) -> MCPServer:
    settings = settings or get_settings()
    auth_mode = settings.mcp_auth_mode.lower()
    if auth_mode not in {"disabled", "required"}:
        raise ValueError("MCP_AUTH_MODE must be 'disabled' or 'required'")

    kwargs: dict[str, Any] = {}
    if auth_mode == "required":
        kwargs.update(
            token_verifier=CareerLensTokenVerifier(settings),
            auth=AuthSettings(
                issuer_url=settings.mcp_auth_issuer_url,
                resource_server_url=settings.mcp_resource_server_url,
                required_scopes=[],
                validate_token_resource=True,
            ),
        )
    return MCPServer(
        "CareerLens",
        description=(
            "Evidence-grounded career profile, job analysis, and report tools. "
            "Every claim remains traceable to a CareerLens Evidence ID."
        ),
        instructions=(
            "Use read-scoped tools to inspect a user's evidence and career profile. "
            "Use write-scoped tools to import evidence, analyze a JD, or generate a report. "
            "Never invent experience that is not supported by returned Evidence IDs."
        ),
        version="0.2.0",
        **kwargs,
    )


mcp = build_mcp_server()


def _authorized_principal(user_id: str, required_scope: str) -> Principal:
    token = get_access_token()
    if token is None:
        # stdio is a local, process-boundary transport. HTTP deployments must enable auth.
        return Principal(user_id=user_id, token_id=None, scopes=("*",))
    if token.subject != user_id:
        raise ToolError("The access token cannot access another user")
    scopes = tuple(token.scopes)
    if required_scope not in scopes and "manage" not in scopes:
        raise ToolError(f"Missing required scope: {required_scope}")
    return Principal(user_id=user_id, token_id=token.client_id, scopes=scopes)


def _evidence_payload(item: Evidence) -> dict[str, Any]:
    return {
        "evidence_id": item.id,
        "source_type": item.source_type,
        "source_name": item.source_name,
        "content": item.content,
        "content_type": item.content_type,
        "chunk_index": item.chunk_index,
        "metadata": item.source_metadata,
        "created_at": item.created_at.isoformat() if item.created_at else None,
    }


def _analysis_payload(item: JobAnalysis) -> dict[str, Any]:
    return {
        "job_analysis_id": item.id,
        "title": item.title,
        "score": item.score,
        "requirements": item.requirements,
        "matches": item.matches,
        "gaps": item.gaps,
        "learning_path": item.learning_path,
        "report": item.report,
        "created_at": item.created_at.isoformat() if item.created_at else None,
    }


def _report_payload(item: CareerReport, *, include_markdown: bool = False) -> dict[str, Any]:
    payload = {
        "report_id": item.id,
        "job_analysis_id": item.job_analysis_id,
        "version": item.version,
        "title": item.title,
        "content": item.content,
        "model_diagnostics": item.model_diagnostics,
        "is_stale": item.is_stale,
        "created_at": item.created_at.isoformat() if item.created_at else None,
    }
    if include_markdown:
        payload["markdown"] = item.markdown
    return payload


async def _commit_audit(
    session: Any,
    *,
    principal: Principal,
    action: str,
    resource_type: str,
    resource_id: str | None = None,
    details: dict[str, Any] | None = None,
) -> None:
    add_audit_event(
        session,
        principal=principal,
        action=f"mcp.{action}",
        resource_type=resource_type,
        resource_id=resource_id,
        details=details,
    )
    await session.commit()


@mcp.tool()
async def list_user_content(user_id: str, ctx: Context, limit: int = 50) -> list[dict]:
    """List a user's imported evidence with source metadata. Requires read scope."""
    principal = _authorized_principal(user_id, "read")
    async with SessionFactory() as session:
        result = await session.scalars(
            select(Evidence)
            .where(Evidence.user_id == user_id)
            .order_by(Evidence.created_at.desc(), Evidence.chunk_index)
            .limit(min(max(limit, 1), 200))
        )
        items = [_evidence_payload(item) for item in result]
        await _commit_audit(
            session,
            principal=principal,
            action="evidence.list",
            resource_type="evidence",
            details={"count": len(items)},
        )
        return items


@mcp.tool()
async def get_evidence(user_id: str, evidence_id: str, ctx: Context) -> dict:
    """Read one Evidence record by ID. Requires read scope."""
    principal = _authorized_principal(user_id, "read")
    async with SessionFactory() as session:
        item = await session.get(Evidence, evidence_id)
        if item is None or item.user_id != user_id:
            raise ToolError("Evidence not found for this user")
        await _commit_audit(
            session,
            principal=principal,
            action="evidence.read",
            resource_type="evidence",
            resource_id=item.id,
        )
        return _evidence_payload(item)


@mcp.tool()
async def import_text_evidence(
    user_id: str,
    source_name: str,
    content: str,
    ctx: Context,
    source_type: str = "mcp_import",
) -> list[dict]:
    """Import plain text as chunked Evidence. Requires write scope."""
    principal = _authorized_principal(user_id, "write")
    async with SessionFactory() as session:
        try:
            records = await create_evidence_chunks(
                session,
                user_id=user_id,
                source_type=source_type,
                source_name=source_name,
                content=content,
                metadata={"imported_via": "mcp"},
            )
        except ValueError as exc:
            raise ToolError(str(exc)) from exc
        await _commit_audit(
            session,
            principal=principal,
            action="evidence.import",
            resource_type="evidence",
            details={"source_name": source_name, "chunks": len(records)},
        )
        return [_evidence_payload(item) for item in records]


@mcp.tool()
async def search_evidence(user_id: str, query: str, ctx: Context, limit: int = 5) -> dict:
    """Search evidence supporting a career claim or job requirement. Requires read scope."""
    principal = _authorized_principal(user_id, "read")
    async with SessionFactory() as session:
        result = await session.scalars(select(Evidence).where(Evidence.user_id == user_id))
        items, diagnostics = await run_evidence_search(
            user_id=user_id,
            query=query,
            evidence=list(result),
            limit=min(max(limit, 1), 20),
        )
        await _commit_audit(
            session,
            principal=principal,
            action="evidence.search",
            resource_type="evidence",
            details={"query": query, "count": len(items)},
        )
        return {"items": items, "retrieval": diagnostics}


@mcp.tool()
async def get_user_profile(user_id: str, ctx: Context) -> list[dict]:
    """Get structured profile items and their supporting Evidence IDs. Requires read scope."""
    principal = _authorized_principal(user_id, "read")
    async with SessionFactory() as session:
        records = await read_profile(session, user_id)
        items = [
            {
                "category": item.category,
                "name": item.name,
                "level": item.level,
                "confidence": item.confidence,
                "evidence_ids": item.evidence_ids,
                "details": item.details,
            }
            for item in records
        ]
        await _commit_audit(
            session,
            principal=principal,
            action="profile.read",
            resource_type="profile",
            resource_id=user_id,
            details={"count": len(items)},
        )
        return items


@mcp.tool()
async def list_job_analyses(user_id: str, ctx: Context, limit: int = 20) -> list[dict]:
    """List saved JD analyses for a user. Requires read scope."""
    principal = _authorized_principal(user_id, "read")
    async with SessionFactory() as session:
        result = await session.scalars(
            select(JobAnalysis)
            .where(JobAnalysis.user_id == user_id)
            .order_by(JobAnalysis.created_at.desc())
            .limit(min(max(limit, 1), 100))
        )
        items = [_analysis_payload(item) for item in result]
        await _commit_audit(
            session,
            principal=principal,
            action="job.list",
            resource_type="job_analysis",
            details={"count": len(items)},
        )
        return items


@mcp.tool()
async def analyze_job_description(
    user_id: str,
    title: str,
    jd_text: str,
    ctx: Context,
    weekly_hours: int = 10,
) -> dict:
    """Analyze a JD against the evidence-backed profile. Requires write scope."""
    principal = _authorized_principal(user_id, "write")
    async with SessionFactory() as session:
        try:
            record = await analyze_job(
                session,
                user_id=user_id,
                title=title,
                jd_text=jd_text,
                weekly_hours=min(max(weekly_hours, 1), 80),
            )
        except ValueError as exc:
            raise ToolError(str(exc)) from exc
        await _commit_audit(
            session,
            principal=principal,
            action="job.analyze",
            resource_type="job_analysis",
            resource_id=record.id,
        )
        return _analysis_payload(record)


@mcp.tool()
async def generate_career_report(user_id: str, job_analysis_id: str, ctx: Context) -> dict:
    """Generate a versioned career report from one JD analysis. Requires write scope."""
    principal = _authorized_principal(user_id, "write")
    async with SessionFactory() as session:
        try:
            record = await generate_report(
                session, user_id=user_id, job_analysis_id=job_analysis_id
            )
        except ValueError as exc:
            raise ToolError(str(exc)) from exc
        await _commit_audit(
            session,
            principal=principal,
            action="report.generate",
            resource_type="career_report",
            resource_id=record.id,
        )
        return _report_payload(record, include_markdown=True)


@mcp.tool()
async def list_career_reports(user_id: str, ctx: Context, limit: int = 20) -> list[dict]:
    """List versioned career reports. Requires read scope."""
    principal = _authorized_principal(user_id, "read")
    async with SessionFactory() as session:
        records = await list_reports(
            session, user_id=user_id, limit=min(max(limit, 1), 100)
        )
        items = [_report_payload(item) for item in records]
        await _commit_audit(
            session,
            principal=principal,
            action="report.list",
            resource_type="career_report",
            details={"count": len(items)},
        )
        return items


@mcp.tool()
async def get_career_report(user_id: str, report_id: str, ctx: Context) -> dict:
    """Read a generated career report, including Markdown. Requires read scope."""
    principal = _authorized_principal(user_id, "read")
    async with SessionFactory() as session:
        record = await session.get(CareerReport, report_id)
        if record is None or record.user_id != user_id:
            raise ToolError("Career report not found for this user")
        await _commit_audit(
            session,
            principal=principal,
            action="report.read",
            resource_type="career_report",
            resource_id=record.id,
        )
        return _report_payload(record, include_markdown=True)


@mcp.resource("profile://{user_id}")
async def profile_resource(user_id: str, ctx: Context) -> str:
    """Structured career profile as JSON."""
    try:
        return json.dumps(await get_user_profile(user_id, ctx), ensure_ascii=False)
    except ToolError as exc:
        raise ResourceError(str(exc)) from exc


@mcp.resource("evidence://{user_id}/{evidence_id}")
async def evidence_resource(user_id: str, evidence_id: str, ctx: Context) -> str:
    """One evidence record as JSON."""
    try:
        return json.dumps(await get_evidence(user_id, evidence_id, ctx), ensure_ascii=False)
    except ToolError as exc:
        raise ResourceError(str(exc)) from exc


@mcp.resource("report://{user_id}/{report_id}")
async def report_resource(user_id: str, report_id: str, ctx: Context) -> str:
    """One career report as JSON, including its Markdown."""
    try:
        return json.dumps(
            await get_career_report(user_id, report_id, ctx), ensure_ascii=False
        )
    except ToolError as exc:
        raise ResourceError(str(exc)) from exc


@mcp.prompt()
def explain_profile_claim(claim: str, evidence_ids: str) -> str:
    """Build an evidence-review prompt for a profile claim."""
    return (
        "Review the career-profile claim below. Only mark it supported when the supplied "
        f"evidence directly supports it.\n\nClaim: {claim}\nEvidence IDs: {evidence_ids}"
    )


@mcp.prompt()
def review_job_match(job_title: str, requirements: str, evidence_ids: str) -> str:
    """Build a strict prompt for reviewing a user's fit for a role."""
    return (
        f"Review the user's fit for {job_title}. Separate supported strengths, partial "
        "matches, and gaps. Cite only the supplied Evidence IDs and do not infer missing "
        f"experience.\n\nRequirements:\n{requirements}\n\nEvidence IDs: {evidence_ids}"
    )


@mcp.prompt()
def prepare_interview_pitch(job_title: str, strengths: str, gaps: str) -> str:
    """Build a candid interview-pitch prompt grounded in verified strengths."""
    return (
        f"Draft a concise interview pitch for {job_title}. Lead with verified strengths, "
        "acknowledge gaps without exaggeration, and describe a concrete learning plan."
        f"\n\nVerified strengths:\n{strengths}\n\nKnown gaps:\n{gaps}"
    )


def _parser(settings: Settings) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the CareerLens MCP server")
    parser.add_argument(
        "--transport",
        choices=("stdio", "streamable-http"),
        default=settings.mcp_transport,
    )
    parser.add_argument("--host", default=settings.mcp_host)
    parser.add_argument("--port", type=int, default=settings.mcp_port)
    parser.add_argument("--path", default=settings.mcp_streamable_http_path)
    return parser


def main() -> None:
    settings = get_settings()
    args = _parser(settings).parse_args()
    if args.transport == "stdio":
        mcp.run(transport="stdio")
        return
    if args.host not in {"127.0.0.1", "localhost", "::1"} and settings.mcp_auth_mode != "required":
        raise RuntimeError("MCP_AUTH_MODE=required is mandatory on non-loopback HTTP hosts")
    mcp.run(
        transport="streamable-http",
        host=args.host,
        port=args.port,
        streamable_http_path=args.path,
        stateless_http=True,
        json_response=True,
    )


if __name__ == "__main__":
    main()
