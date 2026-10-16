import uuid

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from omnitest_api.models import AuditLog, User
from omnitest_api.security.redaction import redact_mapping


def record(
    db: AsyncSession,
    *,
    action: str,
    actor: User | None,
    request: Request | None = None,
    project_id: uuid.UUID | None = None,
    target_type: str | None = None,
    target_id: object = None,
    details: dict[str, object] | None = None,
    actor_email: str | None = None,
) -> None:
    """Ghi audit vào cùng transaction với thao tác. Chi tiết được lọc khóa nhạy cảm lần nữa cho chắc."""
    db.add(
        AuditLog(
            actor_id=actor.id if actor else None,
            actor_email=actor.email if actor else actor_email,
            project_id=project_id,
            action=action,
            target_type=target_type,
            target_id=str(target_id) if target_id is not None else None,
            details=redact_mapping(details or {}),
            ip=request.client.host if request and request.client else None,
        )
    )
