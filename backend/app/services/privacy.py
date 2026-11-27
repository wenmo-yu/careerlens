import hashlib
from datetime import UTC, datetime

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.access_token import AccessToken
from app.models.account_deletion import AccountDeletionReceipt, DeletionWork
from app.models.assessment import AssessmentResult, UserConstraint
from app.models.audit import AuditEvent
from app.models.career_report import CareerReport
from app.models.conversation import ConversationMessage, ConversationThread
from app.models.evidence import Evidence
from app.models.job_analysis import JobAnalysis
from app.models.learning import LearningProgress, SavedJob
from app.models.parsed_block import ParsedBlock
from app.models.profile import ProfileItem
from app.models.profile_extension import DimensionDefinition, ProfileExtension
from app.models.profile_suppression import ProfileSuppression
from app.models.profile_update import ProfileUpdateProposal
from app.models.run import AgentRun, EvidenceIndexWork, RunEvent, RunScope, RunStep
from app.models.source_document import SourceDocument
from app.models.wiki import WikiPage, WikiRevision
from app.retrieval.generations import cleanup_collections
from app.runtime.index_outbox import enqueue_index, try_index_now
from app.runtime.store import DELETION, INPUT, scope
from app.security import Principal
from app.security.auth import DELETED_ACCOUNT
from app.services.audit import add_audit_event


def _serialize(record, fields: tuple[str, ...]) -> dict:
    result = {}
    for field in fields:
        value = getattr(record, field)
        result[field] = value.isoformat() if isinstance(value, datetime) else value
    return result


def _valid_refs(value) -> bool:
    return isinstance(value, list) and all(isinstance(item, str) for item in value)


def _report_depends_on(content, evidence_id: str) -> bool:
    if not isinstance(content, dict) or not _valid_refs(content.get("referenced_evidence_ids")):
        return True
    if evidence_id in content["referenced_evidence_ids"]:
        return True
    catalog = content.get("evidence_catalog", [])
    if not isinstance(catalog, list):
        return True
    return (
        any(
            not isinstance(entry, dict) or not isinstance(entry.get("id"), str)
            or entry["id"] == evidence_id for entry in catalog
        )
        or _rows_depend_on(content.get("job_matching"), evidence_id)
        or _rows_depend_on(content.get("core_capabilities"), evidence_id)
    )


def _rows_depend_on(rows, evidence_id: str) -> bool:
    return not isinstance(rows, list) or any(
        not isinstance(entry, dict) or not _valid_refs(entry.get("evidence_ids"))
        or evidence_id in entry["evidence_ids"] for entry in rows
    )


async def _redact_derived_data(session: AsyncSession, record: Evidence) -> set[str]:
    user_id, evidence_id = record.user_id, record.id
    affected_analyses = set()
    for item in await session.scalars(select(JobAnalysis).where(JobAnalysis.user_id == user_id)):
        if not item.privacy_redacted and not _rows_depend_on(item.matches, evidence_id):
            continue
        affected_analyses.add(item.id)
        item.matches, item.gaps, item.learning_path = [], [], []
        item.score = 0.0  # Database placeholder, unavailable at every public reader.
        item.report = {"privacy_redacted": True}

    for item in await session.scalars(
        select(LearningProgress).where(LearningProgress.user_id == user_id)
    ):
        refs = item.evidence_ids
        if _valid_refs(refs) and evidence_id not in refs:
            continue
        item.evidence_ids = (
            [value for value in refs if value != evidence_id] if _valid_refs(refs) else []
        )
        item.note = ""

    for item in await session.scalars(
        select(ProfileExtension).where(ProfileExtension.user_id == user_id)
    ):
        if not _valid_refs(item.evidence_ids) or evidence_id in item.evidence_ids:
            await session.delete(item)

    metadata = record.source_metadata
    proposal_id = metadata.get("proposal_id") if isinstance(metadata, dict) else None
    if isinstance(proposal_id, str):
        await session.execute(delete(ProfileUpdateProposal).where(
            ProfileUpdateProposal.user_id == user_id, ProfileUpdateProposal.id == proposal_id,
        ))
    return affected_analyses


