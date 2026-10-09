import asyncio
import logging
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from app.config import settings
from app.database.models import User, Plan, Subscription, PaymentReceipt
from app.services.goguard import GoGuardClient
from app.services.payment import process_receipt_approval, process_receipt_rejection
from app.bot.states.states import (
    AdminAddPlanState,
    AdminBroadcastState,
    AdminUserManageState,
    AdminRejectReceiptState,
)
from app.bot.keyboards.default import get_cancel_keyboard, get_main_menu_keyboard
from app.bot.keyboards.admin import (
    get_admin_dashboard_keyboard,
    get_plans_management_keyboard,
    get_single_plan_manage_keyboard,
    get_receipt_review_keyboard,
)
from app.bot.utils.formatters import format_price

logger = logging.getLogger(__name__)
router = Router(name="admin")


# =============================================================================
# Dashboard Access
# =============================================================================

@router.message(Command("admin"))
@router.message(F.text == "⚙️ پنل مدیریت")
async def show_admin_panel(message: Message, is_admin: bool):
    """Show admin control panel."""
    if not is_admin:
        await message.answer("⛔️ شما به این بخش دسترسی ندارید.")
        return

    text = (
        "👑 **پنل مدیریت ربات GoGuard**\n\n"
        "از منوی زیر جهت مدیریت بخش‌های مختلف ربات استفاده نمایید:"
    )
    kb = get_admin_dashboard_keyboard()
    await message.answer(text, reply_markup=kb)


@router.callback_query(F.data == "admin_back_home")
async def callback_admin_back_home(callback: CallbackQuery, is_admin: bool):
    """Return to admin panel main menu."""
    if not is_admin:
        await callback.answer("دسترسی غیرمجاز", show_alert=True)
        return

    text = (
        "👑 **پنل مدیریت ربات GoGuard**\n\n"
        "از منوی زیر جهت مدیریت بخش‌های مختلف ربات استفاده نمایید:"
    )
    kb = get_admin_dashboard_keyboard()
    await callback.message.edit_text(text, reply_markup=kb)
    await callback.answer()


# =============================================================================
# 📊 آمار و گزارشات (Bot Statistics)
# =============================================================================

@router.callback_query(F.data == "admin_stats")
async def callback_admin_stats(callback: CallbackQuery, session: AsyncSession, is_admin: bool):
    """Show key performance indicators and numbers."""
    if not is_admin:
        return

    total_users = (await session.execute(select(func.count(User.id)))).scalar() or 0
    active_subs = (await session.execute(select(func.count(Subscription.id)).where(Subscription.status == "active"))).scalar() or 0
    total_sales = (await session.execute(
        select(func.sum(PaymentReceipt.amount)).where(PaymentReceipt.status == "approved")
    )).scalar() or 0
    pending_receipts = (await session.execute(
        select(func.count(PaymentReceipt.id)).where(PaymentReceipt.status == "pending")
    )).scalar() or 0

    text = (
        "📊 **آمار کلی ربات:**\n\n"
        f"👥 کل کاربران: **{total_users:,} نفر**\n"
        f"⚡️ اشتراک‌های فعال: **{active_subs:,} عدد**\n"
        f"⏳ رسیدهای در انتظار: **{pending_receipts:,} عدد**\n"
        f"💰 مجموع فروش تایید شده: **{format_price(total_sales, settings.CURRENCY_TITLE)}**\n"
    )
    kb = get_admin_dashboard_keyboard()
    await callback.message.edit_text(text, reply_markup=kb)
    await callback.answer()


# =============================================================================
# 🌐 وضعیت اتصال پنل GoGuard (Panel Health Check)
# =============================================================================

