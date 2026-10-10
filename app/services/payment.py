import datetime
import logging
from typing import Optional, Tuple
from aiogram import Bot
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.config import settings
from app.database.models import User, Plan, PaymentReceipt, Subscription
from app.services.goguard import GoGuardClient
from app.services.subscription import create_user_subscription
from app.services.qr import generate_qr_code_file
from app.bot.keyboards.admin import get_receipt_review_keyboard
from app.bot.keyboards.inline import get_subscription_delivered_keyboard
from app.bot.utils.texts import (
    get_receipt_admin_alert_text,
    get_subscription_delivered_text,
)
from app.bot.utils.formatters import format_price

logger = logging.getLogger(__name__)


async def record_payment_receipt(
    bot: Bot,
    session: AsyncSession,
    user: User,
    photo_file_id: str,
    amount: int,
    payment_type: str = "plan_purchase",
    plan: Optional[Plan] = None,
) -> PaymentReceipt:
    """
    Save receipt in database and notify admins with receipt photo and review buttons.
    """
    receipt = PaymentReceipt(
        user_id=user.id,
        plan_id=plan.id if plan else None,
        amount=amount,
        payment_type=payment_type,
        photo_file_id=photo_file_id,
        status="pending",
    )
    session.add(receipt)
    await session.commit()
    await session.refresh(receipt)

    # Notify all admins
    alert_text = get_receipt_admin_alert_text(
        receipt_id=receipt.id,
        user_id=user.id,
        user_name=user.full_name,
        username=user.username,
        amount=amount,
        payment_type=payment_type,
        plan_title=plan.title if plan else None,
    )
    kb = get_receipt_review_keyboard(receipt.id)

    for admin_id in settings.ADMIN_IDS:
        try:
            await bot.send_photo(
                chat_id=admin_id,
                photo=photo_file_id,
                caption=alert_text,
                reply_markup=kb,
            )
        except Exception as exc:
            logger.error(f"Failed to notify admin {admin_id} for receipt #{receipt.id}: {exc}")

    return receipt


