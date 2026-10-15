from typing import Annotated

from fastapi import Depends, Header, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models import User, UserStatus, WorkspaceRole
from app.services.auth import AuthTokenError, parse_access_token
from app.services.workspaces import WorkspaceAccess, WorkspaceAccessError, resolve_workspace_access

_bearer = HTTPBearer(auto_error=False)
SessionDep = Annotated[Session, Depends(get_db)]


def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
    db: SessionDep,
) -> User:
    """验证 Bearer 令牌并从数据库重新确认账号状态。"""
    if credentials is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="请先登录")
    try:
        payload = parse_access_token(credentials.credentials)
        user_id = int(payload["sub"])
    except (AuthTokenError, KeyError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="登录状态无效或已过期"
        ) from exc
    user = db.scalar(select(User).where(User.id == user_id, User.status == UserStatus.ACTIVE.value))
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="账号不存在或已停用")
    return user


def get_workspace_access(
    user: Annotated[User, Depends(get_current_user)],
    db: SessionDep,
    x_workspace_id: Annotated[int | None, Header(alias="X-Workspace-ID")] = None,
) -> WorkspaceAccess:
    """从成员关系解析当前工作空间，禁止信任请求体提供的租户归属。"""
    try:
        return resolve_workspace_access(db, user=user, workspace_id=x_workspace_id)
    except WorkspaceAccessError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc


def require_roles(*roles: WorkspaceRole):
    """创建按工作空间角色授权的依赖，供配置与审批等受保护接口复用。"""

    def check_role(
        access: Annotated[WorkspaceAccess, Depends(get_workspace_access)],
    ) -> WorkspaceAccess:
        if access.role not in {role.value for role in roles}:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="当前角色无权执行此操作"
            )
        return access

    return check_role


require_admin = require_roles(WorkspaceRole.ADMIN)
require_high_risk_approval = require_roles(WorkspaceRole.SUPERVISOR, WorkspaceRole.ADMIN)
