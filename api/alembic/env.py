from alembic import context
from app.core.config import get_settings
from app.db.base import Base
from app.db.session import get_engine
from app.observability import configure_logging

# 迁移脚本复用应用的配置、模型元数据和日志格式。
configure_logging(get_settings().log_level)

# 离线模式只生成 SQL，不建立数据库连接。
if context.is_offline_mode():
    context.configure(
        url=get_settings().database_url.render_as_string(hide_password=False),
        target_metadata=Base.metadata,
        literal_binds=True,
    )
    with context.begin_transaction():
        context.run_migrations()
else:
    # 在线模式使用应用的连接池执行迁移。
    with get_engine().connect() as connection:
        context.configure(connection=connection, target_metadata=Base.metadata)
        with context.begin_transaction():
            context.run_migrations()
