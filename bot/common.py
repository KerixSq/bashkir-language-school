import asyncio
import functools
import logging
import re

from aiogram.types import CallbackQuery, Message

from bot import db, texts

log = logging.getLogger('bashkir-bot')
_locks: dict[int, asyncio.Lock] = {}


def clean_text(raw: str | None, limit: int = 500) -> str:
    return re.sub(r'[\x00-\x1f\x7f-\x9f]', ' ', raw or '').strip()[:limit].strip()


def answer_lock(telegram_id: int) -> asyncio.Lock:
    return _locks.setdefault(telegram_id, asyncio.Lock())


async def reply_error(event, exception: Exception) -> None:
    log.error('Ошибка обработчика: %s', type(exception).__name__)
    detail = str(exception)
    text = next(
        (message for clue, message in texts.KNOWN_ERRORS.items() if clue in detail),
        texts.DATABASE_ERROR,
    )
    try:
        if isinstance(event, CallbackQuery):
            if isinstance(event.message, Message):
                await event.message.answer(text)
            else:
                await event.answer(text, show_alert=True)
        else:
            await event.answer(text)
    except Exception:
        log.warning('Не получилось сообщить об ошибке')


def guard(func):
    @functools.wraps(func)
    async def wrapper(event, *args, **kwargs):
        try:
            return await func(event, *args, **kwargs)
        except Exception as error:
            await reply_error(event, error)

    return wrapper


async def require_user(event) -> dict | None:
    sender = event.from_user
    if sender is None:
        return None
    user = await db.user_by_telegram(sender.id)
    if user is None:
        if isinstance(event, CallbackQuery):
            await event.answer(texts.START_FIRST, show_alert=True)
        else:
            await event.answer(texts.START_FIRST)
    return user
