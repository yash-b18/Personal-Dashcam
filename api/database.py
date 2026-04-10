"""
SQLAlchemy database engine and session configuration.

Provides a FastAPI dependency (`get_db`) that yields a scoped session
and ensures proper cleanup on request completion.
"""

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from api.config import get_settings


def _build_engine():
    """Create the SQLAlchemy engine from settings."""
    settings = get_settings()
    url = settings.database_url
    kwargs: dict = {"pool_pre_ping": True}
    # SQLite doesn't support connection pooling parameters
    if not url.startswith("sqlite"):
        kwargs.update({"pool_size": 10, "max_overflow": 20})
    return create_engine(url, **kwargs)


engine = _build_engine()

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy ORM models."""
    pass


def get_db() -> Generator[Session, None, None]:
    """
    FastAPI dependency that yields a database session.

    Ensures the session is closed after the request completes,
    even if an exception occurs.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
