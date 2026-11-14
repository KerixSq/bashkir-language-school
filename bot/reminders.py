"""One daily attempt per consenting user; database claims survive process restarts."""

import asyncio
import logging

from aiogram.exceptions import TelegramForbiddenError

from bot import keyboards

log = logging.getLogger('bashkir-bot')


async def run_once(bot, now=None, database=None):
    if database is None:
        from bot import db as database
    params = {'p_limit': 20}
    if now is not None:
        if now.tzinfo is None:
            raise ValueError('Reminder clock must be timezone-aware')
        params['p_now'] = now.isoformat()
    # Production uses PostgreSQL's clock, matching user_stats and the daily goal.
    rows = await database.rpc('claim_daily_reminders', params)
    rows = [rows] if isinstance(rows, dict) else (rows or [])
    for row in rows:
        # Consent/deletion/goal can change after the atomic claim. Recheck before transport.
        stats = await database.user_stats(row['user_id'])
        if int(stats.get('day_answers') or 0) >= await database.daily_goal():
            continue
        users = await database.select(
            'users', 'telegram_id,reminders_enabled,deleted_at', id=row['user_id']
        )
        if (
            not users
            or not users[0]['reminders_enabled']
            or users[0]['deleted_at']
            or users[0]['telegram_id'] != row['telegram_id']
        ):
            continue
        try:
            await bot.send_message(
                row['telegram_id'],
                'Время для короткой практики. Проверь перевод и помоги пополнить общую библиотеку. Отключить: /remind off.',
                reply_markup=keyboards.build_keyboard(
                    [[('Задание дня', 'menu:task'), ('Настройки', 'menu:reminders')]]
                ),
            )
        except TelegramForbiddenError:
            await database.update_user(row['user_id'], {'reminders_enabled': False})
        except Exception as error:
            # Keep the claim: a timeout may mean the message was already delivered.
            log.warning('Reminder attempt failed: %s', type(error).__name__)


async def reminder_loop(bot):
    while True:
        try:
            await run_once(bot)
        except Exception as error:
            log.warning('Reminder batch failed: %s', type(error).__name__)
        await asyncio.sleep(60)
