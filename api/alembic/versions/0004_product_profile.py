"""补充原型中的平台商品编号、成本和商品定位字段。"""

import sqlalchemy as sa

from alembic import op

revision = "0004_product_profile"
down_revision = "0003_product_catalog"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # MySQL 的 DDL 会逐条提交；检查已有列以便迁移失败后安全续跑。
    existing = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("products")}
    if "platform_item_code" not in existing:
        op.add_column(
            "products",
            sa.Column("platform_item_code", sa.String(100), nullable=False, server_default=""),
        )
    if "cost" not in existing:
        op.add_column("products", sa.Column("cost", sa.Numeric(12, 2), nullable=True))
    if "target_audience" not in existing:
        op.add_column(
            "products",
            sa.Column("target_audience", sa.String(500), nullable=False, server_default=""),
        )
    if "selling_points" not in existing:
        # MySQL 不允许 TEXT 默认值；先回填旧行，再收紧为非空。
        op.add_column("products", sa.Column("selling_points", sa.Text(), nullable=True))
        op.execute(sa.text("UPDATE products SET selling_points = '' WHERE selling_points IS NULL"))
        op.alter_column("products", "selling_points", existing_type=sa.Text(), nullable=False)


def downgrade() -> None:
    op.drop_column("products", "selling_points")
    op.drop_column("products", "target_audience")
    op.drop_column("products", "cost")
    op.drop_column("products", "platform_item_code")
