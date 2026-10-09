from aiogram.types import ReplyKeyboardMarkup, KeyboardButton


def get_main_menu_keyboard(is_admin: bool = False) -> ReplyKeyboardMarkup:
    """Return standard Reply Keyboard for the user."""
    keyboard = [
        [
            KeyboardButton(text="🛒 خرید اشتراک"),
            KeyboardButton(text="👤 سرویس‌های من"),
        ],
        [
            KeyboardButton(text="💳 افزایش موجودی"),
            KeyboardButton(text="🎁 تست رایگان"),
        ],
        [
            KeyboardButton(text="🤝 همکاری در فروش"),
            KeyboardButton(text="📚 راهنمای اتصال"),
        ],
        [
            KeyboardButton(text="📞 پشتیبانی"),
        ]
    ]

    if is_admin:
        keyboard.append([KeyboardButton(text="⚙️ پنل مدیریت")])

    return ReplyKeyboardMarkup(
        keyboard=keyboard,
        resize_keyboard=True,
        one_time_keyboard=False,
    )


def get_cancel_keyboard() -> ReplyKeyboardMarkup:
    """Standard back button keyboard."""
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="بازگشت")]
        ],
        resize_keyboard=True,
    )


get_back_keyboard = get_cancel_keyboard  # Alias
