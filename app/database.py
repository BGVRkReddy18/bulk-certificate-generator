"""
AEREO Bulk Certificate Generator — Database setup.

Provides the SQLAlchemy engine, session factory, Base class,
and a FastAPI dependency for obtaining a DB session.
"""

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import settings


engine = create_engine(
    settings.DATABASE_URL,
    connect_args={"check_same_thread": False},  # required for SQLite
    echo=False,
)

SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""
    pass


def init_db() -> None:
    """Create all tables that don't already exist."""
    Base.metadata.create_all(bind=engine)


def get_db() -> Session:  # type: ignore[misc]
    """FastAPI dependency — yields a DB session and closes it afterwards."""
    db = SessionLocal()
    try:
        yield db  # type: ignore[misc]
    finally:
        db.close()
