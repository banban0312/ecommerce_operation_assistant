from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.dependencies import SessionDep, get_current_user, get_workspace_access, require_admin
from app.core.config import get_settings
from app.models import MembershipStatus, User, UserStatus, WorkspaceMembership
from app.schemas.auth import (
    CreateMemberRequest,
    LoginRequest,
    LoginResponse,
    MembershipRead,
    UserRead,
    WorkspaceMemberRead,
)
from app.services.audit import record_audit_event
from app.services.auth import AuthTokenError, create_access_token
from app.services.users import hash_password, verify_password
from app.services.workspaces import WorkspaceAccess, list_user_workspaces

router = APIRouter(prefix="/auth", tags=["authentication"])
CurrentUser = Annotated[User, Depends(get_current_user)]


def _user_read(db: Session, user: User) -> UserRead:
    memberships = list_user_workspaces(db, user)
    return UserRead(
        id=user.id,
        email=user.email,
        display_name=user.display_name,
        status=user.status,
        last_login_at=user.last_login_at,
        memberships=[
            MembershipRead(
                workspace_id=item.workspace.id,
                workspace_name=item.workspace.name,
                role=item.role,
            )
            for item in memberships
        ],
    )


@router.post("/login", response_model=LoginResponse)
def login(payload: LoginRequest, db: SessionDep) -> LoginResponse:
    """验证账号密码，更新最后登录时间并签发短期 Bearer 令牌。"""
    email = payload.email.strip().lower()
    user = db.scalar(select(User).where(User.email == email))
    if (
        user is None
        or user.status != UserStatus.ACTIVE.value
        or not verify_password(payload.password, user.password_hash)
    ):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="邮箱或密码错误")

    memberships = list_user_workspaces(db, user)
    if not memberships:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="账号没有可用的工作空间")
    try:
        token = create_access_token(user)
    except AuthTokenError as exc:
        raise HTTPException(status_code=503, detail="认证服务尚未配置") from exc

    user.last_login_at = datetime.now(UTC)
    db.commit()
    return LoginResponse(
        access_token=token,
        expires_in=get_settings().auth_token_expire_minutes * 60,
        user=_user_read(db, user),
    )


@router.get("/me", response_model=UserRead)
def me(db: SessionDep, user: CurrentUser) -> UserRead:
    """返回当前账号及其有效工作空间成员关系，不包含密码摘要或访问令牌。"""
    return _user_read(db, user)


@router.get("/workspaces", response_model=list[MembershipRead])
def workspaces(db: SessionDep, user: CurrentUser) -> list[MembershipRead]:
    """列出当前用户可进入的工作空间和对应角色。"""
    return _user_read(db, user).memberships


@router.get(
    "/workspaces/{workspace_id}/members", response_model=list[WorkspaceMemberRead]
)
def list_members(
    workspace_id: int,
    db: SessionDep,
    access: Annotated[WorkspaceAccess, Depends(get_workspace_access)],
    _admin: Annotated[WorkspaceAccess, Depends(require_admin)],
) -> list[WorkspaceMemberRead]:
    """仅工作区管理员可以查看该工作区成员及其角色，不返回认证凭据。"""
    if access.workspace.id != workspace_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="无权管理此工作空间")
    rows = db.execute(
        select(WorkspaceMembership, User)
        .join(User, User.id == WorkspaceMembership.user_id)
        .where(WorkspaceMembership.workspace_id == workspace_id)
        .order_by(User.display_name, User.email)
    ).all()
    return [
        WorkspaceMemberRead(
            id=user.id,
            email=user.email,
            display_name=user.display_name,
            role=membership.role,
            status=(
                MembershipStatus.DISABLED.value
                if membership.status != MembershipStatus.ACTIVE.value
                else user.status
            ),
            last_login_at=user.last_login_at,
        )
        for membership, user in rows
    ]


@router.post("/workspaces/{workspace_id}/members", status_code=status.HTTP_201_CREATED)
def create_member(
    workspace_id: int,
    payload: CreateMemberRequest,
    db: SessionDep,
    access: Annotated[WorkspaceAccess, Depends(get_workspace_access)],
    _admin: Annotated[WorkspaceAccess, Depends(require_admin)],
) -> dict:
    """仅允许目标工作空间管理员添加成员，并在同一事务记录审计事件。"""
    if access.workspace.id != workspace_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="无权管理此工作空间")

    email = payload.email.strip().lower()
    display_name = payload.display_name.strip()
    if not display_name:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="显示名称不能为空"
        )
    user = db.scalar(select(User).where(User.email == email))
    if user is None:
        user = User(
            email=email,
            display_name=display_name,
            password_hash=hash_password(payload.password),
            status=UserStatus.ACTIVE.value,
        )
        db.add(user)
        db.flush()
    elif user.status != UserStatus.ACTIVE.value:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="账号已停用")

    membership = db.scalar(
        select(WorkspaceMembership).where(
            WorkspaceMembership.workspace_id == workspace_id,
            WorkspaceMembership.user_id == user.id,
        )
    )
    if membership is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="该用户已是工作空间成员")

    membership = WorkspaceMembership(
        workspace_id=workspace_id,
        user_id=user.id,
        role=payload.role,
        status=MembershipStatus.ACTIVE.value,
    )
    db.add(membership)
    record_audit_event(
        db,
        access=access,
        action="workspace.member_created",
        resource_type="user",
        resource_id=str(user.id),
        details={"role": payload.role},
    )
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="成员信息冲突") from exc
    return {
        "id": user.id,
        "email": user.email,
        "display_name": user.display_name,
        "role": membership.role,
    }
