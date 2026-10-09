import logging
from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload
from app.config import settings
from app.database.models import User, Plan, Subscription
from app.services.goguard import GoGuardClient
from app.services.subscription import (
    create_user_subscription,
    sync_subscription_details,
)
from app.services.qr import generate_qr_code_file
from app.bot.states.states import ReceiptState, WalletTopUpState
from app.bot.keyboards.default import get_cancel_keyboard
from app.bot.keyboards.inline import (
    get_plans_inline_keyboard,
    get_plan_payment_methods_keyboard,
    get_my_subscriptions_keyboard,
    get_subscription_actions_keyboard,
    get_topup_presets_keyboard,
)
from app.bot.utils.texts import (
    get_plan_card_text,
    get_card_payment_instructions,
    get_subscription_delivered_text,
    get_subscription_status_text,
    get_tutorials_text,
    get_referral_text,
    get_support_text,
)
from app.bot.utils.formatters import format_price

logger = logging.getLogger(__name__)
router = Router(name="user")


# =============================================================================
# 🛒 خرید اشتراک (Buy Subscription)
# =============================================================================

@router.message(F.text == "🛒 خرید اشتراک")
async def show_plans_menu(message: Message, session: AsyncSession):
    """Display active subscription plans to user."""
    stmt = select(Plan).where(Plan.is_active == True).order_by(Plan.price.asc())
    result = await session.execute(stmt)
    plans = result.scalars().all()

    if not plans:
        await message.answer("⚠️ در حال حاضر هیچ پلنی فعال نیست. لطفاً بعداً مراجعه فرمایید.")
        return

    kb = get_plans_inline_keyboard(plans)
    await message.answer("📦 لطفاً یکی از پلن‌های زیر را جهت خرید انتخاب کنید:", reply_markup=kb)


@router.callback_query(F.data == "back_to_plans")
async def callback_back_to_plans(callback: CallbackQuery, session: AsyncSession):
    """Return to plans list from plan card."""
    stmt = select(Plan).where(Plan.is_active == True).order_by(Plan.price.asc())
    result = await session.execute(stmt)
    plans = result.scalars().all()

    if not plans:
        await callback.answer("پلنی یافت نشد.", show_alert=True)
        return

    kb = get_plans_inline_keyboard(plans)
    await callback.message.edit_text("📦 لطفاً یکی از پلن‌های زیر را جهت خرید انتخاب کنید:", reply_markup=kb)
    await callback.answer()


@router.callback_query(F.data.startswith("select_plan:"))
async def callback_select_plan(callback: CallbackQuery, session: AsyncSession, db_user: User):
    """Show detailed plan info and payment options."""
    plan_id = int(callback.data.split(":")[1])
    stmt = select(Plan).where(Plan.id == plan_id)
    result = await session.execute(stmt)
    plan = result.scalar_one_or_none()

    if not plan or not plan.is_active:
        await callback.answer("پلن انتخابی معتبر نیست.", show_alert=True)
        return

    text = get_plan_card_text(
        plan_title=plan.title,
        traffic_gb=plan.traffic_gb,
        duration_days=plan.duration_days,
        price=plan.price,
        description=plan.description,
    )
    kb = get_plan_payment_methods_keyboard(
        plan_id=plan.id,
        user_balance=db_user.balance,
        plan_price=plan.price,
    )
    await callback.message.edit_text(text, reply_markup=kb)
    await callback.answer()


@router.callback_query(F.data.startswith("pay_wallet:"))
async def callback_pay_with_wallet(
    callback: CallbackQuery,
    session: AsyncSession,
    db_user: User,
    goguard: GoGuardClient,
):
    """Purchase plan immediately using user's wallet balance."""
    plan_id = int(callback.data.split(":")[1])
    stmt = select(Plan).where(Plan.id == plan_id)
    result = await session.execute(stmt)
    plan = result.scalar_one_or_none()

    if not plan or not plan.is_active:
        await callback.answer("پلن انتخابی معتبر نیست.", show_alert=True)
        return

    if db_user.balance < plan.price:
        await callback.answer("موجودی کیف پول شما کافی نیست!", show_alert=True)
        return

    await callback.message.edit_text("⏳ در حال صدور اشتراک از پنل GoGuard... لطفاً شکیبا باشید.")

    try:
        # Deduct balance
        db_user.balance -= plan.price

        # Provision subscription
        sub, sub_url, qr_file = await create_user_subscription(
            session=session,
            goguard=goguard,
            user=db_user,
            plan=plan,
            is_trial=False,
        )

        delivery_text = get_subscription_delivered_text(
            sub_title=plan.title,
            traffic_gb=plan.traffic_gb,
            expire_epoch=sub.expire_timestamp,
            sub_url=sub_url,
            is_trial=False,
        )

        await callback.message.delete()
        await callback.message.answer_photo(photo=qr_file, caption=delivery_text)

    except Exception as exc:
        logger.error(f"Error provisioning subscription via wallet: {exc}")
        # Rollback balance on failure
        db_user.balance += plan.price
        await session.commit()
        await callback.message.answer(f"❌ خطا در صدور اشتراک: {exc}\nمبلغ به کیف پول شما بازگردانده شد.")


