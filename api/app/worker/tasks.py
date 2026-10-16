from datetime import UTC, datetime

from sqlalchemy import select

from app.db.session import get_session_factory
from app.models import ContentVersion, GenerationEvent, GenerationJob, MediaAsset
from app.services.media_provider import generate_media
from app.worker.celery_app import celery_app


@celery_app.task(name="system.ping")
def ping() -> dict:
    """基础设施探针：仅验证 Worker 可执行任务，不调用模型或生成业务素材。"""
    return {"service": "worker", "status": "ok"}


@celery_app.task(name="media.run_generation_job")
def run_generation_job(job_id: int) -> dict:
    """执行一次生成尝试；状态和产物写入同一数据库，重复投递不会重复产出。"""
    with get_session_factory()() as db:
        job = db.get(GenerationJob, job_id)
        if job is None:
            return {"status": "missing"}
        if job.status in {"succeeded", "cancelled"}:
            return {"status": job.status}
        if job.cancel_requested:
            job.status = "cancelled"
            job.finished_at = datetime.now(UTC)
            db.add(GenerationEvent(job_id=job.id, status="cancelled", message="任务已取消"))
            db.commit()
            return {"status": "cancelled"}
        job.status = "running"
        job.attempts += 1
        job.started_at = job.started_at or datetime.now(UTC)
        job.heartbeat_at = datetime.now(UTC)
        db.add(GenerationEvent(job_id=job.id, status="running", message="Worker 开始执行"))
        db.commit()
        content = db.get(ContentVersion, job.content_version_id)
        result = generate_media(job.media_type, job.id, content.content if content else {})
        if result.success and not job.cancel_requested:
            existing = db.scalar(select(MediaAsset).where(MediaAsset.job_id == job.id))
            if existing is None:
                db.add(
                    MediaAsset(
                        workspace_id=job.workspace_id,
                        product_id=job.product_id,
                        job_id=job.id,
                        content_version_id=job.content_version_id,
                        media_type=job.media_type,
                        storage_path=result.storage_path or "",
                        tags=[],
                        updated_by=job.created_by,
                    )
                )
            job.status = "succeeded"
            job.finished_at = datetime.now(UTC)
            job.error_code = None
            job.error_message = None
            db.add(GenerationEvent(job_id=job.id, status="succeeded", message="素材生成完成"))
        else:
            job.status = "cancelled" if job.cancel_requested else "failed"
            job.error_code = result.error_code
            job.error_message = result.error_message
            job.finished_at = datetime.now(UTC)
            db.add(
                GenerationEvent(
                    job_id=job.id,
                    status=job.status,
                    message=result.error_message or "生成失败",
                    details={"error_code": result.error_code},
                )
            )
        db.commit()
        return {"status": job.status, "job_id": job.id}
