import json
import logging
from typing import Any, Dict, List, Optional, Tuple, Union
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from app.config import settings
from app.database.models import Setting, User

logger = logging.getLogger(__name__)

# List of all configurable setting keys
CONFIGURABLE_KEYS = [
    "CARD_NUMBER",
    "CARD_HOLDER",
    "CURRENCY_TITLE",
    "SUPPORT_USERNAME",
    "REQUIRED_CHANNEL_ID",
    "FREE_TRIAL_ENABLED",
    "FREE_TRIAL_TRAFFIC_GB",
    "FREE_TRIAL_DURATION_DAYS",
    "REFERRAL_ENABLED",
    "REFERRAL_COMMISSION_PERCENT",
    "GOGUARD_BASE_URL",
    "GOGUARD_USERNAME",
    "GOGUARD_PASSWORD",
    "GOGUARD_SUB_URL_TEMPLATE",
    "WEB_USERNAME",
    "WEB_PASSWORD",
]


async def get_admin_ids(session: AsyncSession) -> List[int]:
    """
    Retrieve admin IDs from database Setting table and environment config.
    Ensures environment admins and database admins are synchronized.
    """
    stmt = select(Setting).where(Setting.key == "ADMIN_IDS")
    res = await session.execute(stmt)
    record = res.scalar_one_or_none()

    admin_ids: List[int] = []
    if record and record.value:
        try:
            val = record.value.strip()
            if val.startswith("["):
                admin_ids = [int(x) for x in json.loads(val)]
            else:
                admin_ids = [int(x.strip()) for x in val.split(",") if x.strip()]
        except Exception as exc:
            logger.warning(f"Failed to parse ADMIN_IDS from database: {exc}")

    # Parse fallback from runtime/env settings
    raw_conf = getattr(settings, "ADMIN_IDS", [])
    env_ids: List[int] = []
    if isinstance(raw_conf, list):
        for x in raw_conf:
            try:
                env_ids.append(int(x))
            except (ValueError, TypeError):
                pass
    elif isinstance(raw_conf, int):
        env_ids = [raw_conf]

    if not admin_ids:
        admin_ids = env_ids
    else:
        # Preserve configured env admins so owners are never locked out
        for eid in env_ids:
            if eid not in admin_ids:
                admin_ids.append(eid)

    # Keep in-memory settings synchronized
    settings.ADMIN_IDS = admin_ids
    return admin_ids


async def is_user_admin(session: Optional[AsyncSession], user_id: Any) -> bool:
    """
    Verify if a user is an authorized admin across in-memory cache,
    database records, and environment settings.
    """
    if user_id is None:
        return False

    try:
        numeric_id = int(user_id)
    except (ValueError, TypeError):
        return False

    # 1. Quick check against in-memory settings.ADMIN_IDS
    in_mem_ids = getattr(settings, "ADMIN_IDS", [])
    if isinstance(in_mem_ids, list):
        for aid in in_mem_ids:
            try:
                if int(aid) == numeric_id:
                    return True
            except (ValueError, TypeError):
                continue
    elif isinstance(in_mem_ids, int) and in_mem_ids == numeric_id:
        return True

    # 2. Database check if session available
    if session:
        try:
            db_ids = await get_admin_ids(session)
            if numeric_id in db_ids:
                return True
        except Exception as exc:
            logger.warning(f"Error checking is_user_admin in DB: {exc}")

    return False


