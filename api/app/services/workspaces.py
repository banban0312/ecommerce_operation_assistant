from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import MembershipStatus, User, Workspace, WorkspaceMembership, WorkspaceStatus


class WorkspaceAccessError(ValueError):
    """用户不是目标工作空间的有效成员。"""


@dataclass(frozen=True)
class WorkspaceAccess:
    workspace: Workspace
    membership: WorkspaceMembership
    user: User

    @property
    def role(self) -> str:
        return self.membership.role


def list_user_workspaces(db: Session, user: User) -> list[WorkspaceAccess]:
    """只返回用户与工作空间都处于启用状态的成员关系。"""
    rows = db.execute(
        select(WorkspaceMembership, Workspace)
        .join(Workspace, Workspace.id == WorkspaceMembership.workspace_id)
        .where(
            WorkspaceMembership.user_id == user.id,
            WorkspaceMembership.status == MembershipStatus.ACTIVE.value,
            Workspace.status == WorkspaceStatus.ACTIVE.value,
        )
        .order_by(Workspace.id)
    )
    return [
        WorkspaceAccess(workspace=workspace, membership=membership, user=user)
        for membership, workspace in rows
    ]


def resolve_workspace_access(
    db: Session, *, user: User, workspace_id: int | None
) -> WorkspaceAccess:
    """校验工作空间归属；缺失、停用或跨租户 ID 一律拒绝。"""
    statement = (
        select(WorkspaceMembership, Workspace)
        .join(Workspace, Workspace.id == WorkspaceMembership.workspace_id)
        .where(
            WorkspaceMembership.user_id == user.id,
            WorkspaceMembership.status == MembershipStatus.ACTIVE.value,
            Workspace.status == WorkspaceStatus.ACTIVE.value,
        )
    )
    if workspace_id is not None:
        statement = statement.where(Workspace.id == workspace_id)
    row = db.execute(statement.order_by(Workspace.id)).first()
    if row is None:
        raise WorkspaceAccessError("工作空间不存在或当前用户无访问权限")
    membership, workspace = row
    return WorkspaceAccess(workspace=workspace, membership=membership, user=user)
