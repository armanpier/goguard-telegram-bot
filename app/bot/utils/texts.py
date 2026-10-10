from typing import Optional
from app.config import settings
from app.bot.utils.formatters import format_price, format_timestamp, remaining_time_human, bytes_to_human, progress_bar


def get_welcome_text(user_name: str, user_id: int, balance: int) -> str:
    return (
        f"سلام **{user_name}** عزیز، به ربات خرید اشتراک پرسرعت و پایدار خوش آمدید! 🚀\n\n"
        f"🆔 شناسه کاربری: `{user_id}`\n"
        f"💰 موجودی کیف پول: **{format_price(balance, settings.CURRENCY_TITLE)}**\n\n"
        "برای شروع یکی از گزینه‌های زیر را انتخاب نمایید 👇"
    )


def get_force_join_text(channel_id: str) -> str:
    if channel_id.startswith("@"):
        clean_channel = channel_id.lstrip("@")
        escaped_channel = channel_id.replace("_", "\\_").replace("*", "\\*").replace("`", "\\`")
        channel_display = f"[{escaped_channel}](https://t.me/{clean_channel})"
    else:
        channel_display = f"`{channel_id}`"
    return (
        "⚠️ **عضویت اجباری در کانال**\n\n"
        "جهت استفاده از خدمات ربات، ابتدا باید در کانال اطلاع‌رسانی ما عضو شوید:\n"
        f"👉 {channel_display}\n\n"
        "پس از عضویت، روی دکمه «عضو شدم ✅» کلیک کنید."
    )


def get_plan_card_text(plan_title: str, traffic_gb: float, duration_days: int, price: int, description: Optional[str] = None) -> str:
    desc = f"\n📝 توضیحات: {description}" if description else ""
    return (
        f"📦 **{plan_title}**\n\n"
        f"📊 حجم ترافیک: **{traffic_gb:g} گیگابایت**\n"
        f"⏳ مدت اعتبار: **{duration_days} روز**\n"
        f"💵 قیمت: **{format_price(price, settings.CURRENCY_TITLE)}**\n"
        f"{desc}\n\n"
        "لطفاً روش پرداخت مورد نظر خود را انتخاب کنید:"
    )


def get_card_payment_instructions(amount: int, card_number: str, card_holder: str) -> str:
    return (
        "💳 **اطلاعات کارت جهت واریز**\n\n"
        f"مبلغ قابل پرداخت: **{format_price(amount, settings.CURRENCY_TITLE)}**\n\n"
        f"شماره کارت (برای کپی لمس کنید):\n"
        f"`{card_number}`\n\n"
        f"به نام: **{card_holder}**\n\n"
        "⚠️ **نکات مهم قبل از واریز:**\n"
        "1. لطفاً مبلغ دقیق را واریز نمایید.\n"
        "2. پس از واریز، **تصویر رسید (اسکرین‌شات واضح فیش واریزی)** را به صورت عکس برای همین ربات ارسال کنید.\n"
        "3. رسید شما به صورت خودکار برای مدیریت ارسال شده و پس از تایید، کانفیگ تحویل داده می‌شود."
    )


def get_receipt_pending_text(receipt_id: int) -> str:
    return (
        f"✅ **رسید شما با شناسه #{receipt_id} با موفقیت ثبت شد.**\n\n"
        "درخواست شما در صف بررسی مدیریت قرار گرفت. "
        "به محض تایید، اشتراک به همراه لینک و کیو‌آرکد (QR Code) به صورت خودکار برای شما ارسال خواهد شد. ⏳"
    )


def get_receipt_admin_alert_text(
    receipt_id: int,
    user_id: int,
    user_name: str,
    username: Optional[str],
    amount: int,
    payment_type: str,
    plan_title: Optional[str] = None,
) -> str:
    user_handle = f"@{username}" if username else "ندارد"
    type_str = f"خرید پلن: {plan_title}" if payment_type == "plan_purchase" else "افزایش موجودی کیف پول"
    return (
        f"🔔 **رسید پرداخت جدید #{receipt_id}**\n\n"
        f"👤 کاربر: {user_name} ({user_handle})\n"
        f"🆔 شناسه کاربر: `{user_id}`\n"
        f"💵 مبلغ: **{format_price(amount, settings.CURRENCY_TITLE)}**\n"
        f"🎯 نوع تراکنش: **{type_str}**\n\n"
        "تصویر رسید در بالا قابل مشاهده است. لطفاً وضعیت را تعیین کنید:"
    )


def get_subscription_delivered_text(
    sub_title: str,
    traffic_gb: float,
    expire_epoch: int,
    sub_url: str,
    is_trial: bool = False,
) -> str:
    clean_url = str(sub_url).strip().strip("`'\"")
    header = "🎁 *سرویس تست رایگان شما فعال شد!*" if is_trial else f"🎉 *اشتراک شما ({sub_title}) با موفقیت فعال شد!*"
    expire_str = format_timestamp(expire_epoch)
    remaining_str = remaining_time_human(expire_epoch)

    return (
        f"{header}\n\n"
        f"📊 حجم کل: *{traffic_gb:g} گیگابایت*\n"
        f"📅 تاریخ انقضا: *{expire_str}* ({remaining_str})\n\n"
        f"🔗 *لینک اشتراک شما (برای کپی روی متن لمس کنید):*\n"
        f"```\n{clean_url}\n```\n\n"
        "📱 تصویر QR Code نیز در بالا برای اسکن سریع پیوست شده است.\n\n"
        "💡 *نحوه استفاده:*\n"
        "لینک فوق را کپی کرده و در برنامه‌های V2RayNG (اندروید)، FoXray / Streisand (آیفون) یا v2rayN (ویندوز) از طریق دکمه + (Add from Clipboard) وارد کنید."
    )


