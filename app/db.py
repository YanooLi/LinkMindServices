"""Async SQLAlchemy engine and session dependency."""
from collections.abc import AsyncIterator
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import get_settings


class Base(DeclarativeBase):
    pass


def normalize_url(url: str) -> tuple[str, dict]:
    """Accept provider URLs as given (e.g. Neon's postgresql://...?sslmode=require) and adapt them to asyncpg,
    which takes TLS as a connect argument instead of the sslmode/channel_binding query parameters."""
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]
    if url.startswith("postgresql://"):
        url = "postgresql+asyncpg://" + url[len("postgresql://"):]
    connect_args = {}
    parts = urlsplit(url)
    query = parse_qsl(parts.query)
    if any(k == "sslmode" and v != "disable" for k, v in query) or any(k == "ssl" for k, _ in query):
        connect_args["ssl"] = "require"
    query = [(k, v) for k, v in query if k not in ("sslmode", "channel_binding", "ssl")]
    return urlunsplit(parts._replace(query=urlencode(query))), connect_args


def make_engine(url: str | None = None):
    url, connect_args = normalize_url(url or get_settings().database_url)
    kwargs = {} if url.startswith("sqlite") else {"pool_size": 5, "max_overflow": 10, "pool_pre_ping": True}
    return create_async_engine(url, connect_args=connect_args, **kwargs)


engine = make_engine()
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)


async def get_session() -> AsyncIterator[AsyncSession]:
    async with SessionLocal() as session:
        yield session
