from datetime import UTC, datetime

from sqlalchemy import JSON, create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import get_settings


class Base(DeclarativeBase):
    type_annotation_map = {dict: JSON, list: JSON}


def utcnow() -> datetime:
    """Naive UTC: SQLite keeps no time zone, every stored datetime is UTC."""
    return datetime.now(UTC).replace(tzinfo=None)


def configure_sqlite(engine):
    """Foreign keys, WAL, and transactions that SQLAlchemy controls itself: pysqlite's own
    BEGIN handling breaks SAVEPOINT, which every assistant action runs in."""

    @event.listens_for(engine, "connect")
    def connect(connection, _):
        connection.isolation_level = None
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA synchronous=NORMAL")
        connection.execute("PRAGMA busy_timeout=30000")

    @event.listens_for(engine, "begin")
    def begin(connection):
        connection.exec_driver_sql("BEGIN")


engine = create_engine(get_settings().database_url, connect_args={"check_same_thread": False})
configure_sqlite(engine)
SessionLocal = sessionmaker(engine, expire_on_commit=False)


def get_db():
    with SessionLocal() as session:
        yield session
