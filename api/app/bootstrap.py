"""交互式初始化首个管理员账号，不在代码或仓库中放置默认密码。"""

import re
from getpass import getpass

from sqlalchemy import select

from app.db.session import get_session_factory
from app.models import (
    MembershipStatus,
    User,
    UserStatus,
    Workspace,
    WorkspaceMembership,
    WorkspaceRole,
    WorkspaceStatus,
)
from app.services.users import hash_password


def main() -> None:
    email = input("管理员邮箱: ").strip().lower()
    display_name = input("显示名称: ").strip()
    if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email):
        raise SystemExit("邮箱格式不正确。")
    if not display_name or len(display_name) > 120:
        raise SystemExit("显示名称不能为空，且不能超过 120 个字符。")

    password = getpass("设置密码（至少 12 位）: ")
    confirmation = getpass("再次输入密码: ")
    if len(password) < 12:
        raise SystemExit("密码至少需要 12 位。")
    if password != confirmation:
        raise SystemExit("两次输入的密码不一致。")

    with get_session_factory()() as db:
        if db.scalar(select(User.id).limit(1)) is not None:
            raise SystemExit("系统中已存在用户；请由管理员流程创建其他成员。")
        workspace = Workspace(
            slug="default", name="默认工作区", status=WorkspaceStatus.ACTIVE.value
        )
        db.add(workspace)
        db.flush()
        user = User(
            email=email,
            display_name=display_name,
            password_hash=hash_password(password),
            status=UserStatus.ACTIVE.value,
        )
        db.add(user)
        db.flush()
        db.add(
            WorkspaceMembership(
                workspace_id=workspace.id,
                user_id=user.id,
                role=WorkspaceRole.ADMIN.value,
                status=MembershipStatus.ACTIVE.value,
            )
        )
        db.commit()
    print(f"已创建管理员 {email} 和默认工作区。请使用该账号登录。")


if __name__ == "__main__":
    main()
