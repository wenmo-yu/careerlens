import hashlib
from datetime import UTC, datetime

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.graph.career import delete_career_threads
from app.models.access_token import AccessToken
from app.models.account_deletion import AccountDeletionReceipt
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
from app.retrieval.service import delete_user_index
from app.runtime.index_outbox import enqueue_index, try_index_now
from app.runtime.store import DELETION, scope
from app.security import Principal
from app.services.audit import add_audit_event


def _serialize(record, fields: tuple[str, ...]) -> dict:
    result = {}
    for field in fields:
        value = getattr(record, field)
        result[field] = value.isoformat() if isinstance(value, datetime) else value
    return result


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
        await session.scalars(select(CareerReport).where(CareerReport.user_id == user_id))
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
        await session.scalars(select(WikiPage).where(WikiPage.user_id == user_id))
    )
    wiki_revisions = list(
        await session.scalars(select(WikiRevision).where(WikiRevision.user_id == user_id))
    )
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
            for item in jobs
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
        if record.id not in item.evidence_ids:
            continue
        remaining = [value for value in item.evidence_ids if value != record.id]
        if remaining:
            item.evidence_ids = remaining
            updated_profile_items += 1
        else:
            await session.delete(item)
            removed_profile_items += 1
    source_type = record.source_type
    source_name = record.source_name
    evidence_id = record.id
    reports = list(
        await session.scalars(
            select(CareerReport).where(CareerReport.user_id == record.user_id)
        )
    )
    stale_reports = 0
    for report in reports:
        referenced = report.content.get("referenced_evidence_ids", [])
        catalog_ids = [item.get("id") for item in report.content.get("evidence_catalog", [])]
        matching_ids = {
            item_id
            for match in report.content.get("job_matching", [])
            for item_id in match.get("evidence_ids", [])
        }
        if evidence_id in referenced or evidence_id in catalog_ids or evidence_id in matching_ids:
            report.is_stale = True
            stale_reports += 1
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
        if evidence_id in page.source_refs or evidence_id in page.chunk_refs
    }
    for page in pages:
        if page.id in removed_pages:
            await session.delete(page)
    revisions = await session.scalars(
        select(WikiRevision).where(WikiRevision.user_id == record.user_id)
    )
    for revision in revisions:
        if (
            revision.page_id in removed_pages
            or revision.source_refs is None
            or revision.chunk_refs is None
            or evidence_id in revision.source_refs
            or evidence_id in revision.chunk_refs
        ):
            await session.delete(revision)
    await session.delete(record)
    await enqueue_index(session, record.user_id, [evidence_id], action="delete")
    vector = {"status": "skipped" if get_settings().retrieval_backend == "local" else "queued"}
    add_audit_event(
        session,
        principal=principal,
        action="evidence.deleted",
        resource_type="evidence",
        resource_id=evidence_id,
        details={
            "source_type": source_type,
            "source_name": source_name,
            "updated_profile_items": updated_profile_items,
            "removed_profile_items": removed_profile_items,
            "vector_index": vector,
            "stale_reports": stale_reports,
            "removed_wiki_pages": len(removed_pages),
        },
    )
    await session.commit()
    await try_index_now(session, [evidence_id])
    return {
        "deleted": True,
        "evidence_id": evidence_id,
        "updated_profile_items": updated_profile_items,
        "removed_profile_items": removed_profile_items,
        "vector_index": vector,
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


async def delete_user_account(
    session: AsyncSession, *, principal: Principal
) -> dict:
    user_id = principal.user_id
    await scope(session, user_id)
    await scope(session, user_id, DELETION)
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
    try:
        vector_result = await delete_user_index(user_id)
    except Exception:
        vector_result = {"status": "fallback", "backend": "local"}
    if vector_result["status"] != "fallback":
        await session.execute(delete(EvidenceIndexWork).where(EvidenceIndexWork.user_id == user_id))
    elif pending_ids:
        vector_result = {**vector_result, "status": "queued"}
    checkpoint_result = await delete_career_threads(thread_ids)
    for model in (
        RunEvent,
        RunStep,
        AgentRun,
        RunScope,
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

    settings = get_settings()
    subject_hash = hashlib.sha256(
        f"{settings.auth_token_pepper}:deleted-user:{user_id}".encode()
    ).hexdigest()
    receipt = AccountDeletionReceipt(
        subject_hash=subject_hash,
        deleted_counts=deleted_counts,
        vector_result={
            **vector_result,
            "checkpoint_status": checkpoint_result["status"],
            "checkpoint_count": checkpoint_result["deleted"],
        },
    )
    session.add(receipt)
    await session.commit()
    await session.refresh(receipt)
    return {
        "deleted": True,
        "receipt_id": receipt.id,
        "deleted_counts": deleted_counts,
        "vector_result": vector_result,
        "checkpoint_result": checkpoint_result,
        "created_at": receipt.created_at,
    }
