import ast
import asyncio
import re
import unittest
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from aiogram.exceptions import TelegramForbiddenError
from aiogram.methods import SendMessage

from bot.reminders import reminder_loop, run_once


class ReminderTests(unittest.IsolatedAsyncioTestCase):
    def test_scheduler_never_starts_a_second_polling(self):
        root = Path(__file__).resolve().parents[1]
        tree = ast.parse((root / 'bot/reminders.py').read_text(encoding='utf-8'))
        calls = {
            node.func.attr
            for node in ast.walk(tree)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
        }
        self.assertFalse(calls & {'get_updates', 'getUpdates', 'start_polling', 'run_polling'})

    def test_migration_parity_and_private_rpc(self):
        root = Path(__file__).resolve().parents[1]
        migration = (root / 'sql/migrations/20261114_stage14_daily_reminders.sql').read_text(
            encoding='utf-8'
        )
        fresh = (root / 'sql/logic.sql').read_text(encoding='utf-8')
        pattern = r'create or replace function public.claim_daily_reminders\(.*?\n\$\$;'
        self.assertEqual(
            re.search(pattern, migration, re.S).group(), re.search(pattern, fresh, re.S).group()
        )
        self.assertIn('from public,anon,authenticated', migration)
        self.assertIn('to service_role;', migration)

    async def test_loop_survives_database_failure_and_cancels(self):
        with (
            patch('bot.reminders.run_once', AsyncMock(side_effect=RuntimeError('SECRET'))),
            patch('bot.reminders.asyncio.sleep', AsyncMock(side_effect=asyncio.CancelledError)),
            self.assertLogs('bashkir-bot', level='WARNING') as logs,
            self.assertRaises(asyncio.CancelledError),
        ):
            await reminder_loop(object())
        self.assertNotIn('SECRET', ' '.join(logs.output))

    def database(self, result=None):
        row = {'user_id': 'qa', 'telegram_id': 42, 'reminder_date': '2031-01-02'}
        return SimpleNamespace(
            rpc=AsyncMock(return_value=row if result is None else result),
            select=AsyncMock(
                return_value=[{'telegram_id': 42, 'reminders_enabled': True, 'deleted_at': None}]
            ),
            user_stats=AsyncMock(return_value={'day_answers': 0}),
            daily_goal=AsyncMock(return_value=5),
            update_user=AsyncMock(),
        )

    async def test_claimed_singleton_is_delivered_with_task_button(self):
        db = self.database()
        bot = SimpleNamespace(send_message=AsyncMock())
        now = datetime(2031, 1, 2, 13, tzinfo=timezone.utc)
        await run_once(bot, now, db)
        bot.send_message.assert_awaited_once()
        args = bot.send_message.call_args
        self.assertEqual(args.args[0], 42)
        self.assertEqual(
            args.kwargs['reply_markup'].inline_keyboard[0][0].callback_data, 'menu:task'
        )
        self.assertEqual(db.rpc.call_args.args[1]['p_now'], now.isoformat())

    async def test_rechecks_goal_and_revoked_deleted_identity(self):
        for changes in (
            {'reminders_enabled': False},
            {'deleted_at': '2031-01-02'},
            {'telegram_id': -42},
        ):
            db = self.database()
            db.select.return_value = [{**db.select.return_value[0], **changes}]
            bot = SimpleNamespace(send_message=AsyncMock())
            await run_once(bot, database=db)
            bot.send_message.assert_not_awaited()
        db = self.database()
        db.user_stats.return_value = {'day_answers': 5}
        bot = SimpleNamespace(send_message=AsyncMock())
        await run_once(bot, database=db)
        bot.send_message.assert_not_awaited()

    async def test_block_disables_preference_and_timeout_is_not_retried(self):
        db = self.database()
        bot = SimpleNamespace(
            send_message=AsyncMock(
                side_effect=TelegramForbiddenError(
                    method=SendMessage(chat_id=42, text='qa'), message='blocked'
                )
            )
        )
        await run_once(bot, database=db)
        db.update_user.assert_awaited_once_with('qa', {'reminders_enabled': False})
        db = self.database()
        db.rpc.side_effect = [db.rpc.return_value, []]
        bot.send_message = AsyncMock(side_effect=TimeoutError('SECRET MUST NOT BE LOGGED'))
        with self.assertLogs('bashkir-bot', level='WARNING') as logs:
            await run_once(bot, database=db)
            await run_once(bot, database=db)
        self.assertNotIn('SECRET', ' '.join(logs.output))
        bot.send_message.assert_awaited_once()
        db.update_user.assert_not_awaited()  # Never clear the durable claim after uncertain delivery.

    async def test_no_claim_no_send_and_naive_clock_rejected(self):
        bot = SimpleNamespace(send_message=AsyncMock())
        db = self.database([])
        await run_once(bot, database=db)
        self.assertEqual(db.rpc.call_args.args[1], {'p_limit': 20})
        bot.send_message.assert_not_awaited()
        with self.assertRaises(ValueError):
            await run_once(bot, datetime(2031, 1, 2), self.database())
