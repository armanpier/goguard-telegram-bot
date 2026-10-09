import logging
import secrets
import time
from typing import Any, Dict, Optional, Tuple
from sqlalchemy.ext.asyncio import AsyncSession
from app.config import settings
from app.database.models import User, Plan, Subscription
from app.services.goguard import GoGuardClient
from app.services.qr import generate_qr_code_file
from app.bot.utils.formatters import traffic_gb_to_bytes, days_to_epoch_expire
from aiogram.types import BufferedInputFile

logger = logging.getLogger(__name__)


def generate_unique_subscription_username(user_id: int) -> str:
    """Generate clean, alphanumeric lowercase username for GoGuard panel."""
    rand_suffix = secrets.token_hex(2)
    return f"u{user_id}{rand_suffix}".lower()


async def create_user_subscription(
    session: AsyncSession,
    goguard: GoGuardClient,
    user: User,
    plan: Optional[Plan] = None,
    is_trial: bool = False,
) -> Tuple[Subscription, str, BufferedInputFile]:
    """
    Provision a new subscription on GoGuard Panel API 1.0,
    store the record in the database, and generate the QR code.
    """
    goguard_username = generate_unique_subscription_username(user.id)

    if is_trial:
        traffic_bytes = traffic_gb_to_bytes(settings.FREE_TRIAL_TRAFFIC_GB)
        expire_epoch = days_to_epoch_expire(settings.FREE_TRIAL_DURATION_DAYS)
        note = f"TG:{user.id} Trial"
        plan_id = None
    else:
        if not plan:
            raise ValueError("Plan must be provided for non-trial subscriptions")
        traffic_bytes = traffic_gb_to_bytes(plan.traffic_gb)
        expire_epoch = days_to_epoch_expire(plan.duration_days)
        note = f"TG:{user.id} P:{plan.id}"
        plan_id = plan.id

    # 1. Call GoGuard Panel API 1.0
    api_response = await goguard.create_subscription(
        username=goguard_username,
        data_limit=traffic_bytes,
        expire=expire_epoch,
        status="active",
        note=note,
    )

    # 2. Extract or construct subscription URL
    sub_url = goguard.get_subscription_url(goguard_username, api_response)

    # 3. Create Subscription record in DB
    sub = Subscription(
        user_id=user.id,
        plan_id=plan_id,
        goguard_username=goguard_username,
        data_limit_bytes=traffic_bytes,
        expire_timestamp=expire_epoch,
        sub_url=sub_url,
        status="active",
        is_trial=is_trial,
    )
    session.add(sub)

    if is_trial:
        user.has_used_trial = True

    await session.commit()
    await session.refresh(sub)

    # 4. Generate QR code
    qr_file = generate_qr_code_file(sub_url, filename=f"{goguard_username}_qr.png")

    logger.info(f"Subscription #{sub.id} ({goguard_username}) created successfully for user {user.id}")
    return sub, sub_url, qr_file


async def sync_subscription_details(
    session: AsyncSession,
    goguard: GoGuardClient,
    sub: Subscription,
) -> Dict[str, Any]:
    """
    Fetch live statistics from GoGuard Panel API 1.0 and sync with local DB.
    """
    try:
        data = await goguard.get_subscription(sub.goguard_username)
    except Exception as exc:
        logger.warning(f"Failed to fetch live stats for {sub.goguard_username}: {exc}")
        # Return local fallback
        return {
            "username": sub.goguard_username,
            "used_bytes": 0,
            "total_bytes": sub.data_limit_bytes,
            "expire_epoch": sub.expire_timestamp,
            "status": sub.status,
            "sub_url": sub.sub_url,
        }

    # GoGuard typical response fields
    total_bytes = data.get("limit_usage") or data.get("data_limit") or sub.data_limit_bytes
    used_traffic = data.get("total_usage") or data.get("used_traffic")
    if used_traffic is None:
        up = data.get("up", 0) or 0
        down = data.get("down", 0) or 0
        used_bytes = up + down
    else:
        used_bytes = int(used_traffic)

    expire = data.get("limit_expire") or data.get("expire") or sub.expire_timestamp
    status = "active" if data.get("enabled") is True else (data.get("status") or sub.status)
    sub_url = goguard.get_subscription_url(sub.goguard_username, data) or sub.sub_url

    # Update local DB if changed
    changed = False
    if sub.status != status:
        sub.status = status
        changed = True
    if sub.expire_timestamp != expire:
        sub.expire_timestamp = expire
        changed = True
    if sub.sub_url != sub_url:
        sub.sub_url = sub_url
        changed = True
    if changed:
        await session.commit()

    return {
        "username": sub.goguard_username,
        "used_bytes": used_bytes,
        "total_bytes": total_bytes,
        "expire_epoch": expire,
        "status": status,
        "sub_url": sub.sub_url,
    }


async def renew_user_subscription(
    session: AsyncSession,
    goguard: GoGuardClient,
    sub: Subscription,
    plan: Plan,
) -> Tuple[Subscription, str, BufferedInputFile]:
    """
    Renew an existing subscription by extending its traffic limit and expiration date.
    """
    now = int(time.time())
    extra_traffic = traffic_gb_to_bytes(plan.traffic_gb)
    new_data_limit = sub.data_limit_bytes + extra_traffic

    base_expire = max(sub.expire_timestamp, now)
    new_expire = base_expire + (plan.duration_days * 86400)

    # Call GoGuard API update
    await goguard.update_subscription(
        username=sub.goguard_username,
        data_limit=new_data_limit,
        expire=new_expire,
        status="active",
        note=f"TG:{sub.user_id} Renew P:{plan.id}",
    )

    sub.data_limit_bytes = new_data_limit
    sub.expire_timestamp = new_expire
    sub.status = "active"
    sub.plan_id = plan.id

    await session.commit()
    await session.refresh(sub)

    qr_file = generate_qr_code_file(sub.sub_url, filename=f"{sub.goguard_username}_renew_qr.png")
    return sub, sub.sub_url, qr_file
