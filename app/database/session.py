import os
import logging
from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from app.config import settings
from app.database.models import Base, Plan

logger = logging.getLogger(__name__)


def _ensure_sqlite_directory(db_url: str) -> None:
    """Ensure parent directory for sqlite database exists before connecting."""
    if "sqlite" in db_url:
        parts = db_url.split(":///", 1)
        if len(parts) == 2:
            db_path = parts[1]
            dir_name = os.path.dirname(db_path)
            if dir_name:
                try:
                    os.makedirs(dir_name, exist_ok=True)
                except Exception as exc:
                    logger.warning(f"Could not create database directory '{dir_name}': {exc}")


_ensure_sqlite_directory(settings.DATABASE_URL)

engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.DEBUG,
    future=True,
)

async_session_factory = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with async_session_factory() as session:
        try:
            yield session
        finally:
            await session.close()


async def init_db() -> None:
    """Initialize database tables and seed default plans if empty."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Seed default plans if none exist
    async with async_session_factory() as session:
        from sqlalchemy import select
        result = await session.execute(select(Plan))
        existing_plans = result.scalars().all()
        if not existing_plans:
            default_plans = [
                Plan(
                    title="🥉 پلن پایه (۱ ماهه ۳۰ گیگ)",
                    traffic_gb=30.0,
                    duration_days=30,
                    price=95000,
                    description="مناسب استفاده روزمره، وب‌گردی و پیام‌رسان‌ها",
                ),
                Plan(
                    title="🥈 پلن نقره‌ای (۱ ماهه ۵۰ گیگ)",
                    traffic_gb=50.0,
                    duration_days=30,
                    price=145000,
                    description="سرعت عالی، مناسب اینستاگرام، یوتیوب و دانلود",
                ),
                Plan(
                    title="🥇 پلن طلایی (۲ ماهه ۱۰۰ گیگ)",
                    traffic_gb=100.0,
                    duration_days=60,
                    price=260000,
                    description="حجم و زمان بالا، بالاترین اولویت و سرعت",
                ),
                Plan(
                    title="💎 پلن نامحدود زمانی (۱۰۰ گیگ)",
                    traffic_gb=100.0,
                    duration_days=90,
                    price=290000,
                    description="۳ ماه اعتبار، ۱۰۰ گیگابایت حجم با آی‌پی اختصاصی",
                ),
            ]
            session.add_all(default_plans)
            await session.commit()
            logger.info("Default plans seeded successfully.")
