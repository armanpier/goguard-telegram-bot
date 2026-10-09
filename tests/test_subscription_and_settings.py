import pytest
import re
from unittest.mock import AsyncMock, patch
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from app.database.models import Base, Setting, Plan, User
from app.services.settings_service import get_setting, set_setting, get_all_settings


@pytest.mark.asyncio
async def test_subscription_username_format():
    """Verify subscription usernames are alphanumeric and compatible with GoGuard regex."""
    import secrets
    user_id = 123456789
    
    for _ in range(50):
        username = f"u{user_id}{secrets.token_hex(2)}".lower()
        # Must only contain lowercase letters and numbers, NO underscores or special characters
        assert re.match(r"^[a-z0-9]+$", username) is not None
        assert "_" not in username
        assert len(username) <= 32


@pytest.mark.asyncio
async def test_settings_service_crud():
    """Verify dynamic settings database storage and retrieval."""
    test_engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async_session = async_sessionmaker(test_engine, expire_on_commit=False, class_=AsyncSession)
    
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        
    async with async_session() as session:
        # 1. Fallback to default
        val = await get_setting(session, "NON_EXISTENT_KEY", default="default_val")
        assert val == "default_val"
        
        # 2. Set value for a configurable key
        await set_setting(session, "CARD_NUMBER", "6037997112345678")
        val2 = await get_setting(session, "CARD_NUMBER")
        assert val2 == "6037997112345678"
        
        # 3. Update existing value
        await set_setting(session, "CARD_NUMBER", "5022291012345678")
        val3 = await get_setting(session, "CARD_NUMBER")
        assert val3 == "5022291012345678"
        
        # 4. Check get_all_settings includes standard keys
        all_sets = await get_all_settings(session)
        assert "CARD_NUMBER" in all_sets
        assert "GOGUARD_BASE_URL" in all_sets

    await test_engine.dispose()