async def _redact_conversation_references(
    session: AsyncSession, *, user_id: str, evidence_id: str, original: str,
) -> int:
    threads = set(await session.scalars(
        select(ConversationThread.thread_id).where(ConversationThread.user_id == user_id)
    ))
    for item in await session.scalars(
        select(ConversationMessage).where(ConversationMessage.user_id == user_id)
    ):
        threads.add(item.thread_id)
        refs = item.evidence_ids
        if (
            (item.role == "assistant" and (not _valid_refs(refs) or evidence_id in refs))
            or (original.strip() and original.strip() in item.content)
        ):
            item.content = "[内容已随关联证据清除]"
            item.evidence_ids = []
    if get_settings().uses_postgres_checkpoint:
        session.add_all(DeletionWork(kind="checkpoint", subject=thread) for thread in threads)
        return len(threads)
    return 0


async def export_user_data(
    session: AsyncSession, *, principal: Principal
) -> dict:
    user_id = principal.user_id
    runs = list(await session.scalars(select(AgentRun).where(AgentRun.user_id == user_id)))
    steps = list(await session.scalars(select(RunStep).where(RunStep.user_id == user_id)))
    events = list(await session.scalars(select(RunEvent).where(RunEvent.user_id == user_id)))
    evidence = list(
        await session.scalars(select(Evidence).where(Evidence.user_id == user_id))
    )
    profile = list(
        await session.scalars(select(ProfileItem).where(ProfileItem.user_id == user_id))
    )
    jobs = list(
        await session.scalars(select(JobAnalysis).where(JobAnalysis.user_id == user_id))
    )
    reports = list(
        await session.scalars(select(CareerReport).where(
            CareerReport.user_id == user_id, CareerReport.privacy_redacted.is_(False),
        ))
    )
    proposals = list(
        await session.scalars(
            select(ProfileUpdateProposal).where(ProfileUpdateProposal.user_id == user_id)
        )
    )
    audits = list(
        await session.scalars(select(AuditEvent).where(AuditEvent.user_id == user_id))
    )
    documents = list(
        await session.scalars(select(SourceDocument).where(SourceDocument.user_id == user_id))
    )
    parsed_blocks = list(
        await session.scalars(select(ParsedBlock).where(ParsedBlock.user_id == user_id))
    )
    wiki_pages = list(
        await session.scalars(select(WikiPage).where(
            WikiPage.user_id == user_id, WikiPage.privacy_redacted.is_(False),
        ))
    )
    wiki_revisions = [
        item for item in await session.scalars(
            select(WikiRevision).where(WikiRevision.user_id == user_id)
        ) if _valid_refs(item.source_refs) and _valid_refs(item.chunk_refs)
    ]
    saved_jobs = list(
        await session.scalars(select(SavedJob).where(SavedJob.user_id == user_id))
    )
    learning_progress = list(
        await session.scalars(select(LearningProgress).where(LearningProgress.user_id == user_id))
    )
    assessments = list(
        await session.scalars(select(AssessmentResult).where(AssessmentResult.user_id == user_id))
    )
    constraints = list(
        await session.scalars(select(UserConstraint).where(UserConstraint.user_id == user_id))
    )
    dimensions = list(
        await session.scalars(
            select(DimensionDefinition).where(DimensionDefinition.user_id == user_id)
        )
    )
    extensions = list(
        await session.scalars(select(ProfileExtension).where(ProfileExtension.user_id == user_id))
    )
    add_audit_event(
        session,
        principal=principal,
        action="user_data.exported",
        resource_type="user_data",
        resource_id=user_id,
        details={
            "evidence_count": len(evidence),
            "profile_item_count": len(profile),
            "job_analysis_count": len(jobs),
            "career_report_count": len(reports),
            "source_document_count": len(documents),
            "parsed_block_count": len(parsed_blocks),
            "wiki_page_count": len(wiki_pages),
            "wiki_revision_count": len(wiki_revisions),
            "saved_job_count": len(saved_jobs),
            "learning_progress_count": len(learning_progress),
            "assessment_result_count": len(assessments),
            "user_constraint_count": len(constraints),
            "dimension_definition_count": len(dimensions),
            "profile_extension_count": len(extensions),
        },
    )
    await session.commit()
    return {
        "schema_version": "1.0",
        "user_id": user_id,
        "exported_at": datetime.now(UTC).isoformat(),
        "evidence": [
            _serialize(
                item,
                (
                    "id",
                    "source_type",
                    "source_name",
                    "content",
                    "content_type",
                    "chunk_index",
                    "source_metadata",
                    "created_at",
                ),
            )
            for item in evidence
        ],
        "profile": [
            _serialize(
                item,
                (
                    "id",
                    "category",
                    "name",
                    "level",
                    "confidence",
                    "evidence_ids",
                    "details",
                    "updated_at",
                ),
            )
            for item in profile
        ],
        "job_analyses": [
            _serialize(
                item,
                (
                    "id",
                    "title",
                    "jd_text",
                    "score",
                    "requirements",
                    "matches",
                    "gaps",
                    "learning_path",
                    "report",
                    "created_at",
                ),
            )
            for item in jobs if not item.privacy_redacted
        ],
        "career_reports": [
            _serialize(
                item,
                (
                    "id",
                    "job_analysis_id",
                    "version",
                    "title",
                    "content",
                    "markdown",
                    "model_diagnostics",
                    "is_stale",
                    "created_at",
                ),
            )
            for item in reports
        ],
        "profile_update_proposals": [
            _serialize(
                item,
                ("id", "message", "changes", "status", "created_at", "resolved_at"),
            )
            for item in proposals
        ],
        "audit_events": [
            _serialize(
                item,
                (
                    "id",
                    "actor_token_id",
                    "action",
                    "resource_type",
                    "resource_id",
                    "details",
                    "created_at",
                ),
            )
            for item in audits
        ],
        "source_documents": [
            _serialize(
                item,
                (
                    "id",
                    "source_hash",
                    "filename",
                    "source_type",
                    "mime_type",
                    "file_size",
                    "page_count",
                    "parse_status",
                    "meta",
                    "created_at",
                ),
            )
            for item in documents
        ],
        "parsed_blocks": [
            _serialize(
                item,
                (
                    "id",
                    "evidence_id",
                    "doc_id",
                    "block_index",
                    "block_type",
                    "content",
                    "content_hash",
                    "char_start",
                    "char_end",
                    "page_no",
                    "bbox",
                    "time_start",
                    "time_end",
                    "section_path",
                    "image_ref",
                    "source_type",
                    "content_revision",
                    "source_metadata",
                    "created_at",
                ),
            )
            for item in parsed_blocks
        ],
        "wiki_pages": [
            _serialize(
                item,
                (
                    "id",
                    "slug",
                    "title",
                    "page_type",
                    "content",
                    "summary",
                    "version",
                    "last_edit_source",
                    "source_refs",
                    "chunk_refs",
                    "out_links",
                    "in_links",
                    "status",
                    "created_at",
                    "updated_at",
                ),
            )
            for item in wiki_pages
        ],
        "wiki_revisions": [
            _serialize(
                item,
                (
                    "id",
                    "page_id",
                    "version",
                    "title",
                    "page_type",
                    "content",
                    "summary",
                    "status",
                    "edit_source",
                    "edited_at",
                    "source_refs",
                    "chunk_refs",
                    "created_at",
                ),
            )
            for item in wiki_revisions
        ],
        "saved_jobs": [
            _serialize(
                item,
                (
                    "id", "title", "jd_text", "source_type", "source_url",
                    "notes", "created_at", "updated_at",
                ),
            )
            for item in saved_jobs
        ],
        "learning_progress": [
            _serialize(
                item,
                (
                    "id", "plan_id", "skill", "stage", "status", "evidence_ids",
                    "actual_hours", "note", "created_at", "updated_at",
                ),
            )
            for item in learning_progress
        ],
        "assessments": [
            _serialize(
                item,
                (
                    "id", "instrument", "version", "result_json", "answers_json",
                    "source", "consent", "taken_at", "created_at",
                ),
            )
            for item in assessments
        ],
        "constraints": [
            _serialize(
                item,
                ("id", "kind", "value", "strength", "source", "created_at", "updated_at"),
            )
            for item in constraints
        ],
        "dimensions": [
            _serialize(
                item,
                (
                    "id", "key", "label", "description", "source",
                    "enabled", "created_at", "updated_at",
                ),
            )
            for item in dimensions
        ],
        "profile_extensions": [
            _serialize(
                item,
                (
                    "id", "dimension_key", "value_json", "confidence",
                    "evidence_ids", "source", "enabled", "updated_at",
                ),
            )
            for item in extensions
        ],
        "runs": [_serialize(item, (
            "id", "operation", "status", "confirmation", "attempts", "result",
            "error_code", "created_at",
        )) for item in runs],
        "run_steps": [_serialize(item, (
            "run_id", "name", "status", "attempt", "updated_at",
        )) for item in steps],
        "run_events": [_serialize(item, (
            "run_id", "seq", "generation", "event_type", "data", "created_at",
        )) for item in events],
    }


