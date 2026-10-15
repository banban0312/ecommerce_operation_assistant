from collections.abc import Generator
from functools import lru_cache

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings


@lru_cache
def get_engine() -> Engine:
    # 每个进程只创建一个连接池；预检查可发现空闲期间已失效的数据库连接。
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
    # 禁止隐式提交和刷新，由调用方明确控制事务何时写入和提交。
    return sessionmaker(bind=get_engine(), autocommit=False, autoflush=False)


def get_db() -> Generator[Session, None, None]:
    # 请求结束时关闭会话；未提交的事务会随会话关闭而回滚。
    with get_session_factory()() as session:
        yield session
