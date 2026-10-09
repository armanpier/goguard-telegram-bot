import pytest
from httpx import AsyncClient, ASGITransport
from unittest.mock import AsyncMock
from app.config import settings
from app.web.app import create_web_app, create_session_token, verify_session_token
from app.database.session import async_session_factory, init_db
from app.services.settings_service import set_web_password


@pytest.fixture(autouse=True)
async def setup_test_db():
    await init_db()


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
async def test_webui_login_and_force_password_change():
    mock_bot = AsyncMock()
    mock_goguard = AsyncMock()
    app = create_web_app(mock_bot, mock_goguard)
    
    # Ensure default password is set to 'admin'
    async with async_session_factory() as session:
        await set_web_password(session, "admin")

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Invalid credentials
        resp = await client.post(
            "/login",
            data={"username": "wrong", "password": "wrongpassword"},
            follow_redirects=True,
        )
        assert "نام کاربری یا رمز عبور اشتباه است" in resp.text

        # 2. Valid initial login with admin:admin
        resp = await client.post(
            "/login",
            data={"username": "admin", "password": "admin"},
            follow_redirects=False,
        )
        assert resp.status_code in (302, 303)
        assert "admin_session" in resp.cookies
        # Should redirect to change-password because password is default 'admin'
        assert "/change-password" in resp.headers.get("location", "")

        # 3. Accessing /dashboard while password is still 'admin' forces redirect to /change-password
        client.cookies.set("admin_session", resp.cookies.get("admin_session"))
        resp2 = await client.get("/", follow_redirects=False)
        assert resp2.status_code in (302, 303, 307)
        assert "/change-password" in resp2.headers.get("location", "")

        # 4. Attempt to change password to 'admin' again (rejected)
        resp_same = await client.post(
            "/change-password",
            data={"current_password": "admin", "new_password": "admin", "confirm_password": "admin"},
        )
        assert resp_same.status_code == 400
        assert "رمز عبور جدید نمی‌تواند کلمه پیش‌فرض" in resp_same.text

        # 5. Successfully change password to strong password
        resp_change = await client.post(
            "/change-password",
            data={
                "current_password": "admin",
                "new_password": "SuperSecretPass2026",
                "confirm_password": "SuperSecretPass2026",
            },
            follow_redirects=False,
        )
        assert resp_change.status_code in (302, 303)
        assert "/dashboard" in resp_change.headers.get("location", "")

        # 6. Now accessing /dashboard succeeds (200 OK)
        resp_dashboard = await client.get("/dashboard", follow_redirects=True)
        assert resp_dashboard.status_code == 200
        assert "داشبورد و آمار سیستم" in resp_dashboard.text

        # 7. Old password 'admin' no longer works
        resp_old = await client.post(
            "/login",
            data={"username": "admin", "password": "admin"},
        )
        assert "نام کاربری یا رمز عبور اشتباه است" in resp_old.text

        # 8. Reset back to admin for standard test isolation
        async with async_session_factory() as session:
            await set_web_password(session, "admin")


@pytest.mark.asyncio
async def test_webui_pages_with_data_relationships():
    """Verify that dashboard, receipts, and subscriptions render without DetachedInstanceError."""
    import random
    from app.database.models import User, Plan, Subscription, PaymentReceipt

    uid = random.randint(10000000, 99999999)

    async with async_session_factory() as session:
        # Set non-default password so require_auth allows dashboard access
        await set_web_password(session, "SecurePassword123")

        # Create User
        test_user = User(id=uid, username=f"user_{uid}", full_name="تستر سیستم", balance=50000)
        session.add(test_user)

        # Create Plan
        test_plan = Plan(title="پلن تست ۱ ماهه", traffic_gb=20.0, duration_days=30, price=120000)
        session.add(test_plan)
        await session.flush()

        # Create Receipt
        test_receipt = PaymentReceipt(
            user_id=test_user.id,
            plan_id=test_plan.id,
            amount=120000,
            payment_type="plan_purchase",
            photo_file_id="test_photo_id",
            status="pending",
        )
        session.add(test_receipt)

        # Create Subscription
        test_sub = Subscription(
            user_id=test_user.id,
            plan_id=test_plan.id,
            goguard_username=f"u{uid}",
            data_limit_bytes=20 * 1024 * 1024 * 1024,
            expire_timestamp=1750000000,
            sub_url="https://sub.example.com/test",
            status="active",
        )
        session.add(test_sub)
        await session.commit()

    mock_bot = AsyncMock()
    mock_goguard = AsyncMock()
    mock_goguard.health_check = AsyncMock(return_value=True)
    app = create_web_app(mock_bot, mock_goguard)

    token = create_session_token("admin")
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test", cookies={"admin_session": token}) as client:
        # 1. Dashboard
        resp_dash = await client.get("/dashboard")
        assert resp_dash.status_code == 200
        assert "تستر سیستم" in resp_dash.text
        assert "پلن تست ۱ ماهه" in resp_dash.text

        # 2. Receipts page
        resp_rec = await client.get("/receipts")
        assert resp_rec.status_code == 200
        assert "تستر سیستم" in resp_rec.text
        assert f"@user_{uid}" in resp_rec.text
        assert "پلن تست ۱ ماهه" in resp_rec.text

        # 3. Subscriptions page
        resp_subs = await client.get("/subscriptions")
        assert resp_subs.status_code == 200
        assert f"u{uid}" in resp_subs.text
        assert "تستر سیستم" in resp_subs.text
        assert "پلن تست ۱ ماهه" in resp_subs.text

