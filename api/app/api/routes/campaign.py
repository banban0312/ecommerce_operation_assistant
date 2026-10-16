"""M6 投放实验建议与人工风险审批；系统只记录人工决策，不触发外部投放。"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import desc, select

from app.api.dependencies import SessionDep, get_workspace_access, require_high_risk_approval
from app.models import AdProposal, AdProposalDecision, Product, Store
from app.schemas.campaign import (
    DecisionCreate,
    DecisionRead,
    ProposalCreate,
    ProposalRead,
    ProposalUpdate,
    RiskUpdate,
)
from app.services.audit import record_audit_event
from app.services.service_settings import runtime_service
from app.services.text_provider import request_structured
from app.services.workspaces import WorkspaceAccess

router = APIRouter(prefix="/campaigns", tags=["campaigns"])
Access = Annotated[WorkspaceAccess, Depends(get_workspace_access)]


def _product(db: SessionDep, access: WorkspaceAccess, product_id: int) -> Product:
    product = db.get(Product, product_id)
    store = db.get(Store, product.store_id) if product else None
    if product is None:
        raise HTTPException(404, "商品不存在")
    if store is None or store.workspace_id != access.workspace.id:
        raise HTTPException(403, "无权访问此商品")
    return product


def _proposal(db: SessionDep, access: WorkspaceAccess, proposal_id: int) -> AdProposal:
    proposal = db.get(AdProposal, proposal_id)
    if proposal is None:
        raise HTTPException(404, "投放建议不存在")
    if proposal.workspace_id != access.workspace.id:
        raise HTTPException(403, "无权访问此建议")
    return proposal


def _read(db, proposal):
    decisions = list(
        db.scalars(
            select(AdProposalDecision)
            .where(AdProposalDecision.proposal_id == proposal.id)
            .order_by(AdProposalDecision.created_at)
        )
    )
    return ProposalRead.model_validate(proposal, from_attributes=True).model_copy(
        update={"decisions": [DecisionRead.model_validate(d) for d in decisions]}
    )


@router.post("/products/{product_id}/proposals", response_model=ProposalRead, status_code=201)
def generate_proposal(product_id: int, payload: ProposalCreate, db: SessionDep, access: Access):
    product = _product(db, access, product_id)
    prompt = (
        "为商品生成投放实验建议，只输出 JSON，字段必须包括 audience、bidding_strategy、"
        "asset_mix、ab_test。"
        f"商品名称：{product.name}；品类：{product.category}；"
        f"目标人群：{product.target_audience}；卖点：{product.selling_points}。"
    )
    _, model, endpoint, key = runtime_service(db, access.workspace.id, "text")
    content = request_structured(prompt, model=model, endpoint_url=endpoint, api_key=key)
    required = {"audience", "bidding_strategy", "asset_mix", "ab_test"}
    if not required.issubset(content):
        raise HTTPException(502, "模型投放建议结构不完整，请稍后重试")
    proposal = AdProposal(
        workspace_id=access.workspace.id,
        product_id=product.id,
        content=content,
        risk_level=payload.risk_level,
        submitted_by=access.user.id,
        status="pending",
    )
    db.add(proposal)
    record_audit_event(
        db,
        access=access,
        action="campaign.proposal_create",
        resource_type="ad_proposal",
        resource_id=str(product.id),
    )
    db.commit()
    db.refresh(proposal)
    return _read(db, proposal)


@router.get("/products/{product_id}/proposals", response_model=list[ProposalRead])
def list_proposals(product_id: int, db: SessionDep, access: Access):
    _product(db, access, product_id)
    return [
        _read(db, p)
        for p in db.scalars(
            select(AdProposal)
            .where(AdProposal.product_id == product_id)
            .order_by(desc(AdProposal.created_at))
        )
    ]


@router.patch("/proposals/{proposal_id}", response_model=ProposalRead)
def update_proposal(proposal_id: int, payload: ProposalUpdate, db: SessionDep, access: Access):
    proposal = _proposal(db, access, proposal_id)
    if proposal.revision != payload.revision or proposal.status in {"approved", "rejected"}:
        raise HTTPException(409, "建议版本已变化或已处理")
    proposal.content = payload.content
    proposal.revision += 1
    proposal.status = "pending"
    record_audit_event(
        db,
        access=access,
        action="campaign.proposal_edit",
        resource_type="ad_proposal",
        resource_id=str(proposal.id),
        details={"revision": proposal.revision},
    )
    db.commit()
    db.refresh(proposal)
    return _read(db, proposal)


@router.post("/proposals/{proposal_id}/risk", response_model=ProposalRead)
def update_risk(
    proposal_id: int,
    payload: RiskUpdate,
    db: SessionDep,
    access: Annotated[WorkspaceAccess, Depends(require_high_risk_approval)],
):
    proposal = _proposal(db, access, proposal_id)
    if proposal.revision != payload.revision:
        raise HTTPException(409, "建议版本已变化")
    if proposal.risk_level == payload.risk_level:
        return _read(db, proposal)
    previous = proposal.risk_level
    proposal.risk_level = payload.risk_level
    proposal.revision += 1
    record_audit_event(
        db,
        access=access,
        action="campaign.risk_change",
        resource_type="ad_proposal",
        resource_id=str(proposal.id),
        details={"from": previous, "to": payload.risk_level},
    )
    db.commit()
    db.refresh(proposal)
    return _read(db, proposal)


@router.post("/proposals/{proposal_id}/decisions", response_model=DecisionRead, status_code=201)
def decide(proposal_id: int, payload: DecisionCreate, db: SessionDep, access: Access):
    proposal = _proposal(db, access, proposal_id)
    if proposal.revision != payload.revision:
        raise HTTPException(409, "建议版本已变化")
    if proposal.risk_level == "high" and access.role not in {"supervisor", "admin"}:
        raise HTTPException(403, "高风险建议仅主管或管理员可处理")
    if proposal.status in {"approved", "rejected"}:
        raise HTTPException(409, "建议已处理")
    decision = AdProposalDecision(
        proposal_id=proposal.id,
        workspace_id=access.workspace.id,
        actor_user_id=access.user.id,
        actor_role=access.role,
        result=payload.result,
        note=payload.note,
        previous_risk_level=proposal.risk_level,
        risk_level=proposal.risk_level,
    )
    proposal.status = payload.result
    proposal.revision += 1
    db.add(decision)
    record_audit_event(
        db,
        access=access,
        action="campaign.decision",
        resource_type="ad_proposal",
        resource_id=str(proposal.id),
        details={"result": payload.result, "risk_level": proposal.risk_level},
    )
    db.commit()
    db.refresh(decision)
    return decision
