from typing import List
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from app.database.models import Plan


def get_admin_dashboard_keyboard() -> InlineKeyboardMarkup:
    """Main keyboard for admin panel."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📊 آمار و گزارشات", callback_data="admin_stats"),
            InlineKeyboardButton(text="💳 رسیدهای در انتظار", callback_data="admin_receipts"),
        ],
        [
            InlineKeyboardButton(text="📦 مدیریت پلن‌ها", callback_data="admin_plans"),
            InlineKeyboardButton(text="👥 مدیریت کاربران", callback_data="admin_users"),
        ],
        [
            InlineKeyboardButton(text="📢 ارسال پیام همگانی", callback_data="admin_broadcast"),
            InlineKeyboardButton(text="🌐 وضعیت اتصال GoGuard", callback_data="admin_goguard_status"),
        ],
        [
            InlineKeyboardButton(text="👑 مدیریت ادمین‌ها", callback_data="admin_manage_admins"),
            InlineKeyboardButton(text="⚙️ تنظیمات ربات", callback_data="admin_settings"),
        ]
    ])


def get_admins_management_keyboard(admin_details: list, current_user_id: int) -> InlineKeyboardMarkup:
    """Keyboard for managing bot administrators."""
    buttons = [
        [InlineKeyboardButton(text="➕ افزودن ادمین جدید", callback_data="admin_add_admin")]
    ]
    for admin in admin_details:
        aid = admin["id"]
        is_self = (aid == current_user_id)
        name = admin.get("full_name") or str(aid)
        if admin.get("username"):
            label = f"👤 {name} (@{admin['username']})"
        else:
            label = f"👤 {name} ({aid})"
        if is_self:
            label += " (شما)"

        row = [InlineKeyboardButton(text=label, callback_data=f"admin_info_admin:{aid}")]
        if len(admin_details) > 1:
            del_text = "🗑 خروج خود" if is_self else "🗑 حذف"
            row.append(InlineKeyboardButton(text=del_text, callback_data=f"admin_del_admin:{aid}"))
        buttons.append(row)

    buttons.append([InlineKeyboardButton(text="🔙 بازگشت به پنل مدیریت", callback_data="admin_back_home")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_cancel_admin_action_keyboard() -> InlineKeyboardMarkup:
    """Cancel button returning to admins list."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ انصراف و بازگشت", callback_data="admin_manage_admins")]
    ])



def get_receipt_review_keyboard(receipt_id: int) -> InlineKeyboardMarkup:
    """Inline buttons to approve or reject a payment receipt."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ تایید و فعال‌سازی", callback_data=f"adm_appr_rec:{receipt_id}"),
            InlineKeyboardButton(text="❌ رد پرداخت", callback_data=f"adm_rej_rec:{receipt_id}"),
        ]
    ])


def get_plans_management_keyboard(plans: List[Plan]) -> InlineKeyboardMarkup:
    """Plans management menu."""
    buttons = [
        [InlineKeyboardButton(text="➕ افزودن پلن جدید", callback_data="admin_add_plan")]
    ]
    for plan in plans:
        status_icon = "🟢" if plan.is_active else "🔴"
        buttons.append([
            InlineKeyboardButton(
                text=f"{status_icon} {plan.title}",
                callback_data=f"admin_manage_plan:{plan.id}"
            )
        ])
    buttons.append([InlineKeyboardButton(text="🔙 بازگشت به پنل مدیریت", callback_data="admin_back_home")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_single_plan_manage_keyboard(plan_id: int, is_active: bool) -> InlineKeyboardMarkup:
    """Manage single plan: toggle active, delete, back."""
    toggle_text = "🔴 غیرفعال‌سازی پلن" if is_active else "🟢 فعال‌سازی پلن"
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text=toggle_text, callback_data=f"admin_toggle_plan:{plan_id}"),
            InlineKeyboardButton(text="🗑 حذف پلن", callback_data=f"admin_delete_plan:{plan_id}"),
        ],
        [
            InlineKeyboardButton(text="🔙 بازگشت به لیست پلن‌ها", callback_data="admin_plans")
        ]
    ])


def get_broadcast_confirm_keyboard() -> InlineKeyboardMarkup:
    """Confirmation before broadcasting message."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🚀 بله، ارسال به همه", callback_data="confirm_broadcast"),
            InlineKeyboardButton(text="❌ لغو", callback_data="cancel_broadcast"),
        ]
    ])
