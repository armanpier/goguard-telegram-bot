import pytest
from httpx import AsyncClient, ASGITransport
from unittest.mock import AsyncMock

from app.config import settings
from app.database.session import async_session_factory, init_db
from app.database.models import User
from app.services.settings_service import (
    get_admin_ids,
    add_admin_id,
    remove_admin_id,
    get_admin_details,
    set_web_password,
)
from app.bot.keyboards.admin import (
    get_admin_dashboard_keyboard,
    get_admins_management_keyboard,
)
from app.web.app import create_web_app, create_session_token


from sqlalchemy import delete
from app.database.models import Setting


@pytest.fixture(autouse=True)
async def setup_test_db():
    await init_db()
    async with async_session_factory() as session:
        await session.execute(delete(Setting).where(Setting.key == "ADMIN_IDS"))
        await session.execute(delete(User).where(User.id.in_([111111, 222222, 333333, 444444, 555555, 777777, 888888])))
        await session.commit()
    settings.ADMIN_IDS = [111111]



@pytest.mark.asyncio
async def test_admin_service_crud():
    async with async_session_factory() as session:
        # Reset / initialize admin IDs
        settings.ADMIN_IDS = [111111]
        ids = await get_admin_ids(session)
        assert 111111 in ids

        # 1. Add new admin
        success, msg = await add_admin_id(session, 222222)
        assert success is True
        assert 222222 in settings.ADMIN_IDS

        # 2. Add duplicate admin (should fail)
        dup_success, dup_msg = await add_admin_id(session, 222222)
        assert dup_success is False
        assert "در حال حاضر" in dup_msg

        # 3. Add invalid admin ID (should fail)
        inv_success, _ = await add_admin_id(session, -5)
        assert inv_success is False

        # 4. Remove admin 222222
        del_success, del_msg = await remove_admin_id(session, 222222)
        assert del_success is True
        assert 222222 not in settings.ADMIN_IDS

        # 5. Attempt to delete non-existent admin
        del_non_success, _ = await remove_admin_id(session, 999999)
        assert del_non_success is False

        # 6. Attempt to delete the last remaining admin (should be protected)
        assert len(settings.ADMIN_IDS) == 1
        last_del_success, last_del_msg = await remove_admin_id(session, settings.ADMIN_IDS[0])
        assert last_del_success is False
        assert "تنها ادمین" in last_del_msg
        assert len(settings.ADMIN_IDS) == 1


@pytest.mark.asyncio
async def test_get_admin_details():
    async with async_session_factory() as session:
        # Create user in db
        user = User(id=888888, username="boss_admin", full_name="مدیر ارشد", balance=1000)
        session.add(user)
        await session.commit()

        # Add to admin list
        await add_admin_id(session, 888888)
        # Also add an unregistered admin
        await add_admin_id(session, 777777)

        details = await get_admin_details(session)
        admin_map = {d["id"]: d for d in details}

        assert 888888 in admin_map
        assert admin_map[888888]["username"] == "boss_admin"
        assert admin_map[888888]["full_name"] == "مدیر ارشد"
        assert admin_map[888888]["is_registered"] is True

        assert 777777 in admin_map
        assert admin_map[777777]["is_registered"] is False


def test_admin_keyboards():
    # 1. Main dashboard keyboard includes admin_manage_admins
    kb = get_admin_dashboard_keyboard()
    callbacks = [btn.callback_data for row in kb.inline_keyboard for btn in row]
    assert "admin_manage_admins" in callbacks

    # 2. Admins management keyboard
    mock_admins = [
        {"id": 111, "username": "admin1", "full_name": "Admin One"},
        {"id": 222, "username": None, "full_name": "Admin Two"},
    ]
    manage_kb = get_admins_management_keyboard(mock_admins, current_user_id=111)
    manage_callbacks = [btn.callback_data for row in manage_kb.inline_keyboard for btn in row]
    
    assert "admin_add_admin" in manage_callbacks
    assert "admin_del_admin:222" in manage_callbacks
    assert "admin_del_admin:111" in manage_callbacks
    assert "admin_back_home" in manage_callbacks


@pytest.mark.asyncio
async def test_webui_admins_endpoints():
    async with async_session_factory() as session:
        await set_web_password(session, "StrongPass999")
        await add_admin_id(session, 333333)
        await add_admin_id(session, 444444)

    mock_bot = AsyncMock()
    mock_goguard = AsyncMock()
    app = create_web_app(mock_bot, mock_goguard)

    token = create_session_token("admin")
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test", cookies={"admin_session": token}) as client:
        # 1. GET /admins
        resp = await client.get("/admins")
        assert resp.status_code == 200
        assert "مدیریت ادمین‌های ربات تلگرام" in resp.text
        assert "333333" in resp.text
        assert "444444" in resp.text

        # 2. POST /admins/add
        add_resp = await client.post("/admins/add", data={"admin_id": 555555}, follow_redirects=True)
        assert add_resp.status_code == 200
        assert "555555" in add_resp.text

        # 3. POST /admins/555555/delete
        del_resp = await client.post("/admins/555555/delete", follow_redirects=True)
        assert del_resp.status_code == 200
        assert "با موفقیت حذف شد" in del_resp.text
        # Ensure 555555 is not in the active admins list table
        table_body = del_resp.text.split("<tbody")[1].split("</tbody>")[0]
        assert "555555" not in table_body