@router.callback_query(F.data == "insufficient_balance")
async def callback_insufficient_balance(callback: CallbackQuery):
    """Notify user of insufficient wallet balance."""
    await callback.answer(
        "موجودی کیف پول شما کافی نیست! لطفاً از گزینه کارت به کارت استفاده کنید یا کیف پول خود را شارژ نمایید.",
        show_alert=True
    )


@router.callback_query(F.data.startswith("pay_card:"))
async def callback_pay_with_card(callback: CallbackQuery, state: FSMContext, session: AsyncSession):
    """Show bank card payment instructions and wait for receipt."""
    plan_id = int(callback.data.split(":")[1])
    stmt = select(Plan).where(Plan.id == plan_id)
    result = await session.execute(stmt)
    plan = result.scalar_one_or_none()

    if not plan or not plan.is_active:
        await callback.answer("پلن انتخابی معتبر نیست.", show_alert=True)
        return

    await state.set_state(ReceiptState.waiting_for_photo)
    await state.update_data(plan_id=plan.id, amount=plan.price, payment_type="plan_purchase")

    text = get_card_payment_instructions(
        amount=plan.price,
        card_number=settings.CARD_NUMBER,
        card_holder=settings.CARD_HOLDER,
    )
    await callback.message.delete()
    await callback.message.answer(text, reply_markup=get_cancel_keyboard())
    await callback.answer()


# =============================================================================
# 👤 سرویس‌های من (My Services)
# =============================================================================

@router.message(F.text == "👤 سرویس‌های من")
async def show_my_services(message: Message, session: AsyncSession, db_user: User):
    """List all active subscriptions belonging to the user."""
    stmt = (
        select(Subscription)
        .options(selectinload(Subscription.plan))
        .where(Subscription.user_id == db_user.id)
        .order_by(Subscription.id.desc())
    )
    result = await session.execute(stmt)
    subs = result.scalars().all()

    if not subs:
        await message.answer("شما در حال حاضر هیچ اشتراک فعالی ندارید. می‌توانید از بخش «🛒 خرید اشتراک» اقدام به تهیه نمایید.")
        return

    kb = get_my_subscriptions_keyboard(subs)
    await message.answer("📋 لیست سرویس‌های شما:\nجهت مشاهده جزئیات و ترافیک مصرفی، روی سرویس مورد نظر کلیک کنید:", reply_markup=kb)


@router.callback_query(F.data == "back_to_my_subs")
async def callback_back_to_my_subs(callback: CallbackQuery, session: AsyncSession, db_user: User):
    """Return to my subscriptions list."""
    stmt = (
        select(Subscription)
        .options(selectinload(Subscription.plan))
        .where(Subscription.user_id == db_user.id)
        .order_by(Subscription.id.desc())
    )
    result = await session.execute(stmt)
    subs = result.scalars().all()

    if not subs:
        await callback.message.edit_text("اشتراکی یافت نشد.")
        return

    kb = get_my_subscriptions_keyboard(subs)
    await callback.message.edit_text("📋 لیست سرویس‌های شما:", reply_markup=kb)
    await callback.answer()


@router.callback_query(F.data.startswith("view_sub:"))
async def callback_view_subscription(
    callback: CallbackQuery,
    session: AsyncSession,
    db_user: User,
    goguard: GoGuardClient,
):
    """View detailed statistics for selected subscription, synced live from GoGuard Panel."""
    sub_id = int(callback.data.split(":")[1])
    stmt = select(Subscription).where(Subscription.id == sub_id, Subscription.user_id == db_user.id)
    result = await session.execute(stmt)
    sub = result.scalar_one_or_none()

    if not sub:
        await callback.answer("اشتراک یافت نشد.", show_alert=True)
        return

    # Sync live stats with GoGuard API
    stats = await sync_subscription_details(session, goguard, sub)

    text = get_subscription_status_text(
        username=sub.goguard_username,
        used_bytes=stats["used_bytes"],
        total_bytes=stats["total_bytes"],
        expire_epoch=stats["expire_epoch"],
        status=stats["status"],
        sub_url=stats["sub_url"],
    )
    kb = get_subscription_actions_keyboard(sub.id, stats["sub_url"])
    await callback.message.edit_text(text, reply_markup=kb)
    await callback.answer()


