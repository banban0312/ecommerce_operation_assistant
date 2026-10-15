from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.db import session as database


def test_request_session_closes_and_rolls_back_uncommitted_work(monkeypatch):
    engine = create_engine("sqlite+pysqlite:///:memory:")
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE probe (id INTEGER PRIMARY KEY)"))
    factory = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    monkeypatch.setattr(database, "get_session_factory", lambda: factory)
    request_session = database.get_db()
    db = next(request_session)
    db.execute(text("INSERT INTO probe (id) VALUES (1)"))
    request_session.close()
    with engine.connect() as connection:
        assert connection.scalar(text("SELECT COUNT(*) FROM probe")) == 0
    engine.dispose()
