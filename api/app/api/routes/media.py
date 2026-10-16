"""M5 异步媒体任务、时间线和素材审核接口。"""

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import desc, select
from sqlalchemy.exc import IntegrityError

from app.api.dependencies import SessionDep, get_workspace_access, require_high_risk_approval
from app.models import (
    ContentVersion,
    GenerationEvent,
    GenerationJob,
    MediaAsset,
    Product,
    Store,
    TaskRule,
)
from app.schemas.media import AssetRead, AssetUpdate, EventRead, JobCreate, JobRead
from app.services.audit import record_audit_event
from app.services.workspaces import WorkspaceAccess
from app.worker.tasks import run_generation_job

router = APIRouter(prefix="/media", tags=["media"])
Access = Annotated[WorkspaceAccess, Depends(get_workspace_access)]


def _product(db: SessionDep, access: WorkspaceAccess, product_id: int) -> Product:
    product = db.get(Product, product_id)
    store = db.get(Store, product.store_id) if product else None
    if product is None:
        raise HTTPException(404, "商品不存在")
    if store is None or store.workspace_id != access.workspace.id:
        raise HTTPException(403, "无权访问此商品")
    return product


def _job(db: SessionDep, access: WorkspaceAccess, job_id: int) -> GenerationJob:
    job = db.get(GenerationJob, job_id)
    if job is None:
        raise HTTPException(404, "任务不存在")
    if job.workspace_id != access.workspace.id:
        raise HTTPException(403, "无权访问此任务")
    return job


def _read(db, job):
    asset = db.scalar(select(MediaAsset).where(MediaAsset.job_id == job.id))
    events = list(
        db.scalars(
            select(GenerationEvent)
            .where(GenerationEvent.job_id == job.id)
            .order_by(GenerationEvent.created_at)
        )
    )
    return JobRead.model_validate(job, from_attributes=True).model_copy(
        update={
            "events": [EventRead.model_validate(e) for e in events],
            "asset": AssetRead.model_validate(asset) if asset else None,
        }
    )


@router.post("/products/{product_id}/jobs", response_model=JobRead, status_code=202)
def create_job(product_id: int, payload: JobCreate, db: SessionDep, access: Access):
    _product(db, access, product_id)
    content = db.get(ContentVersion, payload.content_version_id)
    expected = "image_idea" if payload.media_type == "image" else "video_script"
    if (
        content is None
        or content.product_id != product_id
        or content.content_type != expected
        or content.status != "confirmed"
    ):
        raise HTTPException(422, "必须使用当前商品已确认的对应创意版本")
    existing = db.scalar(
        select(GenerationJob).where(
            GenerationJob.workspace_id == access.workspace.id,
            GenerationJob.idempotency_key == payload.idempotency_key,
        )
    )
    if existing:
        return _read(db, existing)
    rule = db.scalar(select(TaskRule).where(TaskRule.workspace_id == access.workspace.id))
    job = GenerationJob(
        workspace_id=access.workspace.id,
        product_id=product_id,
        content_version_id=content.id,
        media_type=payload.media_type,
        idempotency_key=payload.idempotency_key,
        provider="openai" if payload.media_type == "image" else "video",
        max_retries=rule.max_retries if rule else 3,
        created_by=access.user.id,
    )
    db.add(job)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        existing = db.scalar(
            select(GenerationJob).where(
                GenerationJob.workspace_id == access.workspace.id,
                GenerationJob.idempotency_key == payload.idempotency_key,
            )
        )
        if existing:
            return _read(db, existing)
        raise HTTPException(409, "任务幂等键冲突") from exc
    db.add(GenerationEvent(job_id=job.id, status="pending", message="任务已排队"))
    record_audit_event(
        db,
        access=access,
        action="media_job_create",
        resource_type="generation_job",
        resource_id=str(job.id),
    )
    db.commit()
    db.refresh(job)
    try:
        run_generation_job.delay(job.id)
    except Exception:
        pass
    return _read(db, job)


