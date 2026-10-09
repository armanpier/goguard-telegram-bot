from aiogram import Dispatcher
from app.bot.middlewares.db import DbSessionMiddleware
from app.bot.middlewares.auth import AuthAndUserMiddleware
from app.bot.middlewares.throttling import ThrottlingMiddleware


def setup_middlewares(dp: Dispatcher) -> None:
    """Register all global middlewares."""
    # 1. Throttling anti-flood
    dp.message.middleware(ThrottlingMiddleware(rate_limit=0.5))
    dp.callback_query.middleware(ThrottlingMiddleware(rate_limit=0.5))

    # 2. Database session injection
    dp.message.middleware(DbSessionMiddleware())
    dp.callback_query.middleware(DbSessionMiddleware())

    # 3. User authentication & channel check
    dp.message.middleware(AuthAndUserMiddleware())
    dp.callback_query.middleware(AuthAndUserMiddleware())