def get_subscription_status_text(
    username: str,
    used_bytes: int,
    total_bytes: int,
    expire_epoch: int,
    status: str,
    sub_url: str,
) -> str:
    clean_url = str(sub_url).strip().strip("`'\"")
    used_human = bytes_to_human(used_bytes)
    total_human = bytes_to_human(total_bytes)
    remaining_bytes = max(total_bytes - used_bytes, 0)
    remaining_human = bytes_to_human(remaining_bytes)

    used_gb = used_bytes / (1024 ** 3)
    total_gb = total_bytes / (1024 ** 3)
    bar = progress_bar(used_gb, total_gb)

    expire_str = format_timestamp(expire_epoch)
    remaining_time = remaining_time_human(expire_epoch)

    status_icon = "🟢 فعال" if status == "active" else "🔴 غیرفعال"

    return (
        f"👤 *جزئیات سرویس: {username}*\n\n"
        f"وضعیت: {status_icon}\n"
        f"📊 ترافیک مصرفی: *{used_human}* از *{total_human}*\n"
        f"📦 ترافیک باقی‌مانده: *{remaining_human}*\n"
        f"{bar}\n\n"
        f"⏳ انقضا: *{expire_str}*\n"
        f"⏱ زمان باقی‌مانده: *{remaining_time}*\n\n"
        f"🔗 *لینک اشتراک:*\n```\n{clean_url}\n```"
    )


def get_tutorials_text() -> str:
    return (
        "📚 **راهنمای اتصال و دانلود نرم‌افزارها**\n\n"
        "🔹 **اندروید (Android):**\n"
        "• نرم‌افزار پیشنهادی: **v2rayNG** یا **Happ**\n"
        "• دانلود از گوگل پلی: [Google Play](https://play.google.com/store/apps/details?id=com.v2ray.ang)\n"
        "• نحوه اتصال: لینک اشتراک را کپی کنید -> علامت + را بزنید -> گزینه Import config from Clipboard را انتخاب کنید.\n\n"
        "🔹 **آیفون و آیپد (iOS):**\n"
        "• نرم‌افزار پیشنهادی: **Streisand**، **FoXray** یا **V2Box**\n"
        "• دانلود از اپ استور: [App Store](https://apps.apple.com/app/streisand/id6450534064)\n"
        "• نحوه اتصال: لینک را در بخش Add Subscription یا + پیست کرده و اتصال را برقرار کنید.\n\n"
        "🔹 **ویندوز (Windows):**\n"
        "• نرم‌افزار پیشنهادی: **v2rayN** یا **Nekoray**\n"
        "• لینک اشتراک را در منوی Subscription Group اضافه کنید.\n\n"
        "در صورت بروز هرگونه مشکل با بخش پشتیبانی در ارتباط باشید."
    )


def get_referral_text(user_id: int, invited_count: int, total_earned: int, bot_username: str) -> str:
    ref_link = f"https://t.me/{bot_username}?start=ref_{user_id}"
    return (
        "🤝 **همکاری در فروش و دعوت از دوستان**\n\n"
        f"با دعوت از دوستان خود، **{settings.REFERRAL_COMMISSION_PERCENT}٪** از هر خرید آنها به عنوان پاداش به کیف پول شما اضافه می‌شود!\n\n"
        f"👥 تعداد دعوت‌شده‌ها: **{invited_count} نفر**\n"
        f"💰 مجموع درآمد کسب شده: **{format_price(total_earned, settings.CURRENCY_TITLE)}**\n\n"
        "🔗 **لینک دعوت اختصاصی شما:**\n"
        f"`{ref_link}`\n\n"
        "این لینک را برای دوستان خود بفرستید تا پس از اولین خرید آنها، پورسانت به صورت آنی دریافت کنید."
    )


def get_support_text() -> str:
    clean_username = settings.SUPPORT_USERNAME.lstrip("@")
    escaped_username = settings.SUPPORT_USERNAME.replace("_", "\\_").replace("*", "\\*").replace("`", "\\`")
    return (
        "📞 **ارتباط با واحد پشتیبانی**\n\n"
        "در صورت داشتن هرگونه سوال، مشکل در اتصال یا پیگیری پرداخت، می‌توانید با آیدی پشتیبانی در ارتباط باشید:\n\n"
        f"👨‍💻 پشتیبانی تلگرام: `{settings.SUPPORT_USERNAME}`\n"
        f"🔗 لینک مستقیم: [{escaped_username}](https://t.me/{clean_username})\n\n"
        "ساعات پاسخگویی: ۹ صبح الی ۲۴ شب"
    )
