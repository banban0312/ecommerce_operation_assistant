"""M10 单品 Agent：限定工具、商品边界和可审计人工审批。"""

import logging
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import desc, select

from app.api.dependencies import SessionDep, get_workspace_access, require_high_risk_approval
from app.models import AgentApproval, AgentStep, AgentTask, Product, Store
from app.schemas.agent import (
    ApprovalDecision,
    ApprovalRead,
    StepRead,
    TaskCreate,
    TaskRead,
    ToolRead,
)
from app.services.audit import record_audit_event
from app.services.workspaces import WorkspaceAccess
from app.worker.tasks import run_agent_task

router = APIRouter(prefix="/agent", tags=["agent"])
logger = logging.getLogger(__name__)
Access = Annotated[WorkspaceAccess, Depends(get_workspace_access)]
AGENT_TOOLS = {
    "catalog_snapshot": ("商品档案快照", "读取商品基础信息和库存概况", False),
    "content_summary": ("内容摘要", "读取已确认的内容版本摘要", False),
    "performance_summary": ("经营数据摘要", "读取商品经营指标摘要", False),
    "recommendation_draft": ("运营建议草稿", "生成仅供人工审核的运营建议", False),
    "recommendation_publish": ("发布运营建议", "受保护的人工审批节点，不执行外部投放", True),
}


def _product(db, access, product_id):
    product = db.get(Product, product_id)
    store = db.get(Store, product.store_id) if product else None
    if product is None:
        raise HTTPException(404, "商品不存在")
    if store is None or store.workspace_id != access.workspace.id:
        raise HTTPException(403, "无权访问此商品")
    return product


def _task(db, access, task_id):
    task = db.get(AgentTask, task_id)
    if task is None:
        raise HTTPException(404, "Agent 任务不存在")
    if task.workspace_id != access.workspace.id:
        raise HTTPException(403, "无权访问此任务")
    return task


def _read(db, task):
    return TaskRead.model_validate(task, from_attributes=True).model_copy(
        update={
            "steps": [
                StepRead.model_validate(s, from_attributes=True)
                for s in db.scalars(
                    select(AgentStep)
                    .where(AgentStep.task_id == task.id)
                    .order_by(AgentStep.step_no)
                )
            ],
            "approvals": [
                ApprovalRead.model_validate(a, from_attributes=True)
                for a in db.scalars(
                    select(AgentApproval)
                    .where(AgentApproval.task_id == task.id)
                    .order_by(AgentApproval.created_at)
                )
            ],
        }
    )


@router.get("/tools", response_model=list[ToolRead])
def tools(access: Access):
    return [
        ToolRead(name=k, label=v[0], description=v[1], protected=v[2])
        for k, v in AGENT_TOOLS.items()
    ]


@router.post("/products/{product_id}/tasks", response_model=TaskRead, status_code=201)
def create_task(product_id: int, payload: TaskCreate, db: SessionDep, access: Access):
    product = _product(db, access, product_id)
    requested = payload.requested_tools or [
        "catalog_snapshot",
        "content_summary",
        "performance_summary",
        "recommendation_draft",
    ]
    unknown = sorted(set(requested) - AGENT_TOOLS.keys())
    if unknown:
        raise HTTPException(422, f"存在未授权工具：{', '.join(unknown)}")
    task = AgentTask(
        workspace_id=access.workspace.id,
        product_id=product.id,
        created_by=access.user.id,
        name=payload.name,
        goal=payload.goal,
        requested_tools=requested,
        context={"product_name": product.name},
        status="queued",
    )
    db.add(task)
    db.flush()
    step_no = 1
    has_gate = False
    for name in requested:
        if AGENT_TOOLS[name][2] and not has_gate:
            db.add(
                AgentStep(
                    task_id=task.id,
                    step_no=step_no,
                    tool_name="approval_gate",
                    input_summary={"risk": "high"},
                    output_summary={},
                    checkpoint={},
                )
            )
            step_no += 1
            has_gate = True
        db.add(
            AgentStep(
                task_id=task.id,
                step_no=step_no,
                tool_name=name,
                input_summary={"product_id": product.id},
                output_summary={},
                checkpoint={},
            )
        )
        step_no += 1
    if payload.require_approval and not has_gate:
        db.add(
            AgentStep(
                task_id=task.id,
                step_no=step_no,
                tool_name="approval_gate",
                input_summary={"risk": "high"},
                output_summary={},
                checkpoint={},
            )
        )
    record_audit_event(
        db,
        access=access,
        action="agent.task.create",
        resource_type="agent_task",
        resource_id=str(task.id),
        details={"tools": requested},
    )
    db.commit()
    db.refresh(task)
    try:
        run_agent_task.delay(task.id)
    except Exception:
        logger.exception("Agent task dispatch failed", extra={"agent_task_id": task.id})
        task.status = "failed"
        task.error_message = "任务队列不可用，请检查 Redis 和 Worker 后重新创建任务。"
        task.finished_at = datetime.now(UTC)
        first_step = db.scalar(
            select(AgentStep)
            .where(AgentStep.task_id == task.id, AgentStep.status == "pending")
            .order_by(AgentStep.step_no)
        )
        if first_step:
            first_step.status = "failed"
            first_step.error_message = task.error_message
            first_step.finished_at = datetime.now(UTC)
        db.commit()
        db.refresh(task)
    return _read(db, task)


