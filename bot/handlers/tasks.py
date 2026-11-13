from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from bot import db, keyboards, texts
from bot.common import answer_lock, guard, require_user

router = Router()


async def remove_buttons(call: CallbackQuery) -> None:
    if not isinstance(call.message, Message):
        return
    try:
        await call.message.edit_reply_markup(reply_markup=None)
    except Exception:
        # Кнопки могли исчезнуть в другом клиенте; ответ уже сохранён в БД.
        pass


async def show_task(message: Message, user: dict) -> None:
    task = await db.rpc('get_next_fragment', {'p_user_id': user['id']})
    if not task:
        await message.answer(texts.NO_TASKS)
        return
    stats = await db.user_stats(user['id'])
    goal = await db.daily_goal()
    await message.answer(
        texts.task(
            task['text_ba'],
            task['translation'],
            int(stats.get('day_answers') or 0),
            goal,
            task.get('source'),
            task.get('time_start'),
            task.get('time_end'),
        ),
        reply_markup=keyboards.task_keyboard(task['fragment_pair_id']),
    )


@router.message(Command('task'))
@guard
async def task_command(message: Message) -> None:
    user = await require_user(message)
    if user is None:
        return
    if not all(user.get(field) for field in ('nickname', 'role', 'class_id', 'lang_pair')):
        await message.answer(texts.REGISTRATION_REQUIRED)
        return
    if user['state'] == 'awaiting_correction':
        await message.answer(texts.CORRECTION_REQUIRED)
        return
    await show_task(message, user)


async def submit(
    message: Message,
    telegram_id: int,
    user: dict,
    fragment_id: str,
    action: str,
    correction: str | None = None,
) -> bool:
    async with answer_lock(telegram_id):
        prior = await db.select('answers', 'id', user_id=user['id'], fragment_pair_id=fragment_id)
        if prior:
            await message.answer(texts.TASK_DUPLICATE)
            return True
        answer = await db.rpc(
            'submit_answer',
            {
                'p_user_id': user['id'],
                'p_fragment_pair_id': fragment_id,
                'p_action': action,
                'p_text': correction,
            },
        )
    if answer.get('too_fast'):
        await message.answer(texts.result(answer))
        return False
    if answer.get('duplicate'):
        await message.answer(texts.TASK_DUPLICATE)
        return True
    await message.answer(texts.result(answer), reply_markup=keyboards.next_task_keyboard())
    return True


@router.callback_query(F.data.startswith('task:'))
@guard
async def task_click(call: CallbackQuery) -> None:
    await call.answer()
    if not isinstance(call.message, Message):
        return
    user = await require_user(call)
    if user is None:
        return
    parts = (call.data or '').split(':')
    if len(parts) != 3 or parts[1] not in ('confirm', 'correct', 'skip'):
        await call.message.answer(texts.BAD_ACTION)
        return
    action, fragment_id = parts[1], parts[2]
    if user['current_fragment_pair_id'] != fragment_id:
        prior = await db.select('answers', 'id', user_id=user['id'], fragment_pair_id=fragment_id)
        await call.message.answer(texts.TASK_DUPLICATE if prior else texts.TASK_STALE)
        return
    if action == 'skip':
        skipped = await db.rpc(
            'skip_fragment',
            {
                'p_user_id': user['id'],
                'p_fragment_pair_id': fragment_id,
            },
        )
        await remove_buttons(call)
        await call.message.answer(texts.TASK_SKIPPED if skipped else texts.TASK_STALE)
    elif action == 'correct':
        started = await db.rpc(
            'begin_correction',
            {
                'p_user_id': user['id'],
                'p_fragment_pair_id': fragment_id,
            },
        )
        await remove_buttons(call)
        await call.message.answer(texts.CORRECTION_PROMPT if started else texts.TASK_STALE)
    else:
        success = await submit(call.message, call.from_user.id, user, fragment_id, 'confirm')
        if success:
            await remove_buttons(call)


@router.callback_query(F.data == 'flow:next')
@guard
async def next_task_click(call: CallbackQuery) -> None:
    await call.answer()
    if not isinstance(call.message, Message):
        return
    user = await require_user(call)
    if user is None:
        return
    if not all(user.get(field) for field in ('nickname', 'role', 'class_id', 'lang_pair')):
        await call.message.answer(texts.REGISTRATION_REQUIRED)
        return
    if user['state'] == 'awaiting_correction':
        await call.message.answer(texts.CORRECTION_REQUIRED)
        return
    await show_task(call.message, user)
    await remove_buttons(call)


async def submit_correction(message: Message, user: dict, value: str) -> None:
    if not value:
        await message.answer(texts.CORRECTION_EMPTY)
        return
    if not user.get('current_fragment_pair_id'):
        await message.answer(texts.TASK_STALE)
        return
    await submit(
        message, message.from_user.id, user, user['current_fragment_pair_id'], 'correct', value
    )


@router.message(Command('cancel'))
@guard
async def cancel(message: Message) -> None:
    user = await require_user(message)
    if user:
        await db.update_user(
            user['id'],
            {
                'state': 'idle',
                'current_fragment_pair_id': None,
                'current_shown_variant': None,
                'current_shown_at': None,
            },
        )
    await message.answer(texts.CANCELLED)
