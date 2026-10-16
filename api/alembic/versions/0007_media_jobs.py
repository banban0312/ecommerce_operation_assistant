"""M5 异步媒体生成任务、事件时间线和素材库。"""

import sqlalchemy as sa

from alembic import op

revision = "0007_media_jobs"
down_revision = "0006_content_versions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "generation_jobs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("workspace_id", sa.Integer(), sa.ForeignKey("workspaces.id"), nullable=False),
        sa.Column("product_id", sa.Integer(), sa.ForeignKey("products.id"), nullable=False),
        sa.Column(
            "content_version_id", sa.Integer(), sa.ForeignKey("content_versions.id"), nullable=False
        ),
        sa.Column("media_type", sa.String(20), nullable=False),
        sa.Column("idempotency_key", sa.String(120), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("provider", sa.String(40), nullable=False, server_default=""),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_retries", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("error_code", sa.String(40)),
        sa.Column("error_message", sa.String(500)),
        sa.Column("cancel_requested", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("heartbeat_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint(
            "workspace_id", "idempotency_key", name="uq_generation_job_idempotency"
        ),
        sa.CheckConstraint("media_type IN ('image', 'video')", name="ck_generation_job_media_type"),
        sa.CheckConstraint(
            "status IN ('pending','running','succeeded','failed','timeout','cancelled')",
            name="ck_generation_job_status",
        ),
    )
    op.create_index(
        "ix_generation_jobs_workspace_created", "generation_jobs", ["workspace_id", "created_at"]
    )
    op.create_table(
        "generation_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "job_id",
            sa.Integer(),
            sa.ForeignKey("generation_jobs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("message", sa.String(500), nullable=False),
        sa.Column("details", sa.JSON()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index(
        "ix_generation_events_job_created", "generation_events", ["job_id", "created_at"]
    )
    op.create_table(
        "media_assets",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("workspace_id", sa.Integer(), sa.ForeignKey("workspaces.id"), nullable=False),
        sa.Column("product_id", sa.Integer(), sa.ForeignKey("products.id"), nullable=False),
        sa.Column("job_id", sa.Integer(), sa.ForeignKey("generation_jobs.id"), nullable=False),
        sa.Column(
            "content_version_id", sa.Integer(), sa.ForeignKey("content_versions.id"), nullable=False
        ),
        sa.Column("media_type", sa.String(20), nullable=False),
        sa.Column("storage_path", sa.String(500), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="available"),
        sa.Column("review_status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("tags", sa.JSON(), nullable=False),
        sa.Column("updated_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint("media_type IN ('image','video')", name="ck_media_asset_media_type"),
        sa.CheckConstraint("status IN ('available','archived')", name="ck_media_asset_status"),
        sa.CheckConstraint(
            "review_status IN ('pending','approved','rejected')", name="ck_media_asset_review"
        ),
    )
    op.create_index("ix_media_assets_product_created", "media_assets", ["product_id", "created_at"])


def downgrade() -> None:
    op.drop_table("media_assets")
    op.drop_table("generation_events")
    op.drop_index("ix_generation_jobs_workspace_created", table_name="generation_jobs")
    op.drop_table("generation_jobs")
