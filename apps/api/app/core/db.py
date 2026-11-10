"""SQLAlchemy engine/session for core. The URL comes from settings.database_url at first use."""

from collections.abc import Iterator
from functools import lru_cache

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.settings import settings


class Base(DeclarativeBase):
    pass


def sqlalchemy_url(url: str) -> str:
    """Accept plain postgresql:// URLs (docker/.env) and use the psycopg 3 driver."""
    for prefix in ("postgresql://", "postgres://"):
        if url.startswith(prefix):
            return "postgresql+psycopg://" + url[len(prefix) :]
    return url


@lru_cache
def get_engine() -> Engine:
    return create_engine(sqlalchemy_url(settings.database_url), pool_pre_ping=True)


@lru_cache
def session_factory() -> sessionmaker[Session]:
    return sessionmaker(bind=get_engine(), expire_on_commit=False)


def reset_engine() -> None:
    """Drop the cached engine and session factory (tests switch databases)."""
    if get_engine.cache_info().currsize:
        get_engine().dispose()
    get_engine.cache_clear()
    session_factory.cache_clear()


def get_session() -> Iterator[Session]:
    with session_factory()() as session:
        yield session