@router.callback_query(F.data == "admin_goguard_status")
async def callback_goguard_status(
    callback: CallbackQuery,
    goguard: GoGuardClient,
    is_admin: bool,
):
    """Verify GoGuard Panel API connectivity and admin credentials."""
    if not is_admin:
        return

    await callback.answer("در حال تست اتصال به پنل GoGuard...", show_alert=False)

    try:
        token = await goguard.login()
        health_ok = True
        error_msg = ""
    except Exception as exc:
        health_ok = False
        error_msg = str(exc)

    if health_ok:
        status_text = (
            "🟢 **وضعیت اتصال به پنل GoGuard: متصل و پایدار**\n\n"
            f"🌐 آدرس پنل: `{goguard.base_url}`\n"
            f"👤 کاربر ادمین: `{goguard.username}`\n"
            "✅ احراز هویت با موفقیت انجام شد و توکن دسترسی دریافت گردید."
        )
    else:
        status_text = (
            "🔴 **وضعیت اتصال به پنل GoGuard: خطا در اتصال!**\n\n"
            f"🌐 آدرس پنل: `{goguard.base_url}`\n"
            f"👤 کاربر ادمین: `{goguard.username}`\n"
            f"⚠️ پیام خطا: `{error_msg}`\n\n"
            "لطفاً آدرس پنل، نام کاربری و رمز عبور را در فایل تنظیمات (.env) بررسی فرمایید."
        )

    kb = get_admin_dashboard_keyboard()
    await callback.message.edit_text(status_text, reply_markup=kb)


# =============================================================================
# 💳 بررسی رسیدهای پرداخت (Receipt Review)
# =============================================================================

@router.callback_query(F.data == "admin_receipts")
async def callback_admin_receipts(callback: CallbackQuery, session: AsyncSession, is_admin: bool):
    """List pending receipts for admin review."""
    if not is_admin:
        return

    stmt = (
        select(PaymentReceipt)
        .where(PaymentReceipt.status == "pending")
        .order_by(PaymentReceipt.id.asc())
        .limit(5)
    )
    result = await session.execute(stmt)
    receipts = result.scalars().all()

    if not receipts:
        await callback.answer("هیچ رسیدی در انتظار تایید وجود ندارد ✅", show_alert=True)
        return

    await callback.message.delete()
    for rec in receipts:
        # Load user
        user_res = await session.execute(select(User).where(User.id == rec.user_id))
        user = user_res.scalar_one_or_none()
        u_name = user.full_name if user else "نامشخص"
        u_handle = f"@{user.username}" if (user and user.username) else "ندارد"

        caption = (
            f"💳 **رسید شماره #{rec.id}**\n\n"
            f"👤 کاربر: {u_name} ({u_handle}) | شناسه: `{rec.user_id}`\n"
            f"💵 مبلغ: **{format_price(rec.amount, settings.CURRENCY_TITLE)}**\n"
            f"🎯 نوع: {rec.payment_type}\n"
        )
        kb = get_receipt_review_keyboard(rec.id)
        try:
            await callback.message.answer_photo(
                photo=rec.photo_file_id,
                caption=caption,
                reply_markup=kb,
            )
        except Exception as exc:
            logger.error(f"Error displaying receipt #{rec.id}: {exc}")


@router.callback_query(F.data.startswith("adm_appr_rec:"))
async def callback_approve_receipt(
    callback: CallbackQuery,
    session: AsyncSession,
    goguard: GoGuardClient,
    is_admin: bool,
):
    """Approve receipt and provision subscription or credit wallet."""
    if not is_admin:
        return

    receipt_id = int(callback.data.split(":")[1])
    await callback.message.edit_caption(
        caption=f"{callback.message.caption or ''}\n\n⏳ در حال پردازش و صدور در GoGuard...",
        reply_markup=None,
    )

    success, msg = await process_receipt_approval(
        bot=callback.bot,
        session=session,
        goguard=goguard,
        receipt_id=receipt_id,
    )

    if success:
        await callback.message.edit_caption(
            caption=f"{callback.message.caption or ''}\n\n✅ **رسید توسط ادمین تایید و اعمال شد.**",
            reply_markup=None,
        )
        await callback.answer("رسید با موفقیت تایید شد ✅", show_alert=False)
    else:
        await callback.message.edit_caption(
            caption=f"{callback.message.caption or ''}\n\n⚠️ **خطا:** {msg}",
            reply_markup=get_receipt_review_keyboard(receipt_id),
        )
        await callback.answer(f"خطا: {msg}", show_alert=True)


