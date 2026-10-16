"""为工作空间服务配置增加地址和加密凭据。"""

import sqlalchemy as sa

from alembic import op

revision = "0013_service_credentials"
down_revision = "0012_competitor_trends"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # MySQL 会对每条 ALTER TABLE 自动提交；支持从部分完成状态安全重试。
    existing = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("service_configs")}
    if "endpoint_url" not in existing:
        op.add_column(
            "service_configs",
            sa.Column("endpoint_url", sa.String(1000), nullable=False, server_default=""),
        )
    if "api_key_encrypted" not in existing:
        op.add_column(
            "service_configs", sa.Column("api_key_encrypted", sa.Text(), nullable=True)
        )


def downgrade() -> None:
    op.drop_column("service_configs", "api_key_encrypted")
    op.drop_column("service_configs", "endpoint_url")