@router.callback_query(F.data.startswith("refresh_sub:"))
async def callback_refresh_subscription(
    callback: CallbackQuery,
    session: AsyncSession,
    db_user: User,
    goguard: GoGuardClient,
):
    """Re-query GoGuard panel and refresh details."""
    sub_id = int(callback.data.split(":")[1])
    stmt = select(Subscription).where(Subscription.id == sub_id, Subscription.user_id == db_user.id)
    result = await session.execute(stmt)
    sub = result.scalar_one_or_none()

    if not sub:
        await callback.answer("اشتراک یافت نشد.", show_alert=True)
        return

    stats = await sync_subscription_details(session, goguard, sub)
    text = get_subscription_status_text(
        username=sub.goguard_username,
        used_bytes=stats["used_bytes"],
        total_bytes=stats["total_bytes"],
        expire_epoch=stats["expire_epoch"],
        status=stats["status"],
        sub_url=stats["sub_url"],
    )
    kb = get_subscription_actions_keyboard(sub.id, stats["sub_url"])

    try:
        await callback.message.edit_text(text, reply_markup=kb)
    except Exception:
        pass
    await callback.answer("اطلاعات از پنل به‌روزرسانی شد 🔄")


@router.callback_query(F.data.startswith("sub_qr:"))
async def callback_sub_qr(callback: CallbackQuery, session: AsyncSession, db_user: User):
    """Generate and send QR code image for subscription URL."""
    sub_id = int(callback.data.split(":")[1])
    stmt = select(Subscription).where(Subscription.id == sub_id, Subscription.user_id == db_user.id)
    result = await session.execute(stmt)
    sub = result.scalar_one_or_none()

    if not sub:
        await callback.answer("اشتراک یافت نشد.", show_alert=True)
        return

    qr_file = generate_qr_code_file(sub.sub_url, filename=f"{sub.goguard_username}_qr.png")
    caption = (
        f"📱 **QR Code اشتراک: {sub.goguard_username}**\n\n"
        f"برای اسکن مستقیم در نرم‌افزارهای V2RayNG یا Streisand استفاده کنید.\n\n"
        f"🔗 لینک مستقیم:\n`{sub.sub_url}`"
    )
    await callback.message.answer_photo(photo=qr_file, caption=caption)
    await callback.answer()


@router.callback_query(F.data.startswith("renew_sub:"))
async def callback_renew_sub(callback: CallbackQuery, session: AsyncSession):
    """Initiate renewal flow for subscription."""
    sub_id = int(callback.data.split(":")[1])
    stmt = select(Plan).where(Plan.is_active == True).order_by(Plan.price.asc())
    result = await session.execute(stmt)
    plans = result.scalars().all()

    if not plans:
        await callback.answer("پلنی جهت تمدید موجود نیست.", show_alert=True)
        return

    kb = get_plans_inline_keyboard(plans)
    await callback.message.answer(
        f"🔄 **تمدید سرویس #{sub_id}**\nلطفاً یکی از پلن‌ها را جهت افزایش حجم و زمان سرویس خود انتخاب کنید:",
        reply_markup=kb,
    )
    await callback.answer()


# =============================================================================
# 🎁 تست رایگان (Free Trial)
# =============================================================================

@router.message(F.text == "🎁 تست رایگان")
async def handle_free_trial(
    message: Message,
    session: AsyncSession,
    db_user: User,
    goguard: GoGuardClient,
):
    """Provision instant free trial subscription if enabled and not already used."""
    if not settings.FREE_TRIAL_ENABLED:
        await message.answer("⚠️ در حال حاضر ارائه سرویس تست رایگان غیرفعال است.")
        return

    if db_user.has_used_trial:
        await message.answer("⚠️ شما قبلاً از سهمیه اشتراک تست رایگان خود استفاده کرده‌اید. جهت ادامه استفاده لطفاً از منوی «🛒 خرید اشتراک» پلن تهیه فرمایید.")
        return

    wait_msg = await message.answer("⏳ در حال صدور اشتراک تست ۲۴ ساعته از پنل GoGuard... لطفاً چند لحظه صبر کنید.")

    try:
        sub, sub_url, qr_file = await create_user_subscription(
            session=session,
            goguard=goguard,
            user=db_user,
            plan=None,
            is_trial=True,
        )

        delivery_text = get_subscription_delivered_text(
            sub_title="تست رایگان",
            traffic_gb=settings.FREE_TRIAL_TRAFFIC_GB,
            expire_epoch=sub.expire_timestamp,
            sub_url=sub_url,
            is_trial=True,
        )

        await wait_msg.delete()
        await message.answer_photo(photo=qr_file, caption=delivery_text)

    except Exception as exc:
        logger.error(f"Error provisioning free trial: {exc}")
        await wait_msg.edit_text(f"❌ خطا در صدور اشتراک تست: {exc}\nلطفاً با پشتیبانی تماس بگیرید.")


