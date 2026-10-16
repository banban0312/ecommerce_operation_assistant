"""M6 投放实验建议与人工风险审批。"""

import sqlalchemy as sa

from alembic import op

revision = "0008_ad_proposals"
down_revision = "0007_media_jobs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ad_proposals",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("workspace_id", sa.Integer(), sa.ForeignKey("workspaces.id"), nullable=False),
        sa.Column(
            "product_id",
            sa.Integer(),
            sa.ForeignKey("products.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("content", sa.JSON(), nullable=False),
        sa.Column("risk_level", sa.String(20), nullable=False, server_default="normal"),
        sa.Column("status", sa.String(20), nullable=False, server_default="draft"),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("submitted_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint("risk_level IN ('normal','high')", name="ck_ad_proposal_risk"),
        sa.CheckConstraint(
            "status IN ('draft','pending','approved','rejected')", name="ck_ad_proposal_status"
        ),
    )
    op.create_index("ix_ad_proposals_product_created", "ad_proposals", ["product_id", "created_at"])
    op.create_table(
        "ad_proposal_decisions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "proposal_id",
            sa.Integer(),
            sa.ForeignKey("ad_proposals.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("workspace_id", sa.Integer(), sa.ForeignKey("workspaces.id"), nullable=False),
        sa.Column("actor_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("actor_role", sa.String(20), nullable=False),
        sa.Column("result", sa.String(20), nullable=False),
        sa.Column("note", sa.String(1000), nullable=False, server_default=""),
        sa.Column("previous_risk_level", sa.String(20), nullable=False),
        sa.Column("risk_level", sa.String(20), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index(
        "ix_ad_decisions_proposal_created", "ad_proposal_decisions", ["proposal_id", "created_at"]
    )


def downgrade() -> None:
    op.drop_table("ad_proposal_decisions")
    op.drop_index("ix_ad_proposals_product_created", table_name="ad_proposals")
    op.drop_table("ad_proposals")
