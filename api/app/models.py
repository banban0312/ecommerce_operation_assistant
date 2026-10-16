from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """统一的 SQLAlchemy 元数据基类，后续业务模型会在此基础上注册。"""


class UserStatus(StrEnum):
    ACTIVE = "active"
    DISABLED = "disabled"


class WorkspaceStatus(StrEnum):
    ACTIVE = "active"
    DISABLED = "disabled"


class WorkspaceRole(StrEnum):
    OPERATOR = "operator"
    SUPERVISOR = "supervisor"
    ADMIN = "admin"


class MembershipStatus(StrEnum):
    ACTIVE = "active"
    DISABLED = "disabled"


class User(Base):
    """登录身份；用户与具体工作空间的角色由成员关系决定。"""

    __tablename__ = "users"
    __table_args__ = (
        Index("ix_users_status", "status"),
        CheckConstraint("status IN ('active', 'disabled')", name="ck_users_status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True)
    display_name: Mapped[str] = mapped_column(String(120))
    password_hash: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default=UserStatus.ACTIVE.value)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    memberships: Mapped[list["WorkspaceMembership"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


class Workspace(Base):
    """多租户边界；业务记录通过工作空间归属实现隔离。"""

    __tablename__ = "workspaces"
    __table_args__ = (
        CheckConstraint("status IN ('active', 'disabled')", name="ck_workspaces_status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(80), unique=True)
    name: Mapped[str] = mapped_column(String(160))
    status: Mapped[str] = mapped_column(String(20), default=WorkspaceStatus.ACTIVE.value)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    memberships: Mapped[list["WorkspaceMembership"]] = relationship(
        back_populates="workspace", cascade="all, delete-orphan"
    )


class WorkspaceMembership(Base):
    """用户在单个工作空间中的角色和启用状态。"""

    __tablename__ = "workspace_memberships"
    __table_args__ = (
        UniqueConstraint("workspace_id", "user_id", name="uq_workspace_membership_user"),
        Index("ix_membership_workspace_status", "workspace_id", "status"),
        CheckConstraint("role IN ('operator', 'supervisor', 'admin')", name="ck_membership_role"),
        CheckConstraint("status IN ('active', 'disabled')", name="ck_membership_status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    workspace_id: Mapped[int] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    role: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(20), default=MembershipStatus.ACTIVE.value)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    workspace: Mapped[Workspace] = relationship(back_populates="memberships")
    user: Mapped[User] = relationship(back_populates="memberships")


class AuditEvent(Base):
    """关键操作的审计条目，保存操作者、工作空间、动作和发生时间。"""

    __tablename__ = "audit_events"
    __table_args__ = (Index("ix_audit_workspace_created", "workspace_id", "created_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    workspace_id: Mapped[int] = mapped_column(ForeignKey("workspaces.id"), index=True)
    actor_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    action: Mapped[str] = mapped_column(String(100))
    resource_type: Mapped[str] = mapped_column(String(100))
    resource_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    details: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Store(Base):
    """店铺属于工作空间；平台授权在后续配置阶段接入。"""

    __tablename__ = "stores"
    __table_args__ = (Index("ix_stores_workspace_name", "workspace_id", "name"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    workspace_id: Mapped[int] = mapped_column(ForeignKey("workspaces.id"), index=True)
    name: Mapped[str] = mapped_column(String(160))
    platform: Mapped[str] = mapped_column(String(50))
    status: Mapped[str] = mapped_column(String(20), default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class ServiceConfig(Base):
    """按工作空间保存服务参数；API Key 使用应用密钥加密后保存。"""

    __tablename__ = "service_configs"
    __table_args__ = (
        UniqueConstraint("workspace_id", "target", name="uq_service_config_workspace_target"),
        CheckConstraint("target IN ('text', 'image', 'video')", name="ck_service_config_target"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    workspace_id: Mapped[int] = mapped_column(ForeignKey("workspaces.id"), index=True)
    target: Mapped[str] = mapped_column(String(20))
    provider: Mapped[str] = mapped_column(String(40))
    model: Mapped[str] = mapped_column(String(120), default="")
    endpoint_url: Mapped[str] = mapped_column(String(1000), default="")
    api_key_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class TaskRule(Base):
    """任务调度参数的持久化入口，供后续生成任务读取。"""

    __tablename__ = "task_rules"

    id: Mapped[int] = mapped_column(primary_key=True)
    workspace_id: Mapped[int] = mapped_column(ForeignKey("workspaces.id"), unique=True, index=True)
    timeout_seconds: Mapped[int] = mapped_column(Integer, default=300)
    max_retries: Mapped[int] = mapped_column(Integer, default=3)
    max_concurrency: Mapped[int] = mapped_column(Integer, default=2)
    image_poll_interval_seconds: Mapped[int] = mapped_column(Integer, default=5)
    image_poll_max_attempts: Mapped[int] = mapped_column(Integer, default=24)
    video_poll_interval_seconds: Mapped[int] = mapped_column(Integer, default=10)
    video_poll_max_attempts: Mapped[int] = mapped_column(Integer, default=36)
    updated_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class BusinessMetric(Base):
    """按商品和周期保存目标、实际经营指标。"""

    __tablename__ = "business_metrics"
    __table_args__ = (
        UniqueConstraint(
            "product_id", "period_start", "period_end", "source", name="uq_business_metric_period"
        ),
        Index("ix_business_metrics_product_period", "product_id", "period_start", "period_end"),
        CheckConstraint("period_end >= period_start", name="ck_business_metric_period"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    workspace_id: Mapped[int] = mapped_column(ForeignKey("workspaces.id"), index=True)
    product_id: Mapped[int] = mapped_column(
        ForeignKey("products.id", ondelete="CASCADE"), index=True
    )
    period_start: Mapped[date] = mapped_column(Date)
    period_end: Mapped[date] = mapped_column(Date)
    source: Mapped[str] = mapped_column(String(40), default="manual")
    target_gmv: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    actual_gmv: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    target_impressions: Mapped[int] = mapped_column(Integer)
    actual_impressions: Mapped[int] = mapped_column(Integer)
    target_ctr: Mapped[Decimal] = mapped_column(Numeric(8, 5))
    actual_ctr: Mapped[Decimal] = mapped_column(Numeric(8, 5))
    target_conversion_rate: Mapped[Decimal] = mapped_column(Numeric(8, 5))
    actual_conversion_rate: Mapped[Decimal] = mapped_column(Numeric(8, 5))
    target_roi: Mapped[Decimal] = mapped_column(Numeric(8, 3))
    actual_roi: Mapped[Decimal] = mapped_column(Numeric(8, 3))
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class ReviewReport(Base):
    """复盘报告快照；content 区分事实、目标差异和行动建议。"""

    __tablename__ = "review_reports"
    __table_args__ = (
        Index("ix_review_reports_product_created", "product_id", "created_at"),
        CheckConstraint("status IN ('draft', 'published')", name="ck_review_report_status"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    workspace_id: Mapped[int] = mapped_column(ForeignKey("workspaces.id"), index=True)
    product_id: Mapped[int] = mapped_column(
        ForeignKey("products.id", ondelete="CASCADE"), index=True
    )
    metric_id: Mapped[int] = mapped_column(ForeignKey("business_metrics.id"))
    content: Mapped[dict] = mapped_column(JSON)
    revision: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(String(20), default="draft")
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class ImportBatch(Base):
    """两阶段导入批次；预览阶段只保存解析结果，确认后才写业务表。"""

    __tablename__ = "import_batches"
    __table_args__ = (UniqueConstraint("workspace_id", "batch_key", name="uq_import_batch_key"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    workspace_id: Mapped[int] = mapped_column(ForeignKey("workspaces.id"), index=True)
    batch_key: Mapped[str] = mapped_column(String(80))
    data_type: Mapped[str] = mapped_column(String(20))
    filename: Mapped[str] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(20), default="preview")
    version: Mapped[int] = mapped_column(Integer, default=1)
    rows: Mapped[list] = mapped_column(JSON)
    valid_count: Mapped[int] = mapped_column(Integer, default=0)
    error_count: Mapped[int] = mapped_column(Integer, default=0)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    committed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class PlatformAccountPlaceholder(Base):
    """仅记录平台账号标识和授权占位状态，不承载密码、Cookie 或令牌。"""

    __tablename__ = "platform_account_placeholders"

    id: Mapped[int] = mapped_column(primary_key=True)
    store_id: Mapped[int] = mapped_column(ForeignKey("stores.id"), unique=True, index=True)
    account_identifier: Mapped[str] = mapped_column(String(120), default="")
    authorization_status: Mapped[str] = mapped_column(String(30), default="not_connected")
    updated_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class ContentVersion(Base):
    """诊断、主图创意和视频脚本的可编辑版本；确认版本不会被重新生成覆盖。"""

    __tablename__ = "content_versions"
    __table_args__ = (
        Index("ix_content_versions_product_type", "product_id", "content_type", "slot_key"),
        UniqueConstraint(
            "product_id",
            "content_type",
            "slot_key",
            "version_no",
            name="uq_content_version_slot",
        ),
        CheckConstraint(
            "content_type IN ('diagnosis', 'image_idea', 'video_script')",
            name="ck_content_version_type",
        ),
        CheckConstraint(
            "status IN ('draft', 'confirmed', 'archived')",
            name="ck_content_version_status",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    product_id: Mapped[int] = mapped_column(
        ForeignKey("products.id", ondelete="CASCADE"), index=True
    )
    content_type: Mapped[str] = mapped_column(String(30))
    slot_key: Mapped[str] = mapped_column(String(40), default="default")
    version_no: Mapped[int] = mapped_column(Integer)
    revision: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(String(20), default="draft")
    source: Mapped[str] = mapped_column(String(20), default="model")
    content: Mapped[dict] = mapped_column(JSON)
    source_report_id: Mapped[int | None] = mapped_column(
        ForeignKey("review_reports.id"), nullable=True
    )
    updated_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class GenerationJob(Base):
    """媒体生成任务；状态变化和幂等键用于 Worker 重试与恢复。"""

    __tablename__ = "generation_jobs"
    __table_args__ = (
        UniqueConstraint("workspace_id", "idempotency_key", name="uq_generation_job_idempotency"),
        Index("ix_generation_jobs_workspace_created", "workspace_id", "created_at"),
        CheckConstraint("media_type IN ('image', 'video')", name="ck_generation_job_media_type"),
        CheckConstraint(
            "status IN ('pending', 'running', 'succeeded', 'failed', 'timeout', 'cancelled')",
            name="ck_generation_job_status",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    workspace_id: Mapped[int] = mapped_column(ForeignKey("workspaces.id"), index=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), index=True)
    content_version_id: Mapped[int] = mapped_column(ForeignKey("content_versions.id"))
    media_type: Mapped[str] = mapped_column(String(20))
    idempotency_key: Mapped[str] = mapped_column(String(120))
    status: Mapped[str] = mapped_column(String(20), default="pending")
    provider: Mapped[str] = mapped_column(String(40), default="")
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    max_retries: Mapped[int] = mapped_column(Integer, default=3)
    error_code: Mapped[str | None] = mapped_column(String(40), nullable=True)
    error_message: Mapped[str | None] = mapped_column(String(500), nullable=True)
    cancel_requested: Mapped[bool] = mapped_column(Boolean, default=False)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class GenerationEvent(Base):
    """任务时间线；每次状态变化追加事件，不覆盖历史。"""

    __tablename__ = "generation_events"
    __table_args__ = (Index("ix_generation_events_job_created", "job_id", "created_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[int] = mapped_column(
        ForeignKey("generation_jobs.id", ondelete="CASCADE"), index=True
    )
    status: Mapped[str] = mapped_column(String(20))
    message: Mapped[str] = mapped_column(String(500))
    details: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class MediaAsset(Base):
    """生成产物与商品、任务和创意版本关联，支持审核、标签和归档。"""

    __tablename__ = "media_assets"
    __table_args__ = (
        Index("ix_media_assets_product_created", "product_id", "created_at"),
        CheckConstraint("media_type IN ('image', 'video')", name="ck_media_asset_media_type"),
        CheckConstraint("status IN ('available', 'archived')", name="ck_media_asset_status"),
        CheckConstraint(
            "review_status IN ('pending', 'approved', 'rejected')", name="ck_media_asset_review"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    workspace_id: Mapped[int] = mapped_column(ForeignKey("workspaces.id"), index=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), index=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("generation_jobs.id"))
    content_version_id: Mapped[int] = mapped_column(ForeignKey("content_versions.id"))
    media_type: Mapped[str] = mapped_column(String(20))
    storage_path: Mapped[str] = mapped_column(String(500))
    status: Mapped[str] = mapped_column(String(20), default="available")
    review_status: Mapped[str] = mapped_column(String(20), default="pending")
    tags: Mapped[list] = mapped_column(JSON, default=list)
    updated_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class AdProposal(Base):
    """投放实验建议；只保存人工可审核的方案，不调用外部广告平台。"""

    __tablename__ = "ad_proposals"
    __table_args__ = (
        Index("ix_ad_proposals_product_created", "product_id", "created_at"),
        CheckConstraint("risk_level IN ('normal', 'high')", name="ck_ad_proposal_risk"),
        CheckConstraint(
            "status IN ('draft', 'pending', 'approved', 'rejected')", name="ck_ad_proposal_status"
        ),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    workspace_id: Mapped[int] = mapped_column(ForeignKey("workspaces.id"), index=True)
    product_id: Mapped[int] = mapped_column(
        ForeignKey("products.id", ondelete="CASCADE"), index=True
    )
    content: Mapped[dict] = mapped_column(JSON)
    risk_level: Mapped[str] = mapped_column(String(20), default="normal")
    status: Mapped[str] = mapped_column(String(20), default="draft")
    revision: Mapped[int] = mapped_column(Integer, default=1)
    submitted_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class AdProposalDecision(Base):
    """投放建议每次人工处理的不可覆盖记录。"""

    __tablename__ = "ad_proposal_decisions"
    __table_args__ = (Index("ix_ad_decisions_proposal_created", "proposal_id", "created_at"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    proposal_id: Mapped[int] = mapped_column(
        ForeignKey("ad_proposals.id", ondelete="CASCADE"), index=True
    )
    workspace_id: Mapped[int] = mapped_column(ForeignKey("workspaces.id"), index=True)
    actor_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    actor_role: Mapped[str] = mapped_column(String(20))
    result: Mapped[str] = mapped_column(String(20))
    note: Mapped[str] = mapped_column(String(1000), default="")
    previous_risk_level: Mapped[str] = mapped_column(String(20))
    risk_level: Mapped[str] = mapped_column(String(20))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Product(Base):
    """商品档案始终经所属店铺确定工作空间。"""

    __tablename__ = "products"
    __table_args__ = (Index("ix_products_store_name", "store_id", "name"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    store_id: Mapped[int] = mapped_column(ForeignKey("stores.id"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    category: Mapped[str] = mapped_column(String(120), default="")
    description: Mapped[str] = mapped_column(Text, default="")
    platform_item_code: Mapped[str] = mapped_column(String(100), default="")
    cost: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    target_audience: Mapped[str] = mapped_column(String(500), default="")
    selling_points: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(20), default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class ProductSku(Base):
    """价格与当前库存按规格保存，库存变化另写不可覆盖的流水。"""

    __tablename__ = "product_skus"
    __table_args__ = (
        UniqueConstraint("product_id", "sku_code", name="uq_product_sku_code"),
        Index("ix_skus_product_stock", "product_id", "stock"),
        CheckConstraint("stock >= 0", name="ck_skus_stock"),
        CheckConstraint("warning_threshold >= 0", name="ck_skus_warning_threshold"),
        CheckConstraint("price >= 0", name="ck_skus_price"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), index=True)
    sku_code: Mapped[str] = mapped_column(String(100))
    specification: Mapped[str] = mapped_column(String(200))
    price: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    stock: Mapped[int] = mapped_column(Integer, default=0)
    warning_threshold: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(20), default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class InventoryMovement(Base):
    """每次库存调整记录变更量、调整后数量和操作者。"""

    __tablename__ = "inventory_movements"
    __table_args__ = (Index("ix_inventory_product_created", "product_id", "created_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), index=True)
    sku_id: Mapped[int] = mapped_column(ForeignKey("product_skus.id"), index=True)
    actor_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    delta: Mapped[int] = mapped_column(Integer)
    quantity_after: Mapped[int] = mapped_column(Integer)
    reason: Mapped[str] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Competitor(Base):
    """竞品参数绑定商品 ID，避免切换商品时混入其他单品。"""

    __tablename__ = "competitors"
    __table_args__ = (Index("ix_competitors_product_created", "product_id", "created_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    price: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    attributes: Mapped[dict] = mapped_column(JSON, default=dict)
    source_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    source_status: Mapped[str] = mapped_column(String(24), default="manual")
    source_fetched_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    source_snapshot: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class AgentTask(Base):
    """绑定单个商品的 Agent 任务；状态和 checkpoint 用于暂停后恢复。"""

    __tablename__ = "agent_tasks"
    __table_args__ = (
        Index("ix_agent_tasks_workspace_product", "workspace_id", "product_id", "created_at"),
        CheckConstraint(
            "status IN ('queued','running','waiting_approval','paused','succeeded','failed',"
            "'rejected','cancelled')",
            name="ck_agent_task_status",
        ),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    workspace_id: Mapped[int] = mapped_column(ForeignKey("workspaces.id"), index=True)
    product_id: Mapped[int] = mapped_column(
        ForeignKey("products.id", ondelete="CASCADE"), index=True
    )
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    name: Mapped[str] = mapped_column(String(160))
    goal: Mapped[str] = mapped_column(Text, default="")
    requested_tools: Mapped[list] = mapped_column(JSON, default=list)
    context: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(24), default="queued")
    current_step: Mapped[int] = mapped_column(Integer, default=0)
    checkpoint_version: Mapped[int] = mapped_column(Integer, default=0)
    error_message: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    paused_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AgentStep(Base):
    """Agent 每一步的输入、输出和 checkpoint，保证可追溯且可幂等重试。"""

    __tablename__ = "agent_steps"
    __table_args__ = (
        UniqueConstraint("task_id", "step_no", name="uq_agent_step_no"),
        Index("ix_agent_steps_task", "task_id", "step_no"),
        CheckConstraint(
            "status IN ('pending','running','waiting_approval','succeeded','failed','skipped')",
            name="ck_agent_step_status",
        ),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    task_id: Mapped[int] = mapped_column(
        ForeignKey("agent_tasks.id", ondelete="CASCADE"), index=True
    )
    step_no: Mapped[int] = mapped_column(Integer)
    tool_name: Mapped[str] = mapped_column(String(80))
    status: Mapped[str] = mapped_column(String(24), default="pending")
    input_summary: Mapped[dict] = mapped_column(JSON, default=dict)
    output_summary: Mapped[dict] = mapped_column(JSON, default=dict)
    checkpoint: Mapped[dict] = mapped_column(JSON, default=dict)
    error_message: Mapped[str | None] = mapped_column(String(500), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AgentApproval(Base):
    """高风险步骤的审批记录；只有主管或管理员可作出决定。"""

    __tablename__ = "agent_approvals"
    __table_args__ = (
        Index("ix_agent_approvals_task", "task_id", "created_at"),
        CheckConstraint(
            "status IN ('pending','approved','rejected')", name="ck_agent_approval_status"
        ),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    task_id: Mapped[int] = mapped_column(
        ForeignKey("agent_tasks.id", ondelete="CASCADE"), index=True
    )
    step_id: Mapped[int] = mapped_column(
        ForeignKey("agent_steps.id", ondelete="CASCADE"), index=True
    )
    workspace_id: Mapped[int] = mapped_column(ForeignKey("workspaces.id"), index=True)
    risk_level: Mapped[str] = mapped_column(String(20), default="high")
    status: Mapped[str] = mapped_column(String(20), default="pending")
    requested_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    decided_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    decision_note: Mapped[str] = mapped_column(String(1000), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
