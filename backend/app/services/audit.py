from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit import AuditEvent
from app.security import Principal


def add_audit_event(
    session: AsyncSession,
    *,
    principal: Principal,
    action: str,
    resource_type: str,
    resource_id: str | None = None,
    details: dict | None = None,
) -> AuditEvent:
    event = AuditEvent(
        user_id=principal.user_id,
        actor_token_id=principal.token_id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        details=details or {},
    )
    session.add(event)
    return event


async def list_audit_events(
    session: AsyncSession, *, user_id: str, limit: int = 100
) -> list[AuditEvent]:
    result = await session.scalars(
        select(AuditEvent)
        .where(AuditEvent.user_id == user_id)
        .order_by(AuditEvent.created_at.desc())
        .limit(limit)
    )
    return list(result)