@router.callback_query(F.data.startswith("adm_rej_rec:"))
async def callback_reject_receipt(callback: CallbackQuery, session: AsyncSession, is_admin: bool):
    """Reject receipt."""
    if not is_admin:
        return

    receipt_id = int(callback.data.split(":")[1])
    success, msg = await process_receipt_rejection(
        bot=callback.bot,
        session=session,
        receipt_id=receipt_id,
        reason="تصویر فیش ناخوانا یا واریزی نامعتبر است",
    )

    if success:
        await callback.message.edit_caption(
            caption=f"{callback.message.caption or ''}\n\n❌ **رسید توسط ادمین رد شد.**",
            reply_markup=None,
        )
        await callback.answer("رسید رد شد ❌", show_alert=False)
    else:
        await callback.answer(f"خطا: {msg}", show_alert=True)


# =============================================================================
# 📦 مدیریت پلن‌ها (Plans CRUD)
# =============================================================================

@router.callback_query(F.data == "admin_plans")
async def callback_admin_plans(callback: CallbackQuery, session: AsyncSession, is_admin: bool):
    """Display plans management list."""
    if not is_admin:
        return

    stmt = select(Plan).order_by(Plan.price.asc())
    result = await session.execute(stmt)
    plans = result.scalars().all()

    kb = get_plans_management_keyboard(plans)
    text = "📦 **مدیریت پلن‌ها و تعرفه‌ها:**\n\nبرای مشاهده یا تغییر وضعیت هر پلن، روی آن کلیک کنید:"
    await callback.message.edit_text(text, reply_markup=kb)
    await callback.answer()


@router.callback_query(F.data.startswith("admin_manage_plan:"))
async def callback_manage_single_plan(callback: CallbackQuery, session: AsyncSession, is_admin: bool):
    """Manage specific plan."""
    if not is_admin:
        return

    plan_id = int(callback.data.split(":")[1])
    stmt = select(Plan).where(Plan.id == plan_id)
    result = await session.execute(stmt)
    plan = result.scalar_one_or_none()

    if not plan:
        await callback.answer("پلن یافت نشد.", show_alert=True)
        return

    status_str = "🟢 فعال" if plan.is_active else "🔴 غیرفعال"
    text = (
        f"📦 **مدیریت پلن: {plan.title}**\n\n"
        f"وضعیت: {status_str}\n"
        f"📊 حجم: {plan.traffic_gb} گیگابایت\n"
        f"⏳ مدت: {plan.duration_days} روز\n"
        f"💵 قیمت: {format_price(plan.price, settings.CURRENCY_TITLE)}\n"
        f"📝 توضیحات: {plan.description or 'ندارد'}"
    )
    kb = get_single_plan_manage_keyboard(plan.id, plan.is_active)
    await callback.message.edit_text(text, reply_markup=kb)
    await callback.answer()


@router.callback_query(F.data.startswith("admin_toggle_plan:"))
async def callback_toggle_plan(callback: CallbackQuery, session: AsyncSession, is_admin: bool):
    """Toggle plan active/inactive status."""
    if not is_admin:
        return

    plan_id = int(callback.data.split(":")[1])
    stmt = select(Plan).where(Plan.id == plan_id)
    result = await session.execute(stmt)
    plan = result.scalar_one_or_none()

    if not plan:
        await callback.answer("پلن یافت نشد.", show_alert=True)
        return

    plan.is_active = not plan.is_active
    await session.commit()
    await callback.answer("وضعیت پلن تغییر یافت.")

    # Refresh view
    status_str = "🟢 فعال" if plan.is_active else "🔴 غیرفعال"
    text = (
        f"📦 **مدیریت پلن: {plan.title}**\n\n"
        f"وضعیت: {status_str}\n"
        f"📊 حجم: {plan.traffic_gb} گیگابایت\n"
        f"⏳ مدت: {plan.duration_days} روز\n"
        f"💵 قیمت: {format_price(plan.price, settings.CURRENCY_TITLE)}\n"
        f"📝 توضیحات: {plan.description or 'ندارد'}"
    )
    kb = get_single_plan_manage_keyboard(plan.id, plan.is_active)
    await callback.message.edit_text(text, reply_markup=kb)


