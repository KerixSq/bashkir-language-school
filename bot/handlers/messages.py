from aiogram import Router
from aiogram.types import Message

from bot import texts
from bot.common import clean_text, guard, require_user
from bot.handlers.registration import register_text
from bot.handlers.tasks import submit_correction

router = Router()


@router.message()
@guard
async def input_message(message: Message) -> None:
    user = await require_user(message)
    if user is None:
        return
    value = clean_text(message.text)
    if await register_text(message, user, value):
        return
    if user['state'] == 'awaiting_correction':
        await submit_correction(message, user, value)
        return
    await message.answer(texts.UNKNOWN_MESSAGE)
