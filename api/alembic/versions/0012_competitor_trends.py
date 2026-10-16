"""M11 竞品来源解析状态和经营趋势查询所需的来源快照字段。"""

import sqlalchemy as sa

from alembic import op

revision = "0012_competitor_trends"
down_revision = "0011_agent_tasks"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "competitors",
        sa.Column("source_status", sa.String(24), nullable=False, server_default="manual"),
    )
    op.add_column(
        "competitors", sa.Column("source_fetched_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        "competitors", sa.Column("source_snapshot", sa.JSON(), nullable=False, server_default="{}")
    )


def downgrade() -> None:
    op.drop_column("competitors", "source_snapshot")
    op.drop_column("competitors", "source_fetched_at")
    op.drop_column("competitors", "source_status")