@router.callback_query(F.data.startswith("admin_delete_plan:"))
async def callback_delete_plan(callback: CallbackQuery, session: AsyncSession, is_admin: bool):
    """Delete a plan."""
    if not is_admin:
        return

    plan_id = int(callback.data.split(":")[1])
    stmt = select(Plan).where(Plan.id == plan_id)
    result = await session.execute(stmt)
    plan = result.scalar_one_or_none()

    if plan:
        await session.delete(plan)
        await session.commit()
        await callback.answer("پلن با موفقیت حذف شد.", show_alert=True)

    # Return to plans list
    stmt = select(Plan).order_by(Plan.price.asc())
    result = await session.execute(stmt)
    plans = result.scalars().all()
    kb = get_plans_management_keyboard(plans)
    await callback.message.edit_text("📦 مدیریت پلن‌ها و تعرفه‌ها:", reply_markup=kb)


# Adding a new plan wizard
@router.callback_query(F.data == "admin_add_plan")
async def callback_start_add_plan(callback: CallbackQuery, state: FSMContext, is_admin: bool):
    """Initiate step-by-step plan creation wizard."""
    if not is_admin:
        return

    await state.set_state(AdminAddPlanState.waiting_for_title)
    await callback.message.delete()
    await callback.message.answer(
        "➕ **افزودن پلن جدید**\n\nلطفاً **عنوان پلن** را وارد کنید (مثال: پلن ۱ ماهه ۴۰ گیگ):",
        reply_markup=get_cancel_keyboard(),
    )
    await callback.answer()


@router.message(AdminAddPlanState.waiting_for_title)
async def process_plan_title(message: Message, state: FSMContext):
    title = message.text.strip()
    await state.update_data(title=title)
    await state.set_state(AdminAddPlanState.waiting_for_traffic)
    await message.answer("📊 لطفاً **حجم ترافیک به گیگابایت** را وارد کنید (مثال: 40 یا 40.5):")


@router.message(AdminAddPlanState.waiting_for_traffic)
async def process_plan_traffic(message: Message, state: FSMContext):
    try:
        traffic = float(message.text.strip())
        if traffic <= 0:
            raise ValueError()
    except ValueError:
        await message.answer("لطفاً یک عدد معتبر برای حجم وارد کنید:")
        return

    await state.update_data(traffic_gb=traffic)
    await state.set_state(AdminAddPlanState.waiting_for_duration)
    await message.answer("⏳ لطفاً **مدت اعتبار به روز** را وارد کنید (مثال: 30):")


@router.message(AdminAddPlanState.waiting_for_duration)
async def process_plan_duration(message: Message, state: FSMContext):
    try:
        days = int(message.text.strip())
        if days <= 0:
            raise ValueError()
    except ValueError:
        await message.answer("لطفاً یک عدد صحیح برای تعداد روزها وارد کنید:")
        return

    await state.update_data(duration_days=days)
    await state.set_state(AdminAddPlanState.waiting_for_price)
    await message.answer("💵 لطفاً **قیمت به تومان** را وارد کنید (مثال: 120000):")


