from typing import List
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from app.database.models import Plan, Subscription
from app.bot.utils.formatters import format_price
from app.config import settings


def get_plans_inline_keyboard(plans: List[Plan]) -> InlineKeyboardMarkup:
    """Generate inline keyboard for available plans."""
    buttons = []
    for plan in plans:
        btn_text = f"{plan.title} - {format_price(plan.price, settings.CURRENCY_TITLE)}"
        buttons.append([InlineKeyboardButton(text=btn_text, callback_data=f"select_plan:{plan.id}")])

    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_plan_payment_methods_keyboard(plan_id: int, user_balance: int, plan_price: int) -> InlineKeyboardMarkup:
    """Show payment options for selected plan."""
    buttons = []

    # Wallet option
    if user_balance >= plan_price:
        wallet_btn = InlineKeyboardButton(
            text=f"💳 پرداخت از موجودی ({format_price(user_balance, settings.CURRENCY_TITLE)})",
            callback_data=f"pay_wallet:{plan_id}"
        )
    else:
        wallet_btn = InlineKeyboardButton(
            text=f"💳 پرداخت با موجودی (کسری موجودی: {format_price(plan_price - user_balance, settings.CURRENCY_TITLE)})",
            callback_data="insufficient_balance"
        )
    buttons.append([wallet_btn])

    # Card-to-Card option
    buttons.append([
        InlineKeyboardButton(
            text="🏦 کارت به کارت (ارسال فیش واریزی)",
            callback_data=f"pay_card:{plan_id}"
        )
    ])

    # Back button
    buttons.append([
        InlineKeyboardButton(text="🔙 بازگشت به لیست پلن‌ها", callback_data="back_to_plans")
    ])

    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_my_subscriptions_keyboard(subs: List[Subscription]) -> InlineKeyboardMarkup:
    """List user's active subscriptions."""
    buttons = []
    for sub in subs:
        title = sub.plan.title if sub.plan else ("سرویس تست رایگان" if sub.is_trial else sub.goguard_username)
        buttons.append([
            InlineKeyboardButton(
                text=f"⚡️ {title} ({sub.goguard_username})",
                callback_data=f"view_sub:{sub.id}"
            )
        ])

    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_subscription_delivered_keyboard(sub_url: str) -> InlineKeyboardMarkup:
    """Action keyboard when subscription is first delivered."""
    clean_url = str(sub_url).strip().strip("`'\"")
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🌐 باز کردن پنل کاربری اشتراک", url=clean_url),
        ]
    ])


def get_subscription_actions_keyboard(sub_id: int, sub_url: str) -> InlineKeyboardMarkup:
    """Actions for a specific subscription."""
    clean_url = str(sub_url).strip().strip("`'\"")
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🌐 ورود به پنل کاربری اشتراک", url=clean_url),
        ],
        [
            InlineKeyboardButton(text="📱 دریافت QR Code", callback_data=f"sub_qr:{sub_id}"),
            InlineKeyboardButton(text="🔄 به‌روزرسانی وضعیت", callback_data=f"refresh_sub:{sub_id}"),
        ],
        [
            InlineKeyboardButton(text="🔄 تمدید این سرویس", callback_data=f"renew_sub:{sub_id}"),
        ],
        [
            InlineKeyboardButton(text="🔙 بازگشت به سرویس‌های من", callback_data="back_to_my_subs"),
        ]
    ])


def get_force_join_keyboard(channel_id: str) -> InlineKeyboardMarkup:
    """Force join channel keyboard."""
    clean_id = channel_id.lstrip("@")
    channel_url = f"https://t.me/{clean_id}"
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📢 عضویت در کانال", url=channel_url)],
        [InlineKeyboardButton(text="عضو شدم ✅", callback_data="check_channel_join")],
    ])


def get_topup_presets_keyboard() -> InlineKeyboardMarkup:
    """Preset amounts for wallet top-up."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="۵۰,۰۰۰ تومان", callback_data="topup_amt:50000"),
            InlineKeyboardButton(text="۱۰۰,۰۰۰ تومان", callback_data="topup_amt:100000"),
        ],
        [
            InlineKeyboardButton(text="۲۰۰,۰۰۰ تومان", callback_data="topup_amt:200000"),
            InlineKeyboardButton(text="۵۰۰,۰۰۰ تومان", callback_data="topup_amt:500000"),
        ],
        [
            InlineKeyboardButton(text="✏️ مبلغ دلخواه", callback_data="topup_custom"),
        ]
    ])