async def process_receipt_approval(
    bot: Bot,
    session: AsyncSession,
    goguard: GoGuardClient,
    receipt_id: int,
) -> Tuple[bool, str]:
    """
    Approve payment receipt, provision subscription (or credit wallet),
    apply referral commission, and notify user.
    """
    stmt = (
        select(PaymentReceipt)
        .where(PaymentReceipt.id == receipt_id)
    )
    result = await session.execute(stmt)
    receipt = result.scalar_one_or_none()

    if not receipt:
        return False, "رسید مورد نظر یافت نشد."

    if receipt.status != "pending":
        return False, f"این رسید قبلاً تعیین وضعیت شده است ({receipt.status})."

    # Fetch user
    user_stmt = select(User).where(User.id == receipt.user_id)
    user_res = await session.execute(user_stmt)
    user = user_res.scalar_one_or_none()
    if not user:
        return False, "کاربر صادرکننده رسید یافت نشد."

    receipt.status = "approved"
    receipt.reviewed_at = datetime.datetime.now(datetime.timezone.utc)

    if receipt.payment_type == "plan_purchase":
        # Fetch plan
        plan_stmt = select(Plan).where(Plan.id == receipt.plan_id)
        plan_res = await session.execute(plan_stmt)
        plan = plan_res.scalar_one_or_none()
        if not plan:
            return False, "پلن انتخابی مربوط به این رسید یافت نشد."

        # Provision subscription on GoGuard Panel API
        try:
            sub, sub_url, qr_file = await create_user_subscription(
                session=session,
                goguard=goguard,
                user=user,
                plan=plan,
                is_trial=False,
            )
        except Exception as exc:
            logger.error(f"Failed to create GoGuard subscription on receipt approval: {exc}")
            receipt.status = "pending"
            await session.commit()
            return False, f"خطا در ایجاد اشتراک در پنل GoGuard: {exc}"

        # Send subscription to user
        delivery_text = get_subscription_delivered_text(
            sub_title=plan.title,
            traffic_gb=plan.traffic_gb,
            expire_epoch=sub.expire_timestamp,
            sub_url=sub_url,
            is_trial=False,
        )
        kb = get_subscription_delivered_keyboard(sub_url)
        try:
            await bot.send_photo(
                chat_id=user.id,
                photo=qr_file,
                caption=delivery_text,
                reply_markup=kb,
            )
        except Exception as exc:
            logger.error(f"Failed to send subscription photo with caption to user {user.id}: {exc}")
            # Ensure QR code image is still delivered even if caption failed
            try:
                fresh_qr = generate_qr_code_file(sub_url)
                await bot.send_photo(chat_id=user.id, photo=fresh_qr, caption="📱 تصویر QR Code اشتراک شما")
            except Exception as e2:
                logger.error(f"Failed to send fallback QR photo: {e2}")
            await bot.send_message(chat_id=user.id, text=delivery_text, reply_markup=kb)

        # Handle Referral Commission
        if settings.REFERRAL_ENABLED and user.referrer_id:
            commission = int(receipt.amount * (settings.REFERRAL_COMMISSION_PERCENT / 100.0))
            if commission > 0:
                ref_stmt = select(User).where(User.id == user.referrer_id)
                ref_res = await session.execute(ref_stmt)
                referrer = ref_res.scalar_one_or_none()
                if referrer:
                    referrer.balance += commission
                    try:
                        await bot.send_message(
                            chat_id=referrer.id,
                            text=(
                                f"🎉 **پورسانت همکاری در فروش!**\n\n"
                                f"یکی از زیرمجموعه‌های شما خریدی انجام داد و مبلغ "
                                f"**{format_price(commission, settings.CURRENCY_TITLE)}** "
                                f"به موجودی کیف پول شما واریز شد."
                            )
                        )
                    except Exception as exc:
                        logger.warning(f"Failed to notify referrer {referrer.id}: {exc}")

    elif receipt.payment_type == "wallet_topup":
        user.balance += receipt.amount
        try:
            await bot.send_message(
                chat_id=user.id,
                text=(
                    f"✅ **شارژ کیف پول با موفقیت انجام شد.**\n\n"
                    f"مبلغ **{format_price(receipt.amount, settings.CURRENCY_TITLE)}** "
                    f"به موجودی حساب شما افزوده شد.\n"
                    f"موجودی فعلی: **{format_price(user.balance, settings.CURRENCY_TITLE)}**"
                )
            )
        except Exception as exc:
            logger.error(f"Failed to notify user {user.id} on wallet top-up: {exc}")

    await session.commit()
    return True, f"رسید #{receipt_id} با موفقیت تایید و اعمال شد."


async def process_receipt_rejection(
    bot: Bot,
    session: AsyncSession,
    receipt_id: int,
    reason: str = "اطلاعات فیش نامعتبر است",
) -> Tuple[bool, str]:
    """
    Reject payment receipt and notify user.
    """
    stmt = select(PaymentReceipt).where(PaymentReceipt.id == receipt_id)
    result = await session.execute(stmt)
    receipt = result.scalar_one_or_none()

    if not receipt:
        return False, "رسید یافت نشد."

    if receipt.status != "pending":
        return False, f"رسید قبلاً تعیین وضعیت شده است ({receipt.status})."

    receipt.status = "rejected"
    receipt.rejection_reason = reason
    receipt.reviewed_at = datetime.datetime.now(datetime.timezone.utc)
    await session.commit()

    # Notify user
    try:
        await bot.send_message(
            chat_id=receipt.user_id,
            text=(
                f"❌ **رسید پرداخت شما تایید نشد.**\n\n"
                f"شناسه رسید: #{receipt.id}\n"
                f"علت رد: **{reason}**\n\n"
                f"در صورت نیاز به راهنمایی، با پشتیبانی ربات (`{settings.SUPPORT_USERNAME}`) تماس بگیرید."
            )
        )
    except Exception as exc:
        logger.warning(f"Failed to notify user {receipt.user_id} of rejection: {exc}")

    return True, f"رسید #{receipt_id} با موفقیت رد شد."
