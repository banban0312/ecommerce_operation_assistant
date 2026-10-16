from datetime import UTC, datetime
from time import monotonic

from sqlalchemy import select

from app.db.session import get_session_factory
from app.models import (
    AgentApproval,
    AgentStep,
    AgentTask,
    BusinessMetric,
    ContentVersion,
    GenerationEvent,
    GenerationJob,
    MediaAsset,
    Product,
    ProductSku,
    TaskRule,
)
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
        started_monotonic = monotonic()
        result = generate_media(job.media_type, job.id, content.content if content else {})
        rule = db.scalar(select(TaskRule).where(TaskRule.workspace_id == job.workspace_id))
        if rule and monotonic() - started_monotonic > rule.timeout_seconds:
            result = result.__class__(
                False, error_code="timeout", error_message="任务超过配置的超时时间"
            )
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


@celery_app.task(name="agent.run_task")
def run_agent_task(task_id: int) -> dict:
    """逐步执行 Agent；每一步提交 checkpoint，审批节点只暂停不执行外部副作用。"""
    with get_session_factory()() as db:
        task = db.get(AgentTask, task_id)
        if task is None:
            return {"status": "missing"}
        if task.status in {"succeeded", "failed", "rejected", "cancelled"}:
            return {"status": task.status}
        steps = list(
            db.scalars(
                select(AgentStep).where(AgentStep.task_id == task.id).order_by(AgentStep.step_no)
            )
        )
        for step in steps:
            if step.status == "succeeded":
                continue
            if step.tool_name == "approval_gate":
                approval = db.scalar(
                    select(AgentApproval)
                    .where(AgentApproval.step_id == step.id)
                    .order_by(AgentApproval.id.desc())
                )
                if approval is None:
                    approval = AgentApproval(
                        task_id=task.id,
                        step_id=step.id,
                        workspace_id=task.workspace_id,
                        requested_by=task.created_by,
                    )
                    db.add(approval)
                    step.status = "waiting_approval"
                    task.status = "waiting_approval"
                    task.current_step = step.step_no
                    task.paused_at = datetime.now(UTC)
                    db.commit()
                    return {"status": "waiting_approval", "task_id": task.id}
                if approval.status == "pending":
                    task.status = "waiting_approval"
                    step.status = "waiting_approval"
                    db.commit()
                    return {"status": "waiting_approval", "task_id": task.id}
                if approval.status == "rejected":
                    task.status = "rejected"
                    step.status = "skipped"
                    task.finished_at = datetime.now(UTC)
                    db.commit()
                    return {"status": "rejected", "task_id": task.id}
                step.status = "succeeded"
                step.output_summary = {"message": "主管已审批，可继续执行人工动作"}
                step.finished_at = datetime.now(UTC)
                task.checkpoint_version += 1
                task.current_step = step.step_no
                task.status = "running"
                db.commit()
                continue
            task.status = "running"
            task.current_step = step.step_no
            step.status = "running"
            step.started_at = datetime.now(UTC)
            db.commit()
            product = db.get(Product, task.product_id)
            if step.tool_name == "catalog_snapshot":
                skus = list(
                    db.scalars(select(ProductSku).where(ProductSku.product_id == task.product_id))
                )
                output = {
                    "product_name": product.name if product else "",
                    "category": product.category if product else "",
                    "sku_count": len(skus),
                    "stock_total": sum(s.stock for s in skus),
                }
            elif step.tool_name == "content_summary":
                versions = list(
                    db.scalars(
                        select(ContentVersion).where(
                            ContentVersion.product_id == task.product_id,
                            ContentVersion.status == "confirmed",
                        )
                    )
                )
                output = {
                    "confirmed_count": len(versions),
                    "types": sorted({v.content_type for v in versions}),
                }
            elif step.tool_name == "performance_summary":
                metrics = list(
                    db.scalars(
                        select(BusinessMetric).where(BusinessMetric.product_id == task.product_id)
                    )
                )
                output = {
                    "metric_count": len(metrics),
                    "latest_actual_gmv": str(metrics[-1].actual_gmv) if metrics else "0",
                }
            else:
                output = {
                    "recommendation": "基于商品上下文生成运营建议草稿，等待人工审核",
                    "protected_action": step.tool_name == "recommendation_publish",
                }
            step.output_summary = output
            step.checkpoint = {"version": task.checkpoint_version + 1, "step_no": step.step_no}
            step.status = "succeeded"
            step.finished_at = datetime.now(UTC)
            task.context = {**(task.context or {}), step.tool_name: output}
            task.checkpoint_version += 1
            db.commit()
        task.status = "succeeded"
        task.finished_at = datetime.now(UTC)
        db.commit()
        return {
            "status": task.status,
            "task_id": task.id,
            "checkpoint_version": task.checkpoint_version,
        }
