from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy import BigInteger, String, DateTime, Text, Integer, func
from sqlalchemy.dialects.postgresql import JSON, ARRAY
from typing import Optional, List
from datetime import datetime

from config import DATABASE_URL

engine = create_async_engine(DATABASE_URL.replace("postgres://", "postgresql+asyncpg://"), echo=False)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

class Base(DeclarativeBase):
    pass

class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    username: Mapped[Optional[str]] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(20), default="editor")
    added_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

class ScheduledPost(Base):
    __tablename__ = "scheduled_posts"
    id: Mapped[int] = mapped_column(primary_key=True)
    channel_id: Mapped[int] = mapped_column(BigInteger)
    channel_name: Mapped[str] = mapped_column(String(100))
    content_text: Mapped[Optional[str]] = mapped_column(Text)
    media_file_ids: Mapped[Optional[list]] = mapped_column(JSON)  # список file_id
    media_type: Mapped[str] = mapped_column(String(20), default="text")  # text/photo/album
    scheduled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[int] = mapped_column(BigInteger)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

async def get_user(telegram_id: int) -> Optional[User]:
    async with async_session() as session:
        return await session.get(User, telegram_id)

async def add_user(telegram_id: int, username: str, role: str = "editor"):
    async with async_session() as session:
        user = User(telegram_id=telegram_id, username=username, role=role)
        session.add(user)
        await session.commit()
        return user

async def get_pending_posts():
    async with async_session() as session:
        result = await session.execute(
            select(ScheduledPost).where(
                ScheduledPost.status == "pending",
                ScheduledPost.scheduled_at > func.now()
            )
        )
        return result.scalars().all()

# и другие функции работы с постами...