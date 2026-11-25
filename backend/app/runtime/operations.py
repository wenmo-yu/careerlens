import asyncio
import json
import os
import sys
from collections.abc import Awaitable, Callable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.ingestion.contract import ParsedBlock, ParsedDocument
from app.models.evidence import Evidence
from app.runtime.agents import Coordinator
from app.services.jobs import job_inputs, persist_analysis, prepare_analysis
from app.services.reports import persist_report, report_content, report_inputs
from app.services.source_ingestion import ingest_source_document
from app.wiki.compiler import check_page_version, persist_page

Effect = Callable[[AsyncSession], Awaitable[dict]]


class InputUnavailable(ValueError):
    pass


class ParserUnavailable(ValueError):
    pass


async def parse_in_process(operation: str, filename: str, data: bytes) -> ParsedDocument:
    inherited = {
        "SYSTEMROOT", "WINDIR", "TEMP", "TMP", "PATH", "HOME", "USERPROFILE", "LANG",
        "XDG_CACHE_HOME", "PADDLE_PDX_CACHE_HOME", "HF_HOME", "SSL_CERT_FILE",
        "WHISPER_MODEL", "WHISPER_DEVICE", "WHISPER_COMPUTE_TYPE", "OCR_LANGUAGE",
        "PYTHONDONTWRITEBYTECODE",
    }
    process = await asyncio.create_subprocess_exec(
        sys.executable, "-m", "app.runtime.parse_input",
        stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL,
        env={key: value for key, value in os.environ.items() if key.upper() in inherited},
    )
    envelope = json.dumps([operation, filename]).encode("utf-8") + b"\n"
    try:
        stdout, _ = await process.communicate(envelope + data)
    except asyncio.CancelledError:
        if process.returncode is None:
            try:
                process.kill()
            except ProcessLookupError:
                pass
        await process.wait()
        raise
    try:
        result = json.loads(stdout.rstrip().rsplit(b"\n", 1)[-1])
        if result.get("error") == "parser_unavailable":
            raise ParserUnavailable
        parsed = result["document"]
        parsed["blocks"] = [ParsedBlock(**item) for item in parsed["blocks"]]
        return ParsedDocument(**parsed)
    except (ValueError, KeyError, TypeError) as exc:
        if isinstance(exc, ParserUnavailable):
            raise
        raise InputUnavailable("Unable to parse this file") from exc


async def prepare_operation(
    factory: async_sessionmaker,
    *,
    operation: str,
    user_id: str,
    data: dict,
    upload: bytes | None,
    progress: Callable[..., Awaitable[None]],
) -> Effect:
    coordinator = Coordinator(progress)
    if operation in {"file_import", "media_import"}:
        if upload is None:
            raise InputUnavailable("Upload no longer exists")
        await progress("parse", "running")
        parsed = await parse_in_process(operation, data["filename"], upload)
        await progress("parse", "succeeded", block_count=len(parsed.blocks))

        async def save_upload(session: AsyncSession) -> dict:
            records = await ingest_source_document(session, user_id=user_id, parsed=parsed,
                                                   commit=False, **data)
            # HY4-A: keep the same result-card contract as the synchronous
            # /evidence/file endpoint. A task can succeed while a scanned PDF
            # produces zero readable Evidence; the UI must be able to say so.
            ocr_pending = sum(
                1 for block in parsed.blocks if block.source_metadata.get("ocr_pending")
            )
            readable = sum(
                1 for block in parsed.blocks
                if block.content.strip() and not block.source_metadata.get("ocr_pending")
            )
            warnings: list[str] = []
            if ocr_pending:
                warnings.append(
                    f"有 {ocr_pending} 页待 OCR；任务成功不等于已读出文字。"
                )
            if not readable and ocr_pending:
                warnings.append(
                    "本次只识别到扫描页，尚未生成可读证据；请补充 OCR 能力或换用带文字层的 PDF。"
                )
            return {
                "count": len(records),
                "evidence_ids": [record.id for record in records],
                "parse_status": (
                    "partial" if ocr_pending and parsed.parse_status == "parsed"
                    else parsed.parse_status
                ),
                "readable_count": readable,
                "ocr_pending_count": ocr_pending,
                "warnings": warnings,
            }

        return save_upload

    if operation == "job_analysis":
        async with factory() as session:
            profile, valid_ids = await job_inputs(session, user_id)
        task = await coordinator.delegate("requirement_analyst", {"jd_text": data["jd_text"]})
        values = prepare_analysis(
            profile, valid_ids, **data, requirements=task["requirements"],
            extraction=task["diagnostics"],
        )
        await coordinator.verify(
            valid_ids, [item_id for row in values["matches"] for item_id in row["evidence_ids"]]
        )

        async def save_job(session: AsyncSession) -> dict:
            record = await persist_analysis(session, user_id, values)
            return {"job_analysis_id": record.id}

        return save_job

    if operation == "report":
        analysis_id = data["job_analysis_id"]
        async with factory() as session:
            context, content, title = await report_inputs(
                session, user_id=user_id, job_analysis_id=analysis_id
            )
        task = await coordinator.delegate("report_writer", context)
        await coordinator.verify(
            set(context["evidence_ids"]), task["narrative"]["cited_evidence_ids"]
        )

        async def save_report(session: AsyncSession) -> dict:
            record = await persist_report(
                session, user_id=user_id, job_analysis_id=analysis_id, title=title,
                content=report_content(content, task["narrative"]), diagnostics=task["diagnostics"],
            )
            return {"report_id": record.id, "version": record.version}

        return save_report

    if operation != "wiki_compile":
        raise InputUnavailable("Unsupported operation")
    ids = list(dict.fromkeys(data["evidence_ids"]))
    async with factory() as session:
        await check_page_version(session, user_id, data["slug"], data["base_version"])
        rows = (await session.execute(
            select(Evidence.id, Evidence.content)
            .where(Evidence.user_id == user_id, Evidence.id.in_(ids))
        )).all()
        sources = {item_id: content for item_id, content in rows}
    if set(ids) != sources.keys():
        raise InputUnavailable("One or more evidence sources are unavailable")
    if sum(map(len, sources.values())) > 250_000:
        raise InputUnavailable("Selected evidence exceeds the Wiki context limit")
    task = await coordinator.delegate(
        "wiki_curator",
        {"title": data["title"], "sources": [
            {"evidence_id": item_id, "content": sources[item_id]} for item_id in ids
        ]},
    )
    await coordinator.verify(set(ids), task["refs"])

    async def save_wiki(session: AsyncSession) -> dict:
        page = await persist_page(
            session, user_id=user_id, slug=data["slug"], base_version=data["base_version"],
            values=task["values"], edit_source="agent", source_refs=ids,
            chunk_refs=task["refs"], verify_sources=True,
        )
        return {"wiki_slug": page.slug, "version": page.version, "page_id": page.id}

    return save_wiki
