"""M8 导入预览批次与确认提交。"""

import sqlalchemy as sa

from alembic import op

revision = "0010_import_batches"
down_revision = "0009_business_reviews"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "import_batches",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("workspace_id", sa.Integer(), sa.ForeignKey("workspaces.id"), nullable=False),
        sa.Column("batch_key", sa.String(80), nullable=False),
        sa.Column("data_type", sa.String(20), nullable=False),
        sa.Column("filename", sa.String(255), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="preview"),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("rows", sa.JSON(), nullable=False),
        sa.Column("valid_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("committed_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("workspace_id", "batch_key", name="uq_import_batch_key"),
    )


def downgrade() -> None:
    op.drop_table("import_batches")
