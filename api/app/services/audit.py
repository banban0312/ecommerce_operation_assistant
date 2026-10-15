from sqlalchemy.orm import Session

from app.models import AuditEvent
from app.services.workspaces import WorkspaceAccess


def record_audit_event(
    db: Session,
    *,
    access: WorkspaceAccess,
    action: str,
    resource_type: str,
    resource_id: str | None = None,
    details: dict | None = None,
) -> AuditEvent:
    """把操作者和操作放入当前事务，由业务操作一并提交或回滚。"""
    event = AuditEvent(
        workspace_id=access.workspace.id,
        actor_user_id=access.user.id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        details=details,
    )
    db.add(event)
    return event
