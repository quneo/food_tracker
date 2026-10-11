import asyncio
import logging

from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.enums import ParseMode
from aiogram.types import MenuButtonWebApp, WebAppInfo

from app import handlers
from app.api import backend
from app.config import settings
from app.delivery import outbox_loop

log = logging.getLogger(__name__)


async def main():
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    # Every outbox poll would be an INFO line otherwise.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    session = AiohttpSession(proxy=settings.telegram_proxy) if settings.telegram_proxy else None
    bot = Bot(
        settings.telegram_bot_token,
        session=session,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dispatcher = Dispatcher()
    dispatcher.message.filter(F.chat.type == "private")
    dispatcher.include_router(handlers.router)
    await bot.set_my_commands(handlers.COMMANDS)
    if settings.public_url and settings.public_url.startswith("https://"):
        # The menu button opens the diary inside Telegram, signed in automatically.
        await bot.set_chat_menu_button(
            menu_button=MenuButtonWebApp(
                text="Дневник", web_app=WebAppInfo(url=settings.public_url)
            )
        )
    delivery = asyncio.create_task(outbox_loop(bot, backend))
    try:
        await dispatcher.start_polling(bot, allowed_updates=["message", "callback_query"])
    finally:
        delivery.cancel()
        await backend.close()
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
