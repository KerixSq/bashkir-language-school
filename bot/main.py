import asyncio
import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path

from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import BotCommand
from dotenv import load_dotenv

from bot.handlers import community, messages, profile, registration, tasks
from bot.live_probe import observe_polling

from aiogram.client.session.aiohttp import AiohttpSession

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / '.env')


def configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s %(levelname)s %(name)s %(message)s',
        handlers=[
            RotatingFileHandler(
                ROOT / 'bot' / 'bot.log', maxBytes=1_000_000, backupCount=3, encoding='utf-8'
            ),
            logging.StreamHandler(),
        ],
    )
    # HTTP request URLs can contain Telegram IDs and class-code filters.
    for name in ('httpx', 'httpcore', 'postgrest', 'supabase', 'aiogram.event'):
        logging.getLogger(name).setLevel(logging.WARNING)


def create_dispatcher() -> Dispatcher:
    dispatcher = Dispatcher()
    dispatcher.message.filter(F.chat.type == 'private')
    dispatcher.callback_query.filter(F.message.chat.type == 'private')
    dispatcher.include_routers(
        registration.router, tasks.router, profile.router, community.router, messages.router
    )
    return dispatcher


async def main() -> None:
    token = os.getenv('TELEGRAM_BOT_TOKEN', '').strip()
    if not token:
        raise SystemExit('Заполни TELEGRAM_BOT_TOKEN в .env')
    configure_logging()
    _bot_session = AiohttpSession(proxy=os.getenv("BOT_PROXY_URL") or None)
    bot = Bot(token, session=_bot_session, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dispatcher = create_dispatcher()
    try:
        await bot.set_my_commands(
            [
                BotCommand(command='start', description='Регистрация'),
                BotCommand(command='task', description='Проверить перевод'),
                BotCommand(command='pair', description='Выбрать языковую пару'),
                BotCommand(command='cancel', description='Отменить действие'),
                BotCommand(command='top', description='Рейтинг'),
                BotCommand(command='me', description='Мой профиль'),
                BotCommand(command='report', description='Отчёт преподавателя'),
                BotCommand(command='newclass', description='Создать класс'),
                BotCommand(command='privacy', description='Приватность'),
                BotCommand(command='delete_me', description='Удалить профиль'),
                BotCommand(command='help', description='Все команды'),
            ]
        )
        logging.getLogger('bashkir-bot').info('Запущен long polling')
        async with observe_polling(bot, dispatcher):
            await dispatcher.start_polling(bot)
    finally:
        await bot.session.close()


if __name__ == '__main__':
    print('Hello, World!')
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