async def delete_evidence_record(
    session: AsyncSession,
    *,
    record: Evidence,
    principal: Principal,
) -> dict:
    await scope(session, record.user_id, bump=True)
    await scope(session, record.user_id, DELETION, bump=True)
    locked = await session.scalar(
        select(Evidence.id).where(Evidence.id == record.id).with_for_update()
    )
    if locked is None:
        return {"deleted": True, "evidence_id": record.id}
    profile_items = list(
        await session.scalars(select(ProfileItem).where(ProfileItem.user_id == record.user_id))
    )
    removed_profile_items = 0
    updated_profile_items = 0
    for item in profile_items:
        if not _valid_refs(item.evidence_ids):
            await session.delete(item)
            removed_profile_items += 1
            continue
        if record.id not in item.evidence_ids:
            continue
        remaining = [value for value in item.evidence_ids if value != record.id]
        if remaining:
            item.evidence_ids = remaining
            # Retain only the lower bounds justified without the original source bundle.
            item.level = min(item.level, 2)
            item.confidence = min(item.confidence, 0.55)
            updated_profile_items += 1
        else:
            await session.delete(item)
            removed_profile_items += 1
    source_type = record.source_type
    evidence_id = record.id
    affected_analyses = await _redact_derived_data(session, record)
    reports = list(
        await session.scalars(
            select(CareerReport).where(CareerReport.user_id == record.user_id)
        )
    )
    stale_reports = 0
    for report in reports:
        if not report.privacy_redacted and (
            report.job_analysis_id in affected_analyses
            or _report_depends_on(report.content, evidence_id)
        ):
            report.is_stale = True
            report.privacy_redacted = True
            report.title = "已清除的报告"
            report.content = {}
            report.markdown = ""
            report.model_diagnostics = {}
            stale_reports += 1
    checkpoint_count = await _redact_conversation_references(
        session, user_id=record.user_id, evidence_id=evidence_id, original=record.content,
    )
    await session.execute(
        delete(ParsedBlock).where(
            ParsedBlock.user_id == record.user_id, ParsedBlock.evidence_id == evidence_id
        )
    )
    pages = list(await session.scalars(
        select(WikiPage).where(WikiPage.user_id == record.user_id).order_by(WikiPage.id)
        .with_for_update()
    ))
    removed_pages = {
        page.id
        for page in pages
        if (
            not page.privacy_redacted and (
                not _valid_refs(page.source_refs) or not _valid_refs(page.chunk_refs)
                or evidence_id in page.source_refs or evidence_id in page.chunk_refs
            )
        )
    }
    surviving_history = set()
    revisions = await session.scalars(
        select(WikiRevision).where(WikiRevision.user_id == record.user_id)
    )
    for revision in revisions:
        if (
            not _valid_refs(revision.source_refs)
            or not _valid_refs(revision.chunk_refs)
            or evidence_id in revision.source_refs
            or evidence_id in revision.chunk_refs
        ):
            await session.delete(revision)
        else:
            surviving_history.add(revision.page_id)
    for page in pages:
        if page.id not in removed_pages:
            continue
        if page.id not in surviving_history:
            await session.delete(page)
            continue
        page.privacy_redacted = True
        page.status = "archived"
        page.content = ""
        page.title = "已清除的页面"
        page.summary = None
        page.source_refs = []
        page.chunk_refs = []
        page.in_links = []
        page.out_links = []
    await session.delete(record)
    await enqueue_index(session, record.user_id, [evidence_id], action="delete")
    vector = {"status": "queued"}
    add_audit_event(
        session,
        principal=principal,
        action="evidence.deleted",
        resource_type="evidence",
        resource_id=evidence_id,
        details={
            "source_type": source_type,
            "updated_profile_items": updated_profile_items,
            "removed_profile_items": removed_profile_items,
            "vector_index": vector,
            "stale_reports": stale_reports,
            "removed_wiki_pages": len(removed_pages),
        },
    )
    await session.commit()
    checkpoint = {"status": "queued" if checkpoint_count else "deleted", "deleted": 0}
    await try_index_now(session, [evidence_id])
    if await session.get(EvidenceIndexWork, evidence_id) is None:
        vector.update(status="deleted", backend="qdrant")
    return {
        "deleted": True,
        "evidence_id": evidence_id,
        "updated_profile_items": updated_profile_items,
        "removed_profile_items": removed_profile_items,
        "vector_index": vector,
        "checkpoint_result": checkpoint,
        "stale_reports": stale_reports,
        "removed_wiki_pages": len(removed_pages),
    }


