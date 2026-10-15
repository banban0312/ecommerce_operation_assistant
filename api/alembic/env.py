from alembic import context
from app.core.config import get_settings
from app.db.base import Base
from app.db.session import get_engine
from app.observability import configure_logging

configure_logging(get_settings().log_level)

if context.is_offline_mode():
    context.configure(
        url=get_settings().database_url.render_as_string(hide_password=False),
        target_metadata=Base.metadata,
        literal_binds=True,
    )
    with context.begin_transaction():
        context.run_migrations()
else:
    with get_engine().connect() as connection:
        context.configure(connection=connection, target_metadata=Base.metadata)
        with context.begin_transaction():
            context.run_migrations()
