from aiogram import Dispatcher
from app.bot.handlers.start import router as start_router
from app.bot.handlers.user import router as user_router
from app.bot.handlers.payment import router as payment_router
from app.bot.handlers.admin import router as admin_router
from app.bot.handlers.errors import router as errors_router


def setup_routers(dp: Dispatcher) -> None:
    """Register all bot routers in proper priority order."""
    dp.include_router(errors_router)
    dp.include_router(start_router)
    dp.include_router(admin_router)
    dp.include_router(payment_router)
    dp.include_router(user_router)
