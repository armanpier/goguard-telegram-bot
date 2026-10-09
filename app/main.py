import asyncio
import logging
import sys
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand

from app.config import settings
from app.database.session import init_db
from app.services.goguard import GoGuardClient
from app.bot.middlewares import setup_middlewares
from app.bot.handlers import setup_routers

# Setup logging
logging.basicConfig(
    level=logging.DEBUG if settings.DEBUG else logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger("goguard_bot")


async def set_default_commands(bot: Bot) -> None:
    """Register standard commands in Telegram menu."""
    commands = [
        BotCommand(command="start", description="🚀 شروع و منوی اصلی"),
        BotCommand(command="help", description="💡 راهنما و توضیحات"),
        BotCommand(command="admin", description="⚙️ پنل مدیریت (مخصوص ادمین‌ها)"),
    ]
    try:
        await bot.set_my_commands(commands)
    except Exception as exc:
        logger.warning(f"Failed to set bot commands: {exc}")


async def main() -> None:
    """Main application entry point."""
    logger.info("Initializing GoGuard Telegram Bot...")

    # 1. Initialize Database
    try:
        await init_db()
        logger.info("Database initialized successfully.")
    except Exception as exc:
        logger.critical(f"Database initialization failed: {exc}")
        sys.exit(1)

    # 2. Initialize GoGuard Panel API Client
    goguard_client = GoGuardClient(
        base_url=settings.GOGUARD_BASE_URL,
        username=settings.GOGUARD_USERNAME,
        password=settings.GOGUARD_PASSWORD,
        sub_url_template=settings.GOGUARD_SUB_URL_TEMPLATE,
        timeout=settings.GOGUARD_TIMEOUT_SECONDS,
    )

    # Health check GoGuard Panel connection asynchronously
    asyncio.create_task(check_panel_health(goguard_client))

    # 3. Initialize Bot & Dispatcher
    bot = Bot(
        token=settings.BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.MARKDOWN),
    )
    storage = MemoryStorage()
    dp = Dispatcher(storage=storage)

    # Pass goguard client to all handlers
    dp["goguard"] = goguard_client

    # 4. Setup Middlewares & Routers
    setup_middlewares(dp)
    setup_routers(dp)

    # 5. Set Bot Commands
    await set_default_commands(bot)

    bot_info = await bot.get_me()
    logger.info(f"Bot @{bot_info.username} (ID: {bot_info.id}) started polling.")

    # 6. Start Polling with clean shutdown
    try:
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        logger.info("Shutting down bot...")
        await goguard_client.close()
        await bot.session.close()
        logger.info("Clean shutdown completed.")


async def check_panel_health(client: GoGuardClient) -> None:
    """Background check for GoGuard Panel API connection on startup."""
    await asyncio.sleep(1.0)
    try:
        is_alive = await client.health_check()
        if is_alive:
            logger.info("GoGuard Panel API connectivity check: OK (200 Authenticated)")
        else:
            logger.warning("GoGuard Panel API connection check failed.")
    except Exception as exc:
        logger.warning(f"Could not connect to GoGuard Panel API on startup: {exc}")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Process interrupted. Exiting.")
