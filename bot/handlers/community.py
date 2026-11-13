import secrets
from datetime import datetime, timezone

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from bot import db, keyboards, texts
from bot.common import clean_text, guard, require_user

router = Router()


async def show_top(message: Message, period: str, user: dict | None) -> None:
    rows = await db.top_users(period)
    extra = await db.rank_summary(user) if user else None
    await message.answer(
        texts.leaderboard(rows, period, extra) if rows else texts.NO_RATING,
        reply_markup=keyboards.period_keyboard(),
    )


@router.message(Command('top'))
@guard
async def top(message: Message) -> None:
    user = await require_user(message)
    await show_top(message, 'day', user)


@router.callback_query(F.data.startswith('top:'))
@guard
async def change_period(call: CallbackQuery) -> None:
    await call.answer()
    if not isinstance(call.message, Message):
        return
    period = (call.data or '').split(':')[-1]
    if period not in ('day', 'week', 'month', 'year'):
        return
    user = await require_user(call)
    await show_top(call.message, period, user)


@router.message(Command('privacy'))
@guard
async def privacy(message: Message) -> None:
    await message.answer(texts.PRIVACY)


@router.message(Command('delete_me'))
@guard
async def delete_me(message: Message) -> None:
    user = await require_user(message)
    if user:
        await message.answer(texts.DELETE_CONFIRM, reply_markup=keyboards.delete_keyboard())


@router.callback_query(F.data.startswith('delete:'))
@guard
async def confirm_delete(call: CallbackQuery) -> None:
    await call.answer()
    if not isinstance(call.message, Message):
        return
    if call.data == 'delete:no':
        await call.message.answer(texts.DELETE_CANCELLED)
        return
    if call.data != 'delete:yes':
        return
    user = await require_user(call)
    if not user:
        return
    await db.update_user(
        user['id'],
        {
            'telegram_id': -(secrets.randbelow(8_000_000_000_000_000) + 1_000_000_000_000_000),
            'username': None,
            'display_name': None,
            'nickname': None,
            'role': None,
            'class_id': None,
            'lang_pair': None,
            'points': 0,
            'level': 1,
            'reminders_enabled': False,
            'state': 'idle',
            'current_fragment_pair_id': None,
            'current_shown_variant': None,
            'current_shown_at': None,
            'deleted_at': datetime.now(timezone.utc).isoformat(),
        },
    )
    await call.message.answer(texts.DELETED)


@router.message(Command('newclass'))
@guard
async def new_class(message: Message) -> None:
    user = await require_user(message)
    if not user:
        return
    if user.get('role') != 'teacher':
        await message.answer(texts.NO_REPORT_ACCESS)
        return
    argument = (message.text or '').partition(' ')[2]
    invite, separator, class_name = argument.partition('|')
    invite, class_name = clean_text(invite, 128), clean_text(class_name, 60)
    if not separator or not invite or not 2 <= len(class_name) <= 60:
        await message.answer(texts.NEWCLASS_USAGE)
        return
    data = await db.rpc(
        'create_teacher_class',
        {
            'p_user_id': user['id'],
            'p_invite': invite,
            'p_name': class_name,
        },
    )
    await message.answer(texts.new_class(data))
