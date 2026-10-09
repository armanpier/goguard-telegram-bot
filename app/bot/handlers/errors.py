import logging
from aiogram import Router
from aiogram.types import ErrorEvent

logger = logging.getLogger(__name__)
router = Router(name="errors")


@router.error()
async def error_handler(event: ErrorEvent):
    """Global error handler for unexpected bot exceptions."""
    logger.exception(f"Unhandled exception occurred while processing update: {event.exception}")

    # Optionally notify user if message context is available
    if event.update.message:
        try:
            await event.update.message.answer(
                "⚠️ متاسفانه خطایی در پردازش درخواست شما رخ داد. لطفاً لحظاتی بعد مجدداً تلاش نمایید."
            )
        except Exception:
            pass
    elif event.update.callback_query:
        try:
            await event.update.callback_query.answer(
                "خطایی در پردازش رخ داد. لطفاً دوباره امتحان کنید.",
                show_alert=True
            )
        except Exception:
            pass