@router.message(AdminAddPlanState.waiting_for_price)
async def process_plan_price(message: Message, state: FSMContext, session: AsyncSession, is_admin: bool):
    try:
        clean_p = message.text.strip().replace(",", "").replace("،", "")
        price = int(clean_p)
        if price <= 0:
            raise ValueError()
    except ValueError:
        await message.answer("لطفاً یک عدد صحیح برای مبلغ وارد کنید:")
        return

    data = await state.get_data()
    plan = Plan(
        title=data["title"],
        traffic_gb=data["traffic_gb"],
        duration_days=data["duration_days"],
        price=price,
        is_active=True,
    )
    session.add(plan)
    await session.commit()
    await state.clear()

    kb = get_main_menu_keyboard(is_admin=is_admin)
    await message.answer(f"✅ پلن **{plan.title}** با موفقیت ایجاد و فعال شد!", reply_markup=kb)


# =============================================================================
# 📢 ارسال پیام همگانی (Broadcast)
# =============================================================================

@router.callback_query(F.data == "admin_broadcast")
async def callback_admin_broadcast(callback: CallbackQuery, state: FSMContext, is_admin: bool):
    """Prompt admin for broadcast message."""
    if not is_admin:
        return

    await state.set_state(AdminBroadcastState.waiting_for_message)
    await callback.message.delete()
    await callback.message.answer(
        "📢 **ارسال پیام همگانی**\n\nلطفاً پیامی که می‌خواهید برای تمام کاربران ارسال شود را بنویسید یا فوروارد کنید:",
        reply_markup=get_cancel_keyboard(),
    )
    await callback.answer()


@router.message(AdminBroadcastState.waiting_for_message)
async def process_broadcast_message(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    is_admin: bool,
):
    """Broadcast message to all users in database."""
    await state.clear()
    status_msg = await message.answer("🚀 در حال شروع ارسال همگانی...", reply_markup=get_main_menu_keyboard(is_admin=is_admin))

    stmt = select(User.id).where(User.is_banned == False)
    result = await session.execute(stmt)
    user_ids = result.scalars().all()

    total = len(user_ids)
    sent = 0
    failed = 0

    for idx, uid in enumerate(user_ids):
        try:
            await message.copy_to(chat_id=uid)
            sent += 1
        except Exception:
            failed += 1

        # Periodic status update every 25 users
        if (idx + 1) % 25 == 0:
            try:
                await status_msg.edit_text(f"🚀 در حال ارسال: {sent}/{total} (خطا: {failed})")
            except Exception:
                pass
            await asyncio.sleep(1.0)

    await status_msg.edit_text(
        f"✅ **ارسال همگانی پایان یافت!**\n\n"
        f"👥 کل مخاطبان: {total}\n"
        f"✔️ ارسال موفق: {sent}\n"
        f"❌ ناموفق / بلاک شده: {failed}"
    )


# =============================================================================
# ⚙️ تنظیمات ربات (Settings)
# =============================================================================

@router.callback_query(F.data == "admin_settings")
async def callback_admin_settings(callback: CallbackQuery, is_admin: bool):
    """Display active environment settings overview."""
    if not is_admin:
        return

    text = (
        "⚙️ **تنظیمات فعلی ربات:**\n\n"
        f"💳 شماره کارت: `{settings.CARD_NUMBER}`\n"
        f"👤 به نام: **{settings.CARD_HOLDER}**\n"
        f"👨‍💻 آیدی پشتیبانی: {settings.SUPPORT_USERNAME}\n"
        f"📢 کانال عضویت اجباری: `{settings.REQUIRED_CHANNEL_ID or 'غیرفعال'}`\n"
        f"🎁 تست رایگان: `{'فعال' if settings.FREE_TRIAL_ENABLED else 'غیرفعال'}` ({settings.FREE_TRIAL_TRAFFIC_GB} GB / {settings.FREE_TRIAL_DURATION_DAYS} روز)\n"
        f"🤝 پورسانت رفرال: `{settings.REFERRAL_COMMISSION_PERCENT}٪`\n\n"
        "برای تغییر این مقادیر می‌توانید متغیرهای فایل `.env` را ویرایش فرمایید."
    )
    kb = get_admin_dashboard_keyboard()
    await callback.message.edit_text(text, reply_markup=kb)
    await callback.answer()
