"""M7 经营数据、复盘报告和下一轮诊断入口。"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import desc, select
from sqlalchemy.exc import IntegrityError

from app.api.dependencies import SessionDep, get_workspace_access
from app.models import (
    AdProposal,
    BusinessMetric,
    ContentVersion,
    MediaAsset,
    Product,
    ReviewReport,
    Store,
)
from app.schemas.review import MetricCreate, MetricRead, ReportRead, ReportUpdate
from app.services.audit import record_audit_event
from app.services.workspaces import WorkspaceAccess

router = APIRouter(prefix="/review", tags=["review"])
Access = Annotated[WorkspaceAccess, Depends(get_workspace_access)]


def _product(db: SessionDep, access: WorkspaceAccess, product_id: int) -> Product:
    product = db.get(Product, product_id)
    store = db.get(Store, product.store_id) if product else None
    if product is None:
        raise HTTPException(404, "商品不存在")
    if store is None or store.workspace_id != access.workspace.id:
        raise HTTPException(403, "无权访问此商品")
    return product


def _report(db, access, report_id):
    report = db.get(ReviewReport, report_id)
    if report is None:
        raise HTTPException(404, "复盘报告不存在")
    if report.workspace_id != access.workspace.id:
        raise HTTPException(403, "无权访问此报告")
    return report


@router.post("/products/{product_id}/metrics", response_model=MetricRead, status_code=201)
def create_metric(product_id: int, payload: MetricCreate, db: SessionDep, access: Access):
    _product(db, access, product_id)
    metric = BusinessMetric(
        workspace_id=access.workspace.id,
        product_id=product_id,
        created_by=access.user.id,
        **payload.model_dump(),
    )
    db.add(metric)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, "相同商品、周期和来源的数据已存在") from exc
    db.refresh(metric)
    record_audit_event(
        db,
        access=access,
        action="review.metric_create",
        resource_type="business_metric",
        resource_id=str(metric.id),
    )
    db.commit()
    return metric


@router.get("/products/{product_id}/metrics", response_model=list[MetricRead])
def list_metrics(product_id: int, db: SessionDep, access: Access):
    _product(db, access, product_id)
    return list(
        db.scalars(
            select(BusinessMetric)
            .where(BusinessMetric.product_id == product_id)
            .order_by(desc(BusinessMetric.period_start))
        )
    )


@router.post("/products/{product_id}/reports/generate", response_model=ReportRead, status_code=201)
def generate_report(product_id: int, metric_id: int, db: SessionDep, access: Access):
    product = _product(db, access, product_id)
    metric = db.get(BusinessMetric, metric_id)
    if metric is None or metric.product_id != product_id:
        raise HTTPException(404, "经营数据不存在")
    diagnosis = list(
        db.scalars(
            select(ContentVersion)
            .where(
                ContentVersion.product_id == product_id,
                ContentVersion.content_type == "diagnosis",
                ContentVersion.status == "confirmed",
            )
            .order_by(desc(ContentVersion.version_no))
        )
    )
    assets = list(
        db.scalars(
            select(MediaAsset).where(
                MediaAsset.product_id == product_id,
                MediaAsset.review_status == "approved",
                MediaAsset.status == "available",
            )
        )
    )
    proposals = list(
        db.scalars(
            select(AdProposal).where(
                AdProposal.product_id == product_id, AdProposal.status == "approved"
            )
        )
    )
    content = {
        "facts": {
            "product": {"name": product.name, "category": product.category},
            "metric": MetricRead.model_validate(metric).model_dump(mode="json"),
        },
        "diagnosis": [row.content for row in diagnosis[:1]],
        "approved_assets": [{"id": a.id, "type": a.media_type} for a in assets],
        "approved_campaigns": [{"id": p.id, "content": p.content} for p in proposals],
        "comparison": {
            "gmv_delta": str(metric.actual_gmv - metric.target_gmv),
            "ctr_delta": str(metric.actual_ctr - metric.target_ctr),
            "conversion_rate_delta": str(
                metric.actual_conversion_rate - metric.target_conversion_rate
            ),
            "roi_delta": str(metric.actual_roi - metric.target_roi),
        },
        "action_items": ["根据实际指标差异优化素材卖点", "复核投放人群与 A/B 实验分组"],
    }
    report = ReviewReport(
        workspace_id=access.workspace.id,
        product_id=product_id,
        metric_id=metric.id,
        content=content,
        created_by=access.user.id,
        status="draft",
    )
    db.add(report)
    db.flush()
    record_audit_event(
        db,
        access=access,
        action="review.report_generate",
        resource_type="review_report",
        resource_id=str(report.id),
    )
    db.commit()
    db.refresh(report)
    return report


@router.get("/products/{product_id}/reports", response_model=list[ReportRead])
def list_reports(product_id: int, db: SessionDep, access: Access):
    _product(db, access, product_id)
    return list(
        db.scalars(
            select(ReviewReport)
            .where(ReviewReport.product_id == product_id)
            .order_by(desc(ReviewReport.created_at))
        )
    )


@router.patch("/reports/{report_id}", response_model=ReportRead)
def update_report(report_id: int, payload: ReportUpdate, db: SessionDep, access: Access):
    report = _report(db, access, report_id)
    if report.revision != payload.revision:
        raise HTTPException(409, "报告版本已变化，请刷新后重试")
    report.content = payload.content
    report.revision += 1
    record_audit_event(
        db,
        access=access,
        action="review.report_edit",
        resource_type="review_report",
        resource_id=str(report.id),
        details={"revision": report.revision},
    )
    db.commit()
    db.refresh(report)
    return report


@router.post(
    "/reports/{report_id}/actions/{action_index}/diagnosis", response_model=dict, status_code=201
)
def start_diagnosis(report_id: int, action_index: int, db: SessionDep, access: Access):
    report = _report(db, access, report_id)
    actions = report.content.get("action_items", [])
    if action_index < 0 or action_index >= len(actions):
        raise HTTPException(422, "行动项不存在")
    last = db.scalar(
        select(ContentVersion)
        .where(
            ContentVersion.product_id == report.product_id,
            ContentVersion.content_type == "diagnosis",
        )
        .order_by(desc(ContentVersion.version_no))
    )
    row = ContentVersion(
        product_id=report.product_id,
        content_type="diagnosis",
        slot_key=f"review-{report.id}-{action_index}",
        version_no=(last.version_no + 1 if last else 1),
        source="human",
        source_report_id=report.id,
        content={"action": actions[action_index], "from_report_id": report.id},
        updated_by=access.user.id,
    )
    db.add(row)
    record_audit_event(
        db,
        access=access,
        action="review.next_diagnosis",
        resource_type="content_version",
        resource_id=str(report.id),
    )
    db.commit()
    db.refresh(row)
    return {"content_version_id": row.id, "source_report_id": report.id}
