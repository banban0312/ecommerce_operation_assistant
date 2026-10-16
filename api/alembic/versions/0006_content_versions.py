"""增加 M4 诊断、创意和脚本版本表。"""

import sqlalchemy as sa

from alembic import op

revision = "0006_content_versions"
down_revision = "0005_service_settings"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "content_versions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "product_id",
            sa.Integer(),
            sa.ForeignKey("products.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("content_type", sa.String(30), nullable=False),
        sa.Column("slot_key", sa.String(40), nullable=False, server_default="default"),
        sa.Column("version_no", sa.Integer(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("status", sa.String(20), nullable=False, server_default="draft"),
        sa.Column("source", sa.String(20), nullable=False, server_default="model"),
        sa.Column("content", sa.JSON(), nullable=False),
        sa.Column("updated_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint(
            "product_id", "content_type", "slot_key", "version_no", name="uq_content_version_slot"
        ),
        sa.CheckConstraint(
            "content_type IN ('diagnosis', 'image_idea', 'video_script')",
            name="ck_content_version_type",
        ),
        sa.CheckConstraint(
            "status IN ('draft', 'confirmed', 'archived')", name="ck_content_version_status"
        ),
    )
    op.create_index("ix_content_versions_product_id", "content_versions", ["product_id"])
    op.create_index(
        "ix_content_versions_product_type",
        "content_versions",
        ["product_id", "content_type", "slot_key"],
    )


def downgrade() -> None:
    op.drop_table("content_versions")
