import hashlib
from datetime import UTC, datetime

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.graph.career import delete_career_threads
from app.models.access_token import AccessToken
from app.models.account_deletion import AccountDeletionReceipt
from app.models.audit import AuditEvent
from app.models.career_report import CareerReport
from app.models.conversation import ConversationMessage, ConversationThread
from app.models.evidence import Evidence
from app.models.job_analysis import JobAnalysis
from app.models.parsed_block import ParsedBlock
from app.models.profile import ProfileItem
from app.models.profile_update import ProfileUpdateProposal
from app.models.source_document import SourceDocument
from app.models.wiki import WikiPage, WikiRevision
from app.retrieval.service import delete_evidence_index, delete_user_index
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
    }


async def delete_evidence_record(
    session: AsyncSession,
    *,
    record: Evidence,
    principal: Principal,
) -> dict:
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
    vector = await delete_evidence_index(evidence_id)
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
        "audit_events": await _count_user_records(session, AuditEvent, user_id),
        "access_tokens": await _count_user_records(session, AccessToken, user_id),
    }

    vector_result = await delete_user_index(user_id)
    checkpoint_result = await delete_career_threads(thread_ids)
    for model in (
        CareerReport,
        JobAnalysis,
        ProfileUpdateProposal,
        ProfileItem,
        Evidence,
        ParsedBlock,
        SourceDocument,
        WikiRevision,
        WikiPage,
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
