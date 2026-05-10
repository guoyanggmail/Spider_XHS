from __future__ import annotations

import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Generator

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker


class Base(DeclarativeBase):
    pass


ROOT_DIR = Path(__file__).resolve().parents[1]
DEFAULT_SQLITE_PATH = ROOT_DIR / "datas" / "app.db"

_engine = None
_session_factory: sessionmaker[Session] | None = None
_database_url = ""


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def build_database_url() -> str:
    explicit = os.getenv("DATABASE_URL", "").strip()
    if explicit:
        return explicit

    postgres_host = os.getenv("POSTGRES_HOST", "").strip()
    if postgres_host:
        postgres_port = os.getenv("POSTGRES_PORT", "5432").strip() or "5432"
        postgres_db = os.getenv("POSTGRES_DB", "spider_xhs").strip() or "spider_xhs"
        postgres_user = os.getenv("POSTGRES_USER", "postgres").strip() or "postgres"
        postgres_password = os.getenv("POSTGRES_PASSWORD", "postgres").strip() or "postgres"
        return f"postgresql+psycopg://{postgres_user}:{postgres_password}@{postgres_host}:{postgres_port}/{postgres_db}"

    DEFAULT_SQLITE_PATH.parent.mkdir(parents=True, exist_ok=True)
    return f"sqlite:///{DEFAULT_SQLITE_PATH}"


def configure_database(url: str | None = None):
    global _engine, _session_factory, _database_url

    database_url = url or build_database_url()
    if _engine is not None:
        _engine.dispose()

    kwargs = {"future": True}
    if database_url.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False}

    _engine = create_engine(database_url, **kwargs)
    _session_factory = sessionmaker(bind=_engine, autoflush=False, autocommit=False, expire_on_commit=False)
    _database_url = database_url
    return _engine


def get_engine():
    global _engine
    if _engine is None:
        configure_database()
    return _engine


def get_database_url() -> str:
    if not _database_url:
        configure_database()
    return _database_url


def get_session_factory() -> sessionmaker[Session]:
    global _session_factory
    if _session_factory is None:
        configure_database()
    assert _session_factory is not None
    return _session_factory


def get_db() -> Generator[Session, None, None]:
    session = get_session_factory()()
    try:
        yield session
    finally:
        session.close()


def init_db(drop_existing: bool = False, retries: int = 10, retry_delay: float = 1.5) -> None:
    import server.models  # noqa: F401

    engine = get_engine()
    for attempt in range(retries + 1):
        try:
            if drop_existing:
                Base.metadata.drop_all(bind=engine)
            Base.metadata.create_all(bind=engine)
            ensure_runtime_schema(engine)
            return
        except OperationalError:
            if attempt >= retries:
                raise
            time.sleep(retry_delay)


def ensure_runtime_schema(engine) -> None:
    inspector = inspect(engine)
    if "accounts" not in inspector.get_table_names():
        return
    columns = {column["name"] for column in inspector.get_columns("accounts")}
    if "user_uid" not in columns:
        ddl = "ALTER TABLE accounts ADD COLUMN user_uid VARCHAR(100) NOT NULL DEFAULT ''"
        with engine.begin() as connection:
            connection.execute(text(ddl))


configure_database()
