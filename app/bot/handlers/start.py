import logging
from aiogram import Router, F
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.config import settings
from app.database.models import User
from app.bot.keyboards.default import get_main_menu_keyboard
from app.bot.utils.texts import get_welcome_text

logger = logging.getLogger(__name__)
router = Router(name="start")


@router.message(CommandStart())
async def handle_start(message: Message, state: FSMContext, session: AsyncSession, db_user: User, is_admin: bool):
    """Handle /start command, optionally with referral parameter."""
    await state.clear()

    # Check for referral payload in start command, e.g. /start ref_123456
    text_parts = message.text.split(maxsplit=1)
    if len(text_parts) > 1 and text_parts[1].startswith("ref_"):
        try:
            ref_id = int(text_parts[1].replace("ref_", "").strip())
            # Don't refer oneself and only set if user doesn't already have a referrer
            if ref_id != db_user.id and db_user.referrer_id is None:
                # Check if referrer exists
                ref_res = await session.execute(select(User).where(User.id == ref_id))
                referrer = ref_res.scalar_one_or_none()
                if referrer:
                    db_user.referrer_id = ref_id
                    await session.commit()
                    logger.info(f"User {db_user.id} set referrer to {ref_id}")
        except Exception as exc:
            logger.warning(f"Error parsing referral code: {exc}")

    kb = get_main_menu_keyboard(is_admin=is_admin)
    welcome_text = get_welcome_text(
        user_name=message.from_user.full_name or "کاربر",
        user_id=message.from_user.id,
        balance=db_user.balance,
    )
    await message.answer(welcome_text, reply_markup=kb)


@router.message(Command("help"))
async def handle_help(message: Message, is_admin: bool):
    """Handle /help command."""
    kb = get_main_menu_keyboard(is_admin=is_admin)
    help_text = (
        "💡 **راهنمای استفاده از ربات**\n\n"
        "• 🛒 **خرید اشتراک:** مشاهده و خرید پلن‌های متنوع با سرعت بالا\n"
        "• 👤 **سرویس‌های من:** مشاهده ترافیک مصرفی، تاریخ انقضا و دریافت لینک و QR Code\n"
        "• 💳 **افزایش موجودی:** شارژ کیف پول جهت خرید سریع\n"
        "• 🎁 **تست رایگان:** دریافت اشتراک تست ۲۴ ساعته رایگان\n"
        "• 🤝 **همکاری در فروش:** دریافت لینک دعوت و کسب درآمد از خریدهای دوستان\n"
        "• 📚 **راهنمای اتصال:** آموزش کار با نرم‌افزارهای مختلف در تمامی سیستم‌عامل‌ها\n"
        "• 📞 **پشتیبانی:** ارتباط با تیم پشتیبانی فنی"
    )
    await message.answer(help_text, reply_markup=kb)


@router.message(F.text.in_(["بازگشت", "🔙 بازگشت", "❌ انصراف و بازگشت", "انصراف", "back", "Back"]))
async def handle_cancel(message: Message, state: FSMContext, is_admin: bool):
    """Cancel any active FSM state and return to main menu."""
    await state.clear()
    kb = get_main_menu_keyboard(is_admin=is_admin)
    await message.answer("به منوی اصلی بازگشتید.", reply_markup=kb)


@router.callback_query(F.data == "check_channel_join")
async def handle_check_channel_join(callback: CallbackQuery, is_admin: bool):
    """Verify channel membership after force join prompt."""
    if not settings.REQUIRED_CHANNEL_ID:
        await callback.message.delete()
        await callback.answer("عضویت تایید شد ✅")
        return

    try:
        member = await callback.bot.get_chat_member(
            chat_id=settings.REQUIRED_CHANNEL_ID,
            user_id=callback.from_user.id,
        )
        if member.status not in ["left", "kicked"]:
            await callback.message.delete()
            kb = get_main_menu_keyboard(is_admin=is_admin)
            await callback.message.answer("عضویت شما با موفقیت تایید شد! به ربات خوش آمدید.", reply_markup=kb)
            await callback.answer("تایید شد ✅")
        else:
            await callback.answer("شما هنوز در کانال عضو نشده‌اید!", show_alert=True)
    except Exception as exc:
        logger.error(f"Error checking membership: {exc}")
        await callback.answer("خطا در بررسی عضویت. لطفاً لحظاتی دیگر تلاش کنید.", show_alert=True)
