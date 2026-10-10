import logging
from typing import Any, Awaitable, Callable, Dict, Optional
from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Message, CallbackQuery, User as TgUser
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database.models import User
from app.config import settings
from app.bot.keyboards.inline import get_force_join_keyboard
from app.bot.utils.texts import get_force_join_text
from app.services.settings_service import is_user_admin

logger = logging.getLogger(__name__)


class AuthAndUserMiddleware(BaseMiddleware):
    """
    Ensures user exists in database, synchronizes profile details,
    verifies ban status, and handles force channel membership checks.
    """

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        tg_user: Optional[TgUser] = None
        if isinstance(event, Message):
            tg_user = event.from_user
        elif isinstance(event, CallbackQuery):
            tg_user = event.from_user

        if not tg_user or tg_user.is_bot:
            return await handler(event, data)

        session: AsyncSession = data.get("session")
        if not session:
            return await handler(event, data)

        # Retrieve or create user
        stmt = select(User).where(User.id == tg_user.id)
        result = await session.execute(stmt)
        user = result.scalar_one_or_none()

        if not user:
            user = User(
                id=tg_user.id,
                username=tg_user.username,
                full_name=tg_user.full_name or "",
                balance=0,
                has_used_trial=False,
                is_banned=False,
                language=settings.DEFAULT_LANGUAGE,
            )
            session.add(user)
            await session.commit()
            logger.info(f"Registered new user: {tg_user.id} ({tg_user.full_name})")
        else:
            # Sync user profile if changed
            changed = False
            if user.username != tg_user.username:
                user.username = tg_user.username
                changed = True
            if user.full_name != (tg_user.full_name or ""):
                user.full_name = tg_user.full_name or ""
                changed = True
            if changed:
                await session.commit()

        # Check ban status
        if user.is_banned:
            if isinstance(event, Message):
                await event.answer("⛔️ دسترسی حساب کاربری شما به ربات مسدود شده است.")
            elif isinstance(event, CallbackQuery):
                await event.answer("⛔️ حساب شما مسدود است.", show_alert=True)
            return

        data["db_user"] = user
        data["is_admin"] = await is_user_admin(session, tg_user.id)

        # Optional force channel check for normal messages
        if settings.REQUIRED_CHANNEL_ID and not data["is_admin"]:
            # Bypass for check callback
            if isinstance(event, CallbackQuery) and event.data == "check_channel_join":
                return await handler(event, data)

            bot = data["bot"]
            try:
                chat_member = await bot.get_chat_member(
                    chat_id=settings.REQUIRED_CHANNEL_ID,
                    user_id=tg_user.id
                )
                if chat_member.status in ["left", "kicked"]:
                    text = get_force_join_text(settings.REQUIRED_CHANNEL_ID)
                    kb = get_force_join_keyboard(settings.REQUIRED_CHANNEL_ID)
                    if isinstance(event, Message):
                        await event.answer(text, reply_markup=kb)
                    elif isinstance(event, CallbackQuery):
                        await event.message.answer(text, reply_markup=kb)
                        await event.answer()
                    return
            except Exception as e:
                logger.warning(f"Error checking channel membership for {tg_user.id}: {e}")

        return await handler(event, data)