async def add_admin_id(session: AsyncSession, admin_identifier: Any) -> Tuple[bool, str]:
    """
    Add a new Telegram admin ID. Accepts integer numeric ID or string @username.
    If a username is provided, looks up existing registered user in database.
    """
    target_id: Optional[int] = None
    target_username: Optional[str] = None

    if isinstance(admin_identifier, int):
        target_id = admin_identifier
    elif isinstance(admin_identifier, str):
        cleaned = admin_identifier.strip()
        if cleaned.lstrip("-").isdigit():
            target_id = int(cleaned)
        else:
            # Username input e.g. @Sib_Support_P or Sib_Support_P
            target_username = cleaned.lstrip("@").strip()
            if not target_username:
                return False, "شناسه عددی یا نام کاربری وارد شده معتبر نمی‌باشد."

            stmt = select(User).where(func.lower(User.username) == target_username.lower())
            res = await session.execute(stmt)
            found_user = res.scalar_one_or_none()
            if not found_user:
                return False, (
                    f"کاربری با نام کاربری @{target_username} در دیتابیس یافت نشد. "
                    "کاربر مورد نظر ابتدا باید ربات را استارت کند، یا شناسه عددی (User ID) ایشان را وارد نمایید."
                )
            target_id = found_user.id
    else:
        return False, "فرمت شناسه یا نام کاربری نامعتبر است."

    if not target_id or target_id <= 0:
        return False, "شناسه کاربری وارد شده نامعتبر است."

    current_ids = await get_admin_ids(session)
    if target_id in current_ids:
        u_suffix = f" (@{target_username})" if target_username else ""
        return False, f"کاربر {target_id}{u_suffix} در حال حاضر در لیست مدیران ربات قرار دارد."

    updated_ids = list(current_ids) + [target_id]
    json_val = json.dumps(updated_ids)

    stmt = select(Setting).where(Setting.key == "ADMIN_IDS")
    res = await session.execute(stmt)
    record = res.scalar_one_or_none()
    if record:
        record.value = json_val
    else:
        record = Setting(key="ADMIN_IDS", value=json_val)
        session.add(record)

    await session.commit()
    settings.ADMIN_IDS = updated_ids
    logger.info(f"Added admin {target_id}. Active admins: {updated_ids}")
    u_suffix = f" (@{target_username})" if target_username else ""
    return True, f"ادمین جدید با شناسه {target_id}{u_suffix} با موفقیت افزوده شد."


async def remove_admin_id(session: AsyncSession, admin_id: int) -> Tuple[bool, str]:
    """Remove a Telegram admin ID with protection against removing the last admin."""
    current_ids = await get_admin_ids(session)
    if admin_id not in current_ids:
        return False, "کاربر مورد نظر در لیست ادمین‌ها یافت نشد."

    if len(current_ids) <= 1:
        return False, "امکان حذف تنها ادمین باقی‌مانده ربات وجود ندارد!"

    updated_ids = [x for x in current_ids if x != admin_id]
    json_val = json.dumps(updated_ids)

    stmt = select(Setting).where(Setting.key == "ADMIN_IDS")
    res = await session.execute(stmt)
    record = res.scalar_one_or_none()
    if record:
        record.value = json_val
    else:
        record = Setting(key="ADMIN_IDS", value=json_val)
        session.add(record)

    await session.commit()
    settings.ADMIN_IDS = updated_ids
    logger.info(f"Removed admin {admin_id}. Active admins: {updated_ids}")
    return True, f"ادمین با شناسه {admin_id} با موفقیت حذف شد."



async def get_admin_details(session: AsyncSession) -> List[Dict[str, Any]]:
    """Get rich profile info for all registered admins."""
    admin_ids = await get_admin_ids(session)
    details: List[Dict[str, Any]] = []

    for a_id in admin_ids:
        stmt = select(User).where(User.id == a_id)
        user_res = await session.execute(stmt)
        user = user_res.scalar_one_or_none()
        if user:
            details.append({
                "id": a_id,
                "username": user.username,
                "full_name": user.full_name or "بدون نام",
                "balance": user.balance,
                "is_banned": user.is_banned,
                "created_at": user.created_at,
                "is_registered": True,
            })
        else:
            details.append({
                "id": a_id,
                "username": None,
                "full_name": "کاربر ثبت‌نشده در دیتابیس",
                "balance": 0,
                "is_banned": False,
                "created_at": None,
                "is_registered": False,
            })

    return details


