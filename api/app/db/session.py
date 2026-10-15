from collections.abc import Generator
from functools import lru_cache

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings


@lru_cache
def get_engine() -> Engine:
    # Keep one bounded connection pool per process; pre-ping drops stale connections after idle periods.
    return create_engine(
        get_settings().database_url,
        pool_pre_ping=True,
        pool_recycle=3600,
        pool_timeout=2,
        hide_parameters=True,
        connect_args={"connect_timeout": 2, "read_timeout": 2, "write_timeout": 2},
    )


@lru_cache
def get_session_factory() -> sessionmaker[Session]:
    # Disable implicit commits and flushes so callers control transaction boundaries explicitly.
    return sessionmaker(bind=get_engine(), autocommit=False, autoflush=False)


def get_db() -> Generator[Session, None, None]:
    # The context manager closes the request session and rolls back any uncommitted transaction.
    with get_session_factory()() as session:
        yield session
