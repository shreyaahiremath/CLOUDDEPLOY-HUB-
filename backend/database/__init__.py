"""Database layer.

SQLAlchemy always talks to a local SQLite file. When Supabase is configured (SUPABASE_URL +
SUPABASE_SECRET_KEY) that file is only a working copy: it is filled from Supabase at startup and
every committed change is written back through Supabase's HTTPS API. No Postgres connection string
or database password is involved. See backend/services/supabase_store.py.
"""
from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from backend.config import settings

DATABASE_URL = f"sqlite:///{(settings.data_dir / 'clouddeploy.db').as_posix()}"

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})


@event.listens_for(engine, "connect")
def _sqlite_pragmas(dbapi_conn, _record):  # pragma: no cover - driver hook
    cur = dbapi_conn.cursor()
    cur.execute("PRAGMA journal_mode=WAL")
    cur.execute("PRAGMA foreign_keys=ON")
    cur.close()


SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def get_db() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


_sync_installed = False


def init_db() -> None:
    from backend import models  # noqa: F401  (registers tables)
    from backend.services import supabase_store

    global _sync_installed
    Base.metadata.create_all(engine)
    if not _sync_installed:
        supabase_store.install(SessionLocal, Base.metadata)
        _sync_installed = True
    supabase_store.store.configure(settings.supabase_url, settings.supabase_secret_key)
    supabase_store.store.bootstrap(engine, Base.metadata)