@router.get("/products/{product_id}/tasks", response_model=list[TaskRead])
def list_tasks(product_id: int, db: SessionDep, access: Access):
    _product(db, access, product_id)
    return [
        _read(db, t)
        for t in db.scalars(
            select(AgentTask)
            .where(
                AgentTask.workspace_id == access.workspace.id, AgentTask.product_id == product_id
            )
            .order_by(desc(AgentTask.created_at))
        )
    ]


@router.get("/tasks/{task_id}", response_model=TaskRead)
def get_task(task_id: int, db: SessionDep, access: Access):
    return _read(db, _task(db, access, task_id))


@router.post("/tasks/{task_id}/approvals/{approval_id}", response_model=TaskRead)
def decide(
    task_id: int,
    approval_id: int,
    payload: ApprovalDecision,
    db: SessionDep,
    access: Annotated[WorkspaceAccess, Depends(require_high_risk_approval)],
):
    task = _task(db, access, task_id)
    approval = db.get(AgentApproval, approval_id)
    if approval is None or approval.task_id != task.id:
        raise HTTPException(404, "审批请求不存在")
    if approval.status != "pending":
        raise HTTPException(409, "审批请求已处理")
    approval.status = payload.result
    approval.decided_by = access.user.id
    approval.decision_note = payload.note
    approval.decided_at = datetime.now(UTC)
    step = db.get(AgentStep, approval.step_id)
    if payload.result == "approved":
        task.status = "queued"
        step.status = "pending"
    else:
        task.status = "rejected"
        step.status = "skipped"
        task.finished_at = datetime.now(UTC)
    record_audit_event(
        db,
        access=access,
        action="agent.approval.decision",
        resource_type="agent_task",
        resource_id=str(task.id),
        details={"approval_id": approval.id, "result": payload.result},
    )
    db.commit()
    db.refresh(task)
    if payload.result == "approved":
        try:
            run_agent_task.delay(task.id)
        except Exception:
            logger.exception(
                "Approved Agent task dispatch failed", extra={"agent_task_id": task.id}
            )
            task.status = "failed"
            task.error_message = "任务队列不可用，请检查 Redis 和 Worker 后从有效 checkpoint 恢复。"
            task.finished_at = datetime.now(UTC)
            db.commit()
            db.refresh(task)
    return _read(db, task)


@router.post("/tasks/{task_id}/cancel", response_model=TaskRead)
def cancel(task_id: int, db: SessionDep, access: Access):
    task = _task(db, access, task_id)
    if task.status in {"succeeded", "failed", "rejected", "cancelled"}:
        raise HTTPException(409, "任务已结束")
    task.status = "cancelled"
    task.finished_at = datetime.now(UTC)
    record_audit_event(
        db,
        access=access,
        action="agent.task.cancel",
        resource_type="agent_task",
        resource_id=str(task.id),
    )
    db.commit()
    db.refresh(task)
    return _read(db, task)
