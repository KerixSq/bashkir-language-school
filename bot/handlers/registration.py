from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.types import CallbackQuery, Message

from bot import db, keyboards, texts
from bot.common import guard, require_user
from scripts.pure import valid_nickname

router = Router()


async def show_pairs(message: Message) -> None:
    rows = await db.lang_pairs()
    if not rows:
        await message.answer(texts.NO_AVAILABLE_PAIRS)
        return
    await message.answer(texts.CHOOSE_PAIR, reply_markup=keyboards.pair_keyboard(rows))


async def continue_registration(message: Message, user: dict) -> None:
    if not user.get('nickname'):
        await db.update_user(user['id'], {'state': 'choosing_nickname'})
        await message.answer(texts.NICKNAME_PROMPT)
    elif (
        user.get('role')
        and (user.get('class_id') or user.get('role') == 'student')
        and user.get('lang_pair')
    ):
        if user.get('state') == 'awaiting_correction':
            await message.answer(texts.CORRECTION_REQUIRED)
            return
        await db.update_user(user['id'], {'state': 'idle'})
        await message.answer(
            texts.returned(user['nickname']), reply_markup=keyboards.main_menu(user['role'])
        )
    elif (
        user.get('role') == 'student'
        and user.get('state') == 'choosing_pair'
        or user.get('role')
        and user.get('class_id')
    ):
        await db.update_user(user['id'], {'state': 'choosing_pair'})
        await show_pairs(message)
    elif user.get('role'):
        await db.update_user(user['id'], {'state': 'joining_class'})
        await message.answer(
            texts.TEACHER_CODE if user['role'] == 'teacher' else texts.STUDENT_CODE,
            reply_markup=keyboards.study_mode() if user['role'] == 'student' else None,
        )
    else:
        await db.update_user(user['id'], {'state': 'choosing_role'})
        await message.answer(texts.WELCOME, reply_markup=keyboards.role_keyboard())


@router.message(CommandStart())
@guard
async def start(message: Message) -> None:
    if message.from_user is None:
        return
    user = await db.user_by_telegram(message.from_user.id)
    if user is None:
        user = await db.register_user(message.from_user.id)
    await continue_registration(message, user)


@router.message(Command('pair'))
@guard
async def change_pair(message: Message) -> None:
    user = await require_user(message)
    if not user:
        return
    if not all(user.get(field) for field in ('nickname', 'role')) or (
        user['role'] == 'teacher' and not user.get('class_id')
    ):
        await message.answer(texts.REGISTRATION_REQUIRED)
        return
    if user.get('state') == 'awaiting_correction':
        await message.answer(texts.CORRECTION_REQUIRED)
        return
    available = await db.lang_pairs()
    if not available:
        await message.answer(texts.NO_AVAILABLE_PAIRS)
        return
    await db.update_user(
        user['id'],
        {
            'state': 'choosing_pair',
            'current_fragment_pair_id': None,
            'current_shown_variant': None,
            'current_shown_at': None,
        },
    )
    await message.answer(texts.CHOOSE_PAIR, reply_markup=keyboards.pair_keyboard(available))


@router.callback_query(F.data.startswith('role:'))
@guard
async def choose_role(call: CallbackQuery) -> None:
    await call.answer()
    if not isinstance(call.message, Message):
        return
    user = await require_user(call)
    if user is None:
        return
    role = (call.data or '').partition(':')[2]
    if role not in ('student', 'teacher') or user['state'] != 'choosing_role':
        await call.message.answer(texts.ROLE_BUTTONS)
        return
    await db.update_user(user['id'], {'role': role, 'state': 'joining_class'})
    await call.message.answer(
        texts.TEACHER_CODE if role == 'teacher' else 'Как ты хочешь учиться?',
        reply_markup=keyboards.study_mode() if role == 'student' else None,
    )


@router.callback_query(F.data.startswith('study:'))
@guard
async def study_choice(call: CallbackQuery) -> None:
    await call.answer()
    if not isinstance(call.message, Message):
        return
    user = await require_user(call)
    if not user or user.get('role') != 'student' or user['state'] != 'joining_class':
        return
    if call.data == 'study:solo' and not user.get('class_id'):
        await db.update_user(user['id'], {'state': 'choosing_pair'})
        await show_pairs(call.message)
    elif call.data == 'study:class':
        await call.message.answer(texts.STUDENT_CODE)


@router.message(Command('join'))
@guard
async def join_class(message: Message) -> None:
    user = await require_user(message)
    if not user:
        return
    if user.get('role') != 'student' or not user.get('nickname'):
        await message.answer(texts.REGISTRATION_REQUIRED)
        return
    if user['state'] == 'awaiting_correction':
        await message.answer(texts.CORRECTION_REQUIRED)
        return
    await db.update_user(
        user['id'],
        {
            'state': 'joining_class',
            'current_fragment_pair_id': None,
            'current_shown_variant': None,
            'current_shown_at': None,
        },
    )
    await message.answer(texts.STUDENT_CODE)


@router.callback_query(F.data.startswith('pair:'))
@guard
async def choose_pair(call: CallbackQuery) -> None:
    await call.answer()
    if not isinstance(call.message, Message):
        return
    user = await require_user(call)
    if user is None:
        return
    if user['state'] != 'choosing_pair':
        await call.message.answer(texts.REGISTRATION_REQUIRED)
        return
    selected = (call.data or '').partition(':')[2]
    pairs = await db.lang_pairs()
    if selected not in {row['code'] for row in pairs}:
        await call.message.answer(texts.UNKNOWN_PAIR)
        return
    await db.update_user(user['id'], {'lang_pair': selected, 'state': 'idle'})
    await call.message.answer(
        texts.registered(user['nickname']), reply_markup=keyboards.main_menu(user['role'])
    )


async def register_text(message: Message, user: dict, value: str) -> bool:
    state = user['state']
    if state == 'choosing_nickname':
        if not valid_nickname(value):
            await message.answer(texts.INVALID_NICKNAME)
            return True
        await db.update_user(user['id'], {'nickname': value})
        await continue_registration(message, {**user, 'nickname': value})
        return True
    if state == 'joining_class':
        is_teacher = user['role'] == 'teacher'
        column = 'teacher_code' if is_teacher else 'join_code'
        code = value if is_teacher else value.upper()
        if not code or len(code) > 128:
            await message.answer(texts.TEACHER_CODE if is_teacher else texts.STUDENT_CODE)
            return True
        room = await db.class_for_code(column, code)
        if room is None:
            await message.answer(texts.UNKNOWN_CODE)
            return True
        await db.update_user(user['id'], {'class_id': room['id'], 'state': 'choosing_pair'})
        await show_pairs(message)
        return True
    if state == 'choosing_role':
        await message.answer(texts.ROLE_BUTTONS)
        return True
    if state == 'choosing_pair':
        await show_pairs(message)
        return True
    return False
