"""M7 经营指标、复盘报告与下一轮诊断来源。"""

import sqlalchemy as sa

from alembic import op

revision = "0009_business_reviews"
down_revision = "0008_ad_proposals"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "business_metrics",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("workspace_id", sa.Integer(), sa.ForeignKey("workspaces.id"), nullable=False),
        sa.Column(
            "product_id",
            sa.Integer(),
            sa.ForeignKey("products.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("period_end", sa.Date(), nullable=False),
        sa.Column("source", sa.String(40), nullable=False, server_default="manual"),
        sa.Column("target_gmv", sa.Numeric(14, 2), nullable=False),
        sa.Column("actual_gmv", sa.Numeric(14, 2), nullable=False),
        sa.Column("target_impressions", sa.Integer(), nullable=False),
        sa.Column("actual_impressions", sa.Integer(), nullable=False),
        sa.Column("target_ctr", sa.Numeric(8, 5), nullable=False),
        sa.Column("actual_ctr", sa.Numeric(8, 5), nullable=False),
        sa.Column("target_conversion_rate", sa.Numeric(8, 5), nullable=False),
        sa.Column("actual_conversion_rate", sa.Numeric(8, 5), nullable=False),
        sa.Column("target_roi", sa.Numeric(8, 3), nullable=False),
        sa.Column("actual_roi", sa.Numeric(8, 3), nullable=False),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint(
            "product_id", "period_start", "period_end", "source", name="uq_business_metric_period"
        ),
        sa.CheckConstraint("period_end >= period_start", name="ck_business_metric_period"),
    )
    op.create_index(
        "ix_business_metrics_product_period",
        "business_metrics",
        ["product_id", "period_start", "period_end"],
    )
    op.create_table(
        "review_reports",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("workspace_id", sa.Integer(), sa.ForeignKey("workspaces.id"), nullable=False),
        sa.Column(
            "product_id",
            sa.Integer(),
            sa.ForeignKey("products.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("metric_id", sa.Integer(), sa.ForeignKey("business_metrics.id"), nullable=False),
        sa.Column("content", sa.JSON(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("status", sa.String(20), nullable=False, server_default="draft"),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint("status IN ('draft','published')", name="ck_review_report_status"),
    )
    op.create_index(
        "ix_review_reports_product_created", "review_reports", ["product_id", "created_at"]
    )
    op.add_column(
        "content_versions",
        sa.Column(
            "source_report_id", sa.Integer(), sa.ForeignKey("review_reports.id"), nullable=True
        ),
    )


def downgrade() -> None:
    op.drop_column("content_versions", "source_report_id")
    op.drop_index("ix_review_reports_product_created", table_name="review_reports")
    op.drop_table("review_reports")
    op.drop_index("ix_business_metrics_product_period", table_name="business_metrics")
    op.drop_table("business_metrics")