@router.get("/products/{product_id}/jobs", response_model=list[JobRead])
def list_jobs(product_id: int, db: SessionDep, access: Access):
    _product(db, access, product_id)
    return [
        _read(db, j)
        for j in db.scalars(
            select(GenerationJob)
            .where(GenerationJob.product_id == product_id)
            .order_by(desc(GenerationJob.created_at))
        )
    ]


@router.get("/jobs/{job_id}", response_model=JobRead)
def get_job(job_id: int, db: SessionDep, access: Access):
    return _read(db, _job(db, access, job_id))


@router.post("/jobs/{job_id}/cancel", response_model=JobRead)
def cancel_job(job_id: int, db: SessionDep, access: Access):
    job = _job(db, access, job_id)
    if job.status in {"succeeded", "failed", "timeout", "cancelled"}:
        raise HTTPException(409, "当前任务不可取消")
    job.cancel_requested = True
    if job.status == "pending":
        job.status = "cancelled"
        job.finished_at = datetime.now(UTC)
    db.add(GenerationEvent(job_id=job.id, status="cancelled", message="已提交取消请求"))
    record_audit_event(
        db,
        access=access,
        action="media_job_cancel",
        resource_type="generation_job",
        resource_id=str(job.id),
    )
    db.commit()
    db.refresh(job)
    return _read(db, job)


@router.post("/jobs/{job_id}/retry", response_model=JobRead, status_code=202)
def retry_job(job_id: int, db: SessionDep, access: Access):
    job = _job(db, access, job_id)
    if job.status not in {"failed", "timeout", "cancelled"}:
        raise HTTPException(409, "只有失败、超时或已取消任务可重试")
    job.status = "pending"
    job.cancel_requested = False
    job.error_code = None
    job.error_message = None
    job.finished_at = None
    db.add(GenerationEvent(job_id=job.id, status="pending", message="任务已重新排队"))
    db.commit()
    db.refresh(job)
    try:
        run_generation_job.delay(job.id)
    except Exception:
        pass
    return _read(db, job)


@router.get("/products/{product_id}/assets", response_model=list[AssetRead])
def list_assets(product_id: int, db: SessionDep, access: Access):
    _product(db, access, product_id)
    return list(
        db.scalars(
            select(MediaAsset)
            .where(MediaAsset.product_id == product_id, MediaAsset.status == "available")
            .order_by(desc(MediaAsset.created_at))
        )
    )


@router.patch("/assets/{asset_id}", response_model=AssetRead)
def update_asset(
    asset_id: int,
    payload: AssetUpdate,
    db: SessionDep,
    access: Annotated[WorkspaceAccess, Depends(require_high_risk_approval)],
):
    asset = db.get(MediaAsset, asset_id)
    if asset is None:
        raise HTTPException(404, "素材不存在")
    if asset.workspace_id != access.workspace.id:
        raise HTTPException(403, "无权访问此素材")
    if payload.review_status is not None:
        asset.review_status = payload.review_status
    if payload.tags is not None:
        asset.tags = payload.tags
    asset.updated_by = access.user.id
    record_audit_event(
        db,
        access=access,
        action="media_asset_review",
        resource_type="media_asset",
        resource_id=str(asset.id),
        details={
            "review_status": payload.review_status,
            "tag_count": len(payload.tags or asset.tags),
        },
    )
    db.commit()
    db.refresh(asset)
    return asset


@router.post("/assets/{asset_id}/archive", response_model=AssetRead)
def archive_asset(
    asset_id: int,
    db: SessionDep,
    access: Annotated[WorkspaceAccess, Depends(require_high_risk_approval)],
):
    asset = db.get(MediaAsset, asset_id)
    if asset is None:
        raise HTTPException(404, "素材不存在")
    if asset.workspace_id != access.workspace.id:
        raise HTTPException(403, "无权访问此素材")
    asset.status = "archived"
    asset.updated_by = access.user.id
    record_audit_event(
        db,
        access=access,
        action="media_asset_archive",
        resource_type="media_asset",
        resource_id=str(asset.id),
    )
    db.commit()
    db.refresh(asset)
    return asset