async def get_all_settings(session: AsyncSession) -> Dict[str, Any]:
    """
    Retrieve all settings, merging database overrides with .env defaults.
    """
    stmt = select(Setting)
    res = await session.execute(stmt)
    db_settings = {row.key: row.value for row in res.scalars().all()}

    merged = {}
    for key in CONFIGURABLE_KEYS:
        if key in db_settings:
            val = db_settings[key]
            # Convert booleans and numbers
            if val.lower() in ("true", "false"):
                merged[key] = val.lower() == "true"
            elif val.replace(".", "", 1).isdigit() and "." in val:
                merged[key] = float(val)
            elif val.isdigit():
                merged[key] = int(val)
            else:
                merged[key] = val
        else:
            merged[key] = getattr(settings, key, "")

    # Add bot token and admin ids as read-only / display
    admin_ids = await get_admin_ids(session)
    merged["BOT_TOKEN"] = getattr(settings, "BOT_TOKEN", "")
    merged["ADMIN_IDS"] = str(admin_ids)
    merged["DATABASE_URL"] = getattr(settings, "DATABASE_URL", "")

    return merged


async def get_setting(session: AsyncSession, key: str, default: Any = None) -> Any:
    """Retrieve a single setting by key, checking database then config fallback."""
    stmt = select(Setting).where(Setting.key == key)
    res = await session.execute(stmt)
    record = res.scalar_one_or_none()
    if record:
        return record.value
    if hasattr(settings, key):
        return getattr(settings, key)
    return default


async def set_setting(session: AsyncSession, key: str, value: Any) -> None:
    """Set or update a single setting."""
    await update_settings(session, {key: value})


async def get_web_credentials(session: AsyncSession) -> tuple[str, str]:
    """Retrieve current WebUI username and password from DB or config fallback."""
    username = await get_setting(session, "WEB_USERNAME", default=settings.WEB_USERNAME)
    password = await get_setting(session, "WEB_PASSWORD", default=settings.WEB_PASSWORD)
    return str(username or "admin"), str(password or "admin")


async def is_default_password(session: AsyncSession) -> bool:
    """Check if the current admin password is still the default 'admin'."""
    _, password = await get_web_credentials(session)
    return password == "admin"


async def set_web_password(session: AsyncSession, new_password: str) -> None:
    """Set new WebUI admin password in DB and runtime config."""
    await set_setting(session, "WEB_PASSWORD", new_password)
    settings.WEB_PASSWORD = new_password


async def update_settings(session: AsyncSession, new_values: Dict[str, Any]) -> None:
    """
    Update runtime settings in database and in-memory config.
    """
    for key, val in new_values.items():
        if key not in CONFIGURABLE_KEYS:
            continue

        str_val = str(val).strip()
        if key == "SUPPORT_USERNAME":
            import re
            clean_s = re.sub(r"^(?:https?://)?(?:www\.)?t\.me/", "", str_val).strip()
            clean_s = clean_s.strip("/").strip("@").strip("/")
            str_val = f"@{clean_s}" if clean_s else "@vpn_support"
        elif key == "REQUIRED_CHANNEL_ID":
            import re
            if str_val:
                if not (str_val.startswith("-100") or (str_val.startswith("-") and str_val[1:].isdigit()) or str_val.isdigit()):
                    clean_c = re.sub(r"^(?:https?://)?(?:www\.)?t\.me/", "", str_val).strip()
                    clean_c = clean_c.strip("/").strip("@").strip("/")
                    str_val = f"@{clean_c}" if clean_c else ""

        # Update in database
        stmt = select(Setting).where(Setting.key == key)
        res = await session.execute(stmt)
        record = res.scalar_one_or_none()

        if record:
            record.value = str_val
        else:
            record = Setting(key=key, value=str_val)
            session.add(record)

        # Update in-memory settings object
        if hasattr(settings, key):
            target_type = type(getattr(settings, key))
            try:
                if target_type == bool:
                    setattr(settings, key, str_val.lower() in ("true", "1", "yes"))
                elif target_type == int:
                    setattr(settings, key, int(str_val))
                elif target_type == float:
                    setattr(settings, key, float(str_val))
                else:
                    setattr(settings, key, str_val)
            except Exception as exc:
                logger.warning(f"Could not cast setting {key} to {target_type}: {exc}")

    await session.commit()
    logger.info("Dynamic settings successfully updated and saved.")