# =============================================================================
# 💳 افزایش موجودی (Top-up Balance)
# =============================================================================

@router.message(F.text == "💳 افزایش موجودی")
async def show_topup_menu(message: Message, db_user: User):
    """Show options for wallet top-up."""
    text = (
        f"💳 **افزایش موجودی کیف پول**\n\n"
        f"موجودی فعلی شما: **{format_price(db_user.balance, settings.CURRENCY_TITLE)}**\n\n"
        "یکی از مبالغ زیر را انتخاب کنید یا مبلغ دلخواه را وارد نمایید:"
    )
    kb = get_topup_presets_keyboard()
    await message.answer(text, reply_markup=kb)


@router.callback_query(F.data.startswith("topup_amt:"))
async def callback_topup_preset(callback: CallbackQuery, state: FSMContext):
    """Top-up with preset amount."""
    amount = int(callback.data.split(":")[1])
    await state.set_state(WalletTopUpState.waiting_for_photo)
    await state.update_data(amount=amount, payment_type="wallet_topup")

    text = get_card_payment_instructions(
        amount=amount,
        card_number=settings.CARD_NUMBER,
        card_holder=settings.CARD_HOLDER,
    )
    await callback.message.delete()
    await callback.message.answer(text, reply_markup=get_cancel_keyboard())
    await callback.answer()


@router.callback_query(F.data == "topup_custom")
async def callback_topup_custom(callback: CallbackQuery, state: FSMContext):
    """Prompt for custom amount to top up."""
    await state.set_state(WalletTopUpState.waiting_for_amount)
    await callback.message.delete()
    await callback.message.answer(
        "لطفاً مبلغ مورد نظر برای افزایش موجودی را به عدد و به تومان وارد کنید (مثال: 150000):",
        reply_markup=get_cancel_keyboard(),
    )
    await callback.answer()


@router.message(WalletTopUpState.waiting_for_amount)
async def handle_custom_amount_input(message: Message, state: FSMContext):
    """Process custom amount string."""
    try:
        clean_num = message.text.strip().replace(",", "").replace("،", "")
        amount = int(clean_num)
        if amount < 10000:
            await message.answer("حداقل مبلغ شارژ ۱۰,۰۰۰ تومان می‌باشد. لطفاً دوباره وارد کنید:")
            return
    except ValueError:
        await message.answer("لطفاً یک عدد معتبر به عنوان مبلغ وارد نمایید:")
        return

    await state.set_state(WalletTopUpState.waiting_for_photo)
    await state.update_data(amount=amount, payment_type="wallet_topup")

    text = get_card_payment_instructions(
        amount=amount,
        card_number=settings.CARD_NUMBER,
        card_holder=settings.CARD_HOLDER,
    )
    await message.answer(text, reply_markup=get_cancel_keyboard())


# =============================================================================
# 🤝 همکاری در فروش (Referral & Affiliate)
# =============================================================================

@router.message(F.text == "🤝 همکاری در فروش")
async def show_referral_info(message: Message, session: AsyncSession, db_user: User):
    """Display referral link and earnings stats."""
    # Count referrals
    count_stmt = select(func.count(User.id)).where(User.referrer_id == db_user.id)
    count_res = await session.execute(count_stmt)
    invited_count = count_res.scalar() or 0

    bot_info = await message.bot.get_me()
    text = get_referral_text(
        user_id=db_user.id,
        invited_count=invited_count,
        total_earned=db_user.balance,
        bot_username=bot_info.username or "GoGuardBot",
    )
    await message.answer(text)


# =============================================================================
# 📚 راهنما و پشتیبانی (Tutorials & Support)
# =============================================================================

@router.message(F.text == "📚 راهنمای اتصال")
async def show_tutorials(message: Message):
    """Display software download links and setup tutorials."""
    await message.answer(get_tutorials_text(), disable_web_page_preview=True)


@router.message(F.text == "📞 پشتیبانی")
async def show_support(message: Message):
    """Display support username and details."""
    await message.answer(get_support_text())
