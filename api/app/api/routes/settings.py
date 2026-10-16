"""管理员服务配置、任务规则、平台占位和审计接口。"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select

from app.api.dependencies import SessionDep, require_admin
from app.models import AuditEvent, PlatformAccountPlaceholder, ServiceConfig, Store, TaskRule, User
from app.schemas.settings import (
    ConfigAuditRead,
    ConnectionCheckRead,
    PlatformAccountRead,
    PlatformAccountUpdate,
    ServiceConfigUpdate,
    SettingsRead,
    Target,
    TaskRulesUpdate,
)
from app.services.audit import record_audit_event
from app.services.secret_storage import encrypt_secret
from app.services.service_settings import check_connection, read_services, runtime_service
from app.services.workspaces import WorkspaceAccess

router = APIRouter(prefix="/settings", tags=["settings"])
Admin = Annotated[WorkspaceAccess, Depends(require_admin)]

DEFAULT_RULES = TaskRulesUpdate(
    timeout_seconds=300,
    max_retries=3,
    max_concurrency=2,
    image_poll_interval_seconds=5,
    image_poll_max_attempts=24,
    video_poll_interval_seconds=10,
    video_poll_max_attempts=36,
)


def _rules(db: SessionDep, workspace_id: int) -> TaskRulesUpdate:
    row = db.scalar(select(TaskRule).where(TaskRule.workspace_id == workspace_id))
    if row is None:
        return DEFAULT_RULES
    return TaskRulesUpdate.model_validate(
        {key: getattr(row, key) for key in TaskRulesUpdate.model_fields}
    )


def _platforms(db: SessionDep, workspace_id: int) -> list[PlatformAccountRead]:
    rows = db.execute(
        select(Store, PlatformAccountPlaceholder)
        .outerjoin(PlatformAccountPlaceholder, PlatformAccountPlaceholder.store_id == Store.id)
        .where(Store.workspace_id == workspace_id, Store.status == "active")
        .order_by(Store.id.desc())
    ).all()
    return [
        PlatformAccountRead(
            store_id=store.id,
            store_name=store.name,
            platform=store.platform,
            account_identifier=placeholder.account_identifier if placeholder else "",
            authorization_status=placeholder.authorization_status
            if placeholder
            else "not_connected",
        )
        for store, placeholder in rows
    ]


@router.get("", response_model=SettingsRead)
def get_settings_page(db: SessionDep, admin: Admin) -> SettingsRead:
    """管理员读取当前工作空间配置；响应不包含任何密钥字段。"""
    workspace_id = admin.workspace.id
    return SettingsRead(
        services=read_services(db, workspace_id),
        rules=_rules(db, workspace_id),
        platforms=_platforms(db, workspace_id),
    )


@router.patch("/services/{target}", response_model=SettingsRead)
def update_service(
    target: Target, payload: ServiceConfigUpdate, db: SessionDep, admin: Admin
) -> SettingsRead:
    """保存工作空间服务参数；密钥加密后写库，审计中不记录密钥。"""
    allowed = {"video": {"none", "jimeng", "dashscope"}, "text": {"openai"}, "image": {"openai"}}
    if payload.provider not in allowed[target]:
        raise HTTPException(status_code=422, detail="供应商与服务类型不匹配")
    row = db.scalar(
        select(ServiceConfig).where(
            ServiceConfig.workspace_id == admin.workspace.id,
            ServiceConfig.target == target,
        )
    )
    before = (
        {"provider": row.provider, "model": row.model, "endpoint_url": row.endpoint_url}
        if row
        else None
    )
    if row is None:
        row = ServiceConfig(
            workspace_id=admin.workspace.id, target=target, updated_by=admin.user.id
        )
        db.add(row)
    row.provider = payload.provider
    row.model = payload.model.strip()
    row.endpoint_url = payload.endpoint_url
    if payload.api_key:
        row.api_key_encrypted = encrypt_secret(payload.api_key)
    elif payload.clear_api_key:
        row.api_key_encrypted = None
    row.updated_by = admin.user.id
    record_audit_event(
        db,
        access=admin,
        action="settings.service_updated",
        resource_type="service_config",
        resource_id=target,
        details={
            "before": before,
            "after": {
                "provider": row.provider,
                "model": row.model,
                "endpoint_url": row.endpoint_url,
            },
            "api_key_changed": bool(payload.api_key or payload.clear_api_key),
        },
    )
    db.commit()
    return get_settings_page(db, admin)


@router.post("/services/{target}/check", response_model=ConnectionCheckRead)
def check_service(target: Target, db: SessionDep, admin: Admin) -> ConnectionCheckRead:
    """执行明确的外部元数据请求；结果只写状态码与安全描述。"""
    service = next(item for item in read_services(db, admin.workspace.id) if item.target == target)
    _, _, _, api_key = runtime_service(db, admin.workspace.id, target)
    result = check_connection(service, api_key=api_key)
    record_audit_event(
        db,
        access=admin,
        action="settings.connection_checked",
        resource_type="service_config",
        resource_id=target,
        details={"ok": result.ok, "code": result.code},
    )
    db.commit()
    return result


@router.put("/rules", response_model=TaskRulesUpdate)
def update_rules(payload: TaskRulesUpdate, db: SessionDep, admin: Admin) -> TaskRulesUpdate:
    """任务规则与变更审计在同一事务中提交。"""
    row = db.scalar(select(TaskRule).where(TaskRule.workspace_id == admin.workspace.id))
    before = _rules(db, admin.workspace.id).model_dump()
    if row is None:
        row = TaskRule(workspace_id=admin.workspace.id, updated_by=admin.user.id)
        db.add(row)
    for field, value in payload.model_dump().items():
        setattr(row, field, value)
    row.updated_by = admin.user.id
    record_audit_event(
        db,
        access=admin,
        action="settings.rules_updated",
        resource_type="task_rules",
        resource_id=str(admin.workspace.id),
        details={"before": before, "after": payload.model_dump()},
    )
    db.commit()
    return payload


@router.patch("/platform-accounts/{store_id}", response_model=PlatformAccountRead)
def update_platform_account(
    store_id: int,
    payload: PlatformAccountUpdate,
    db: SessionDep,
    admin: Admin,
) -> PlatformAccountRead:
    """仅存账号标识与占位状态，校验店铺归属，不接收平台凭据。"""
    store = db.get(Store, store_id)
    if store is None or store.workspace_id != admin.workspace.id or store.status != "active":
        raise HTTPException(status_code=404, detail="店铺不存在")
    row = db.scalar(
        select(PlatformAccountPlaceholder).where(PlatformAccountPlaceholder.store_id == store_id)
    )
    before_status = row.authorization_status if row else "not_connected"
    if row is None:
        row = PlatformAccountPlaceholder(store_id=store_id, updated_by=admin.user.id)
        db.add(row)
    changed_identifier = row.account_identifier != payload.account_identifier.strip()
    row.account_identifier = payload.account_identifier.strip()
    row.authorization_status = payload.authorization_status
    row.updated_by = admin.user.id
    record_audit_event(
        db,
        access=admin,
        action="settings.platform_placeholder_updated",
        resource_type="store",
        resource_id=str(store_id),
        details={
            "before_status": before_status,
            "after_status": row.authorization_status,
            "account_identifier_changed": changed_identifier,
        },
    )
    db.commit()
    return PlatformAccountRead(
        store_id=store.id,
        store_name=store.name,
        platform=store.platform,
        account_identifier=row.account_identifier,
        authorization_status=row.authorization_status,
    )


@router.get("/audit", response_model=list[ConfigAuditRead])
def list_config_audit(
    db: SessionDep,
    admin: Admin,
    limit: Annotated[int, Query(ge=1, le=100)] = 30,
) -> list[ConfigAuditRead]:
    """按工作空间返回配置记录；不公开其他业务审计或凭据。"""
    rows = db.execute(
        select(AuditEvent, User.display_name)
        .join(User, User.id == AuditEvent.actor_user_id)
        .where(AuditEvent.workspace_id == admin.workspace.id, AuditEvent.action.like("settings.%"))
        .order_by(AuditEvent.id.desc())
        .limit(limit)
    ).all()
    return [
        ConfigAuditRead(
            id=event.id,
            actor_name=name,
            action=event.action,
            resource_type=event.resource_type,
            resource_id=event.resource_id,
            details=event.details,
            created_at=event.created_at,
        )
        for event, name in rows
    ]
