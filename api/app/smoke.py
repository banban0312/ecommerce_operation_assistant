from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory

from app.db.session import get_engine
from app.worker.tasks import ping


def main() -> None:
    # 同时验证数据库迁移版本，以及消息队列、Worker 和结果存储的完整往返链路。
    expected = ScriptDirectory.from_config(Config("alembic.ini")).get_current_head()
    with get_engine().connect() as connection:
        current = MigrationContext.configure(connection).get_current_revision()
    if current != expected:
        raise RuntimeError("Database migration is not at the expected head")
    print("Database migration is at head")
    task = ping.delay()
    result = task.get(timeout=20)
    if result != {"service": "worker", "status": "ok"}:
        raise RuntimeError("Unexpected worker probe result")
    task.forget()
    print("Worker probe passed: API -> Redis -> Worker -> result backend")


if __name__ == "__main__":
    main()