async def _count_user_records(
    session: AsyncSession, model: type, user_id: str
) -> int:
    return int(
        await session.scalar(
            select(func.count()).select_from(model).where(model.user_id == user_id)
        )
        or 0
    )


async def deletion_receipt(session: AsyncSession, receipt: AccountDeletionReceipt) -> dict:
    work = list(await session.scalars(select(DeletionWork).where(
        DeletionWork.receipt_id == receipt.id,
    )))
    vectors = [item for item in work if item.kind == "vector_user"]
    checkpoints = [item for item in work if item.kind == "checkpoint"]

    def status(items, default: str) -> str:
        states = {item.status for item in items}
        if "failed" in states:
            return "failed"
        if "pending" in states:
            return "queued"
        return "deleted" if states else default

    # No registered collection means the local/hash backend has no external
    # vectors to clean; that is a completed cleanup, not an unknown one.
    vector_status = status(vectors, "deleted")
    checkpoint_status = status(
        checkpoints, receipt.vector_result.get("checkpoint_status", "deleted"),
    )
    statuses = {vector_status, checkpoint_status}
    cleanup_status = (
        "failed" if statuses & {"failed", "unavailable"} else "pending" if "queued" in statuses
        else "completed" if statuses == {"deleted"} else "unknown"
    )
    return {
        "deleted": True,
        "receipt_id": receipt.id,
        "deleted_counts": receipt.deleted_counts,
        "vector_result": {"status": vector_status, "backend": "qdrant"},
        "checkpoint_result": {
            "status": checkpoint_status,
            "deleted": sum(item.status == "completed" for item in checkpoints)
            if checkpoints else receipt.vector_result.get("checkpoint_count", 0),
        },
        "cleanup_status": cleanup_status,
        "pending_targets": sum(item.status == "pending" for item in work),
        "completed_targets": sum(item.status == "completed" for item in work),
        "failed_targets": sum(item.status == "failed" for item in work),
        "cleanup_attempts": sum(item.attempts for item in work),
        "last_error_codes": sorted({item.last_error for item in work if item.last_error}),
        "created_at": receipt.created_at,
    }


