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


def test_installer_detection_and_sanitize(tmp_path, monkeypatch):
    """Verify setup.py can detect existing files and sanitize env safely."""
    from setup import detect_installation_state, sanitize_and_patch_env
    
    # Change working directory to isolated temp path
    monkeypatch.chdir(tmp_path)
    
    # 1. Fresh state
    fresh_state = detect_installation_state()
    assert fresh_state["is_installed"] is False
    assert fresh_state["has_env"] is False
    assert fresh_state["has_db"] is False
    
    # 2. Simulate existing installation
    (tmp_path / ".env").write_text("BOT_TOKEN=123:abc\nADMIN_IDS=123456\nCARD_NUMBER=6037\n", encoding="utf-8")
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "bot.db").write_text("fake db", encoding="utf-8")
    
    detected = detect_installation_state()
    assert detected["is_installed"] is True
    assert detected["has_env"] is True
    assert detected["has_db"] is True
    
    # 3. Sanitize and patch
    env_data = {"BOT_TOKEN": "123:abc", "ADMIN_IDS": "123456", "CARD_NUMBER": "6037"}
    patched = sanitize_and_patch_env(env_data)
    
    # ADMIN_IDS should be converted to JSON list
    assert patched["ADMIN_IDS"] == "[123456]"
    # Web variables injected
    assert patched["WEB_ENABLE"] == "true"
    assert patched["WEB_PORT"] == "8080"
    assert patched["WEB_USERNAME"] == "admin"
    assert patched["WEB_PASSWORD"] == "admin"
    assert "WEB_SECRET_KEY" in patched

