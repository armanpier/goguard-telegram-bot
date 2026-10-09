import pytest
from httpx import AsyncClient, ASGITransport
from unittest.mock import AsyncMock, MagicMock
from app.config import settings
from app.web.app import create_web_app, create_session_token, verify_session_token


def test_session_token_signing():
    username = "admin"
    token = create_session_token(username)
    assert token.startswith("admin:")
    
    # Valid verification
    assert verify_session_token(token) == "admin"
    
    # Invalid verification (tampered)
    tampered = token + "bad"
    assert verify_session_token(tampered) is None
    
    # Empty or malformed
    assert verify_session_token("") is None
    assert verify_session_token("admin_without_colon") is None


@pytest.mark.asyncio
async def test_webui_auth_redirect():
    mock_bot = AsyncMock()
    mock_goguard = AsyncMock()
    app = create_web_app(mock_bot, mock_goguard)
    
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Accessing dashboard without session should redirect to /login
        resp = await client.get("/", follow_redirects=False)
        assert resp.status_code in (302, 303, 307)
        assert resp.headers.get("location") == "/login"


@pytest.mark.asyncio
async def test_webui_login_flow():
    mock_bot = AsyncMock()
    mock_goguard = AsyncMock()
    app = create_web_app(mock_bot, mock_goguard)
    
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Invalid credentials
        resp = await client.post(
            "/login",
            data={"username": "wrong", "password": "wrongpassword"},
            follow_redirects=True,
        )
        assert "نام کاربری یا رمز عبور اشتباه است" in resp.text

        # 2. Valid credentials
        resp = await client.post(
            "/login",
            data={"username": settings.WEB_USERNAME, "password": settings.WEB_PASSWORD},
            follow_redirects=False,
        )
        assert resp.status_code in (302, 303)
        assert "admin_session" in resp.cookies
