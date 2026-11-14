import os
import secrets
from datetime import datetime, timezone
from html import escape

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from bot import db, keyboards, texts
from bot.common import clean_text, guard, require_user
from bot.links import public_web_url

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


@router.callback_query(F.data.startswith('menu:'))
@guard
async def menu_click(call: CallbackQuery) -> None:
    await call.answer()
    if not isinstance(call.message, Message):
        return
    user = await require_user(call)
    if not user:
        return
    # Callback messages were authored by the bot; preserve the actual human identity.
    message = call.message.model_copy(update={'from_user': call.from_user})
    from bot.handlers import profile, registration, tasks

    action = (call.data or '').partition(':')[2]
    actions = {
        'task': tasks.task_command,
        'progress': profile.me,
        'ratings': top,
        'report': profile.report,
        'pair': registration.change_pair,
        'join': registration.join_class,
        'privacy': privacy,
        'help': profile.help_command,
    }
    if action in actions:
        await actions[action](message)
    elif action == 'home':
        await message.answer(
            'Выбери следующий шаг.', reply_markup=keyboards.main_menu(user.get('role'))
        )
    elif action == 'settings':
        await message.answer(
            'Настройки обучения',
            reply_markup=keyboards.build_keyboard(
                [
                    [('Языковая пара', 'menu:pair'), ('Вступить в класс', 'menu:join')],
                    [('Приватность', 'menu:privacy'), ('Помощь', 'menu:help')],
                    [('Меню', 'menu:home')],
                ]
            ),
        )
    elif action in ('contribution', 'history'):
        await contribution(message, user, history=action == 'history')
    elif action == 'web':
        url = public_web_url(os.getenv('PUBLIC_WEB_URL', ''))
        if not url:
            await message.answer(
                'Публичный адрес сайта не настроен. Локальную платформу можно открыть только на ноутбуке организатора. Задания и вклад доступны здесь в Telegram.',
                reply_markup=keyboards.main_menu(user.get('role')),
            )
        else:
            await message.answer(
                'Сайт использует общую библиотеку и серверные рейтинги. Веб-профиль и Telegram-профиль пока независимы. Тренировочные XP игры хранятся отдельно.',
                reply_markup=InlineKeyboardMarkup(
                    inline_keyboard=[
                        [InlineKeyboardButton(text='Веб-платформа', url=url)],
                        [InlineKeyboardButton(text='Игра с Акбузатом', url=url + '#game-zone')],
                        [
                            InlineKeyboardButton(
                                text='Библиотека переводов', url=url + '#translations'
                            )
                        ],
                    ]
                ),
            )


async def contribution(message: Message, user: dict, history: bool = False) -> None:
    # User ID is resolved only from the authenticated Telegram sender, never callback data.
    counts, rows = await db.contribution_summary(user['id'])
    labels = {
        'collecting': 'Собираем голоса',
        'confirmed': 'Подтверждено сообществом',
        'expert_review': 'Направлено эксперту',
    }
    stats = await db.user_stats(user['id'])
    badges = await db.user_badges(user['id'])
    lines = [
        f'Проверок: {int(stats.get("total_answers") or 0)} · исправлений: {int(stats.get("corrections") or 0)}',
        f'Сегодня: {int(stats.get("day_answers") or 0)} · очки: {user["points"]} · уровень: {user["level"]}',
    ]
    lines.extend(f'{label}: {counts[key]}' for key, label in labels.items())
    lines.append('Достижения: ' + (', '.join(escape(badge) for badge in badges) or 'пока нет'))
    if user.get('lang_pair'):
        progress = await db.select('adventure_progress', lang_pair=user['lang_pair'])
        if progress:
            row = progress[0]
            total = sum(
                int(row.get(key) or 0) for key in ('confirmed', 'collecting', 'expert_review')
            )
            lines.append(
                f'Библиотека: {row.get("confirmed", 0)} подтверждено сообществом из {total}'
            )
    if history:
        lines.append('Последние проверки:')
        lines.extend(
            f'{str(row["created_at"])[:10]} — {labels.get((row.get("fragment_pairs") or {}).get("status"), "Статус недоступен")}'
            for row in sorted(rows, key=lambda r: r['created_at'], reverse=True)[:20]
        )
    await message.answer(
        '\n'.join(lines),
        reply_markup=keyboards.build_keyboard(
            [[('История моих проверок', 'menu:history'), ('Меню', 'menu:home')]]
        ),
    )
