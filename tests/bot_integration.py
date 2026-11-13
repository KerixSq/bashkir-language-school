"""Exercise aiogram handlers and real database FSM, with Telegram transport stubbed.

Uses SUPABASE_URL / SUPABASE_SECRET_KEY. Creates and removes only its fixtures.
This is not a live Telegram polling test.
"""

import asyncio
import secrets
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from aiogram import Bot
from aiogram.client.session.base import BaseSession
from aiogram.types import CallbackQuery, Chat, Message, Update, User

from bot import db
from bot.main import create_dispatcher
from scripts.common import client
from scripts.pure import new_join_code


class TelegramStub(BaseSession):
    def __init__(self):
        super().__init__()
        self.messages = []

    async def close(self):
        pass

    async def stream_content(self, *args, **kwargs):
        if False:
            yield b''

    async def make_request(self, bot, method, timeout=None):
        if method.__api_method__ == 'getMe':
            return User(id=123456, is_bot=True, first_name='Test', username='test_school_bot')
        if method.__api_method__ in ('sendMessage', 'sendDocument'):
            self.messages.append(getattr(method, 'text', '[document]'))
            return Message(
                message_id=len(self.messages),
                date=datetime.now(timezone.utc),
                chat=Chat(id=int(method.chat_id), type='private'),
                text=getattr(method, 'text', None),
            )
        if method.__api_method__ in ('answerCallbackQuery', 'editMessageReplyMarkup'):
            return True
        raise AssertionError('Unexpected Telegram call: ' + method.__api_method__)


async def main():
    api = client()
    stamp = secrets.token_hex(5)
    pair_code = 'ba-bot-' + stamp
    stored = {}
    users = []
    stub = TelegramStub()
    bot = Bot('123456:transport-is-stubbed-no-real-token', session=stub)
    dispatcher = create_dispatcher()
    tick = 0

    async def send(telegram_id, text=None, callback=None, group=False):
        nonlocal tick
        tick += 1
        sender = User(id=telegram_id, is_bot=False, first_name='Test')
        message = Message(
            message_id=tick,
            date=datetime.now(timezone.utc),
            from_user=sender,
            chat=Chat(id=telegram_id, type='group' if group else 'private'),
            text=text,
        )
        if callback:
            event = Update(
                update_id=tick,
                callback_query=CallbackQuery(
                    id=str(tick),
                    from_user=sender,
                    chat_instance='test',
                    data=callback,
                    message=message,
                ),
            )
        else:
            event = Update(update_id=tick, message=message)
        await dispatcher.feed_update(bot, event)

    try:
        api.table('lang_pairs').insert({'code': pair_code, 'name': 'Bot integration'}).execute()
        stored['pair_code'] = pair_code
        stored['school'] = (
            api.table('schools').insert({'name': 'Bot integration'}).execute().data[0]['id']
        )
        room = (
            api.table('classes')
            .insert(
                {
                    'school_id': stored['school'],
                    'name': 'Bot integration',
                    'join_code': new_join_code(),
                    'teacher_code': secrets.token_urlsafe(32),
                }
            )
            .execute()
            .data[0]
        )
        stored['room'] = room['id']
        stored['source'] = (
            api.table('sources')
            .insert({'title': 'Bot integration', 'kind': 'text', 'license': 'test'})
            .execute()
            .data[0]['id']
        )
        stored['fragment'] = (
            api.table('fragments')
            .insert(
                {'source_id': stored['source'], 'position': 1, 'text_ba': 'TECHNICAL BOT FIXTURE'}
            )
            .execute()
            .data[0]['id']
        )
        stored['pair'] = (
            api.table('fragment_pairs')
            .insert(
                {
                    'fragment_id': stored['fragment'],
                    'lang_pair': pair_code,
                    'auto_translation': 'Техническая проверка.',
                }
            )
            .execute()
            .data[0]['id']
        )
        tg = 8_000_000_000_000 + secrets.randbelow(100_000_000)
        await send(tg, '/start', group=True)
        assert await db.user_by_telegram(tg) is None
        await send(tg, '/start')
        user = await db.user_by_telegram(tg)
        users.append(user['id'])
        assert user['state'] == 'choosing_nickname'
        await send(tg, '___')
        assert (await db.user_by_telegram(tg))['nickname'] is None
        await send(tg, 'Тестовый ученик')
        await send(tg, callback='role:student')
        await send(tg, room['join_code'])
        await send(tg, callback='pair:' + pair_code)
        assert (await db.user_by_telegram(tg))['state'] == 'idle'
        await send(tg, '/task')
        user = await db.user_by_telegram(tg)
        assert user['current_fragment_pair_id'] == stored['pair']
        await send(tg, callback='task:correct:' + stored['pair'])
        assert (await db.user_by_telegram(tg))['state'] == 'awaiting_correction'
        await send(tg, '/cancel')
        assert (await db.user_by_telegram(tg))['current_fragment_pair_id'] is None
        await send(tg, '/task')
        await db.update_user(
            user['id'],
            {'current_shown_at': (datetime.now(timezone.utc) - timedelta(seconds=10)).isoformat()},
        )
        await send(tg, callback='task:confirm:' + stored['pair'])
        assert (await db.user_by_telegram(tg))['points'] == 10
        await send(tg, callback='task:confirm:' + stored['pair'])
        assert (await db.user_by_telegram(tg))['points'] == 10
        await send(tg, '/report')
        assert 'Отчёт доступен преподавателю' in stub.messages[-1]
        for command in ('/me', '/top', '/help', '/privacy', '/pair', '/cancel'):
            await send(tg, command)
        await send(tg, '/delete_me')
        await send(tg, callback='delete:yes')
        assert await db.user_by_telegram(tg) is None
        assert api.table('answers').select('id').eq('user_id', user['id']).execute().data
        print(
            'PASS aiogram: private-chat guard, registration, invalid nickname, task, correction, cancel, duplicate, report access, profile, deletion'
        )
        print('Telegram transport was stubbed; live polling NOT RUN')
    finally:
        for table, field, values in [
            ('user_badges', 'user_id', users),
            ('answers', 'user_id', users),
            ('users', 'id', users),
            ('status_history', 'fragment_pair_id', [stored.get('pair')]),
            ('fragment_pairs', 'id', [stored.get('pair')]),
            ('fragments', 'id', [stored.get('fragment')]),
            ('sources', 'id', [stored.get('source')]),
            ('classes', 'id', [stored.get('room')]),
            ('schools', 'id', [stored.get('school')]),
            ('lang_pairs', 'code', [stored.get('pair_code')]),
        ]:
            values = [value for value in values if value]
            if values:
                api.table(table).delete().in_(field, values).execute()
        await bot.session.close()


if __name__ == '__main__':
    asyncio.run(main())
