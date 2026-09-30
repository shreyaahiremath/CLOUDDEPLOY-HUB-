"""Database engine. Uses Supabase Postgres when DATABASE_URL is set, SQLite locally otherwise."""
from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from backend.config import settings


def normalize_url(url: str) -> str:
    """Accept the connection string exactly as Supabase shows it and pick the psycopg 3 driver."""
    placeholders = ("PUT-", "[YOUR-PASSWORD]", "<db-password>", "<region>")
    if any(p in url for p in placeholders):
        raise RuntimeError(
            "DATABASE_URL still contains a placeholder. Set it to the Supabase Transaction pooler URI "
            "(Supabase > Connect > Transaction pooler, port 6543) with your database password filled in."
        )
    for prefix in ("postgres://", "postgresql://"):
        if url.startswith(prefix):
            url = "postgresql+psycopg://" + url[len(prefix):]
    if url.startswith("postgresql+psycopg://") and "supabase" in url and "sslmode=" not in url:
        url += ("&" if "?" in url else "?") + "sslmode=require"
    return url


DATABASE_URL = normalize_url(settings.database_url) if settings.database_url else (
    f"sqlite:///{(settings.data_dir / 'clouddeploy.db').as_posix()}"
)
IS_SQLITE = DATABASE_URL.startswith("sqlite")

if IS_SQLITE:
    engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})

    @event.listens_for(engine, "connect")
    def _sqlite_pragmas(dbapi_conn, _record):  # pragma: no cover - driver hook
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA journal_mode=WAL")
        cur.execute("PRAGMA foreign_keys=ON")
        cur.close()
else:
    # prepare_threshold=None keeps psycopg compatible with Supabase's transaction pooler (port 6543).
    engine = create_engine(
        DATABASE_URL, pool_pre_ping=True, pool_size=5, max_overflow=5, pool_recycle=300,
        connect_args={"prepare_threshold": None},
    )

SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def get_db() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    from backend import models  # noqa: F401  (registers tables)

    Base.metadata.create_all(engine)
