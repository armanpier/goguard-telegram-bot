import logging
from typing import Any, Dict, Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.config import settings
from app.database.models import Setting

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
    merged["BOT_TOKEN"] = getattr(settings, "BOT_TOKEN", "")
    merged["ADMIN_IDS"] = str(getattr(settings, "ADMIN_IDS", []))
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