async def delete_user_account(
    session: AsyncSession, *, principal: Principal,
) -> dict:
    user_id = principal.user_id
    await scope(session, user_id, bump=True)
    await scope(session, user_id, DELETION, bump=True)
    await scope(session, user_id, DELETED_ACCOUNT, bump=True)
    await session.scalars(
        select(AgentRun.id).where(AgentRun.user_id == user_id)
        .order_by(AgentRun.id).with_for_update()
    )
    thread_ids = list(
        await session.scalars(
            select(ConversationThread.thread_id).where(
                ConversationThread.user_id == user_id
            )
        )
    )
    settings = get_settings()
    checkpoint_threads = set(thread_ids)
    if settings.uses_postgres_checkpoint:
        checkpoint_threads.update(await session.scalars(
            select(ConversationMessage.thread_id)
            .where(ConversationMessage.user_id == user_id).distinct()
        ))
    deleted_counts = {
        "evidence": await _count_user_records(session, Evidence, user_id),
        "profile_items": await _count_user_records(session, ProfileItem, user_id),
        "job_analyses": await _count_user_records(session, JobAnalysis, user_id),
        "career_reports": await _count_user_records(session, CareerReport, user_id),
        "profile_update_proposals": await _count_user_records(
            session, ProfileUpdateProposal, user_id
        ),
        "conversation_threads": len(thread_ids),
        "conversation_messages": await _count_user_records(session, ConversationMessage, user_id),
        "source_documents": await _count_user_records(session, SourceDocument, user_id),
        "parsed_blocks": await _count_user_records(session, ParsedBlock, user_id),
        "wiki_pages": await _count_user_records(session, WikiPage, user_id),
        "wiki_revisions": await _count_user_records(session, WikiRevision, user_id),
        "saved_jobs": await _count_user_records(session, SavedJob, user_id),
        "learning_progress": await _count_user_records(session, LearningProgress, user_id),
        "assessment_results": await _count_user_records(session, AssessmentResult, user_id),
        "user_constraints": await _count_user_records(session, UserConstraint, user_id),
        "dimension_definitions": await _count_user_records(session, DimensionDefinition, user_id),
        "profile_extensions": await _count_user_records(session, ProfileExtension, user_id),
        "audit_events": await _count_user_records(session, AuditEvent, user_id),
        "access_tokens": await _count_user_records(session, AccessToken, user_id),
        "runs": await _count_user_records(session, AgentRun, user_id),
        "run_steps": await _count_user_records(session, RunStep, user_id),
        "run_events": await _count_user_records(session, RunEvent, user_id),
    }

    pending_ids = set(await session.scalars(
        select(EvidenceIndexWork.evidence_id).where(EvidenceIndexWork.user_id == user_id)
    ))
    pending_ids.update(await session.scalars(
        select(Evidence.id).where(Evidence.user_id == user_id)
    ))
    if pending_ids:
        sorted_ids = sorted(pending_ids)
        for offset in range(0, len(sorted_ids), 500):
            await enqueue_index(session, user_id, sorted_ids[offset:offset + 500], action="delete")
    await session.execute(delete(RunScope).where(
        RunScope.user_id == user_id, RunScope.key.not_in((INPUT, DELETION, DELETED_ACCOUNT)),
    ))
    for model in (
        RunEvent,
        RunStep,
        AgentRun,
        CareerReport,
        JobAnalysis,
        ProfileUpdateProposal,
        ProfileItem,
        ProfileSuppression,
        Evidence,
        ParsedBlock,
        SourceDocument,
        WikiRevision,
        WikiPage,
        SavedJob,
        LearningProgress,
        AssessmentResult,
        UserConstraint,
        DimensionDefinition,
        ProfileExtension,
        ConversationThread,
        ConversationMessage,
        AuditEvent,
        AccessToken,
    ):
        await session.execute(delete(model).where(model.user_id == user_id))

    vector_result = {"status": "queued", "backend": "qdrant"}
    checkpoint_status = (
        "queued" if settings.uses_postgres_checkpoint and checkpoint_threads else "deleted"
    )
    subject_hash = hashlib.sha256(
        f"{settings.auth_token_pepper}:deleted-user:{user_id}".encode()
    ).hexdigest()
    receipt = AccountDeletionReceipt(
        subject_hash=subject_hash,
        deleted_counts=deleted_counts,
        vector_result={
            **vector_result,
            "checkpoint_status": checkpoint_status,
            "checkpoint_count": 0,
        },
    )
    session.add(receipt)
    await session.flush()
    session.add_all(
        DeletionWork(
            receipt_id=receipt.id, kind="vector_user", subject=user_id, collection=collection,
        )
        for collection in await cleanup_collections(session)
    )
    if settings.uses_postgres_checkpoint:
        session.add_all(
            DeletionWork(receipt_id=receipt.id, kind="checkpoint", subject=thread)
            for thread in checkpoint_threads
        )
    await session.commit()
    await session.refresh(receipt)
    return await deletion_receipt(session, receipt)
