"""增加 M3 服务参数、任务规则和平台授权占位表。"""

import sqlalchemy as sa

from alembic import op

revision = "0005_service_settings"
down_revision = "0004_product_profile"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "service_configs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("workspace_id", sa.Integer(), sa.ForeignKey("workspaces.id"), nullable=False),
        sa.Column("target", sa.String(20), nullable=False),
        sa.Column("provider", sa.String(40), nullable=False),
        sa.Column("model", sa.String(120), nullable=False, server_default=""),
        sa.Column("updated_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint("workspace_id", "target", name="uq_service_config_workspace_target"),
        sa.CheckConstraint("target IN ('text', 'image', 'video')", name="ck_service_config_target"),
    )
    op.create_index("ix_service_configs_workspace_id", "service_configs", ["workspace_id"])
    op.create_table(
        "task_rules",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("workspace_id", sa.Integer(), sa.ForeignKey("workspaces.id"), nullable=False),
        sa.Column("timeout_seconds", sa.Integer(), nullable=False, server_default="300"),
        sa.Column("max_retries", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("max_concurrency", sa.Integer(), nullable=False, server_default="2"),
        sa.Column("image_poll_interval_seconds", sa.Integer(), nullable=False, server_default="5"),
        sa.Column("image_poll_max_attempts", sa.Integer(), nullable=False, server_default="24"),
        sa.Column("video_poll_interval_seconds", sa.Integer(), nullable=False, server_default="10"),
        sa.Column("video_poll_max_attempts", sa.Integer(), nullable=False, server_default="36"),
        sa.Column("updated_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint("workspace_id", name="uq_task_rules_workspace_id"),
    )
    op.create_index("ix_task_rules_workspace_id", "task_rules", ["workspace_id"])
    op.create_table(
        "platform_account_placeholders",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("store_id", sa.Integer(), sa.ForeignKey("stores.id"), nullable=False),
        sa.Column("account_identifier", sa.String(120), nullable=False, server_default=""),
        sa.Column(
            "authorization_status", sa.String(30), nullable=False, server_default="not_connected"
        ),
        sa.Column("updated_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint("store_id", name="uq_platform_placeholder_store_id"),
    )
    op.create_index(
        "ix_platform_account_placeholders_store_id", "platform_account_placeholders", ["store_id"]
    )


def downgrade() -> None:
    op.drop_table("platform_account_placeholders")
    op.drop_table("task_rules")
    op.drop_table("service_configs")
