from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine

from app.models import Base

engine: AsyncEngine | None = None
SessionLocal: async_sessionmaker | None = None


def init_engine(database_url: str) -> async_sessionmaker:
    global engine, SessionLocal
    engine = create_async_engine(database_url, pool_pre_ping=True, future=True)
    SessionLocal = async_sessionmaker(engine, expire_on_commit=False)
    return SessionLocal


async def create_schema() -> None:
    if engine is None:
        raise RuntimeError("DB engine is not initialized")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def close_engine() -> None:
    if engine is not None:
        await engine.dispose()
