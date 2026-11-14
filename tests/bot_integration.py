"""Exercise aiogram handlers and real database FSM, with Telegram transport stubbed.

Uses SUPABASE_URL / SUPABASE_SECRET_KEY. Creates and removes only its fixtures.
This is not a live Telegram polling test.
"""

import asyncio
import csv
import io
import secrets
import subprocess
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
        self.documents = []

    async def close(self):
        pass

    async def stream_content(self, *args, **kwargs):
        if False:
            yield b''

    async def make_request(self, bot, method, timeout=None):
        if method.__api_method__ == 'getMe':
            return User(id=123456, is_bot=True, first_name='Test', username='test_school_bot')
        if method.__api_method__ in ('sendMessage', 'sendDocument'):
            if method.__api_method__ == 'sendDocument':
                self.documents.append(method.document.data)
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
    pairs = []
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
            message = message.model_copy(
                update={'from_user': User(id=123456, is_bot=True, first_name='Bot')}
            )
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
        pairs.append(stored['pair'])
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
        await send(tg, callback='role:invalid')
        assert (await db.user_by_telegram(tg))['state'] == 'choosing_role'
        await send(tg, callback='role:student')
        await send(tg, 'INVALID-CODE')
        assert (await db.user_by_telegram(tg))['class_id'] is None
        await send(tg, room['join_code'])
        await send(tg, callback='pair:missing')
        assert (await db.user_by_telegram(tg))['state'] == 'choosing_pair'
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
        assert await db.user_badges(user['id'])
        assert len(api.table('answers').select('id').eq('user_id', user['id']).execute().data) == 1
        print('PASS student registration, validation, confirm, duplicate points and first badge')

        async def register(account, role):
            await send(account, '/start')
            registered = await db.user_by_telegram(account)
            users.append(registered['id'])
            await send(account, 'QA ' + role + ' ' + str(account)[-6:])
            await send(account, callback='role:' + role)
            if role == 'teacher':
                await send(account, room['join_code'])
                assert (await db.user_by_telegram(account))['class_id'] is None
            await send(account, room['teacher_code'] if role == 'teacher' else room['join_code'])
            await send(account, callback='pair:' + pair_code)
            result = await db.user_by_telegram(account)
            assert result['state'] == 'idle' and result['role'] == role
            assert result['class_id'] == room['id'] and result['lang_pair'] == pair_code
            return result

        for account in (tg + 1, tg + 2):
            voter = await register(account, 'student')
            await send(account, '/task')
            await db.update_user(
                voter['id'],
                {
                    'current_shown_at': (
                        datetime.now(timezone.utc) - timedelta(seconds=10)
                    ).isoformat()
                },
            )
            await send(account, callback='task:confirm:' + stored['pair'])
            assert (await db.user_by_telegram(account))['points'] >= 10
        final = api.table('fragment_pairs').select('*').eq('id', stored['pair']).execute().data[0]
        assert (
            final['status'] == 'confirmed' and final['final_translation'] == 'Техническая проверка.'
        )
        votes = (
            api.table('answers').select('*').eq('fragment_pair_id', stored['pair']).execute().data
        )
        assert len(votes) == 3 and len({vote['user_id'] for vote in votes}) == 3
        for account in (tg, tg + 1, tg + 2):
            participant = await db.user_by_telegram(account)
            assert participant['points'] == 15
            await send(account, callback='task:confirm:' + stored['pair'])
            assert (await db.user_by_telegram(account))['points'] == 15
        print('PASS three independent users: consensus, final translation, bonus exactly once')

        await register(tg + 3, 'teacher')
        await send(tg + 3, '/report')
        assert len(stub.documents) == 1
        csv_rows = list(csv.reader(io.StringIO(stub.documents[0].decode('utf-8-sig'))))
        assert csv_rows[1][0:4] == ['Bot integration', 'Bot integration', '3', '3']
        student = await db.user_by_telegram(tg)
        assert any(student['nickname'] in row for row in csv_rows)
        await send(tg + 3, '/newclass')
        assert '|' in stub.messages[-1]
        await send(tg, '/newclass')
        assert 'Отчёт доступен преподавателю' in stub.messages[-1]
        print(
            'PASS teacher registration, student-code rejection, report permissions and CSV content'
        )

        solo = tg + 4
        await send(solo, '/start')
        independent = await db.user_by_telegram(solo)
        users.append(independent['id'])
        await send(solo, 'Самостоятельный QA')
        await send(solo, callback='role:student')
        await send(solo, callback='study:solo')
        await send(solo, callback='pair:' + pair_code)
        await send(solo, '/start')
        independent = await db.user_by_telegram(solo)
        assert independent['class_id'] is None and independent['state'] == 'idle'
        await send(solo, callback='menu:task')
        independent = await db.user_by_telegram(solo)
        assert independent['current_fragment_pair_id'] == stored['pair']
        await db.update_user(
            independent['id'],
            {'current_shown_at': (datetime.now(timezone.utc) - timedelta(seconds=10)).isoformat()},
        )
        await send(solo, callback='task:confirm:' + stored['pair'])
        independent = await db.user_by_telegram(solo)
        assert independent['points'] > 0
        earned = independent['points']
        for action in ('home', 'progress', 'contribution', 'history', 'ratings', 'settings'):
            await send(solo, callback='menu:' + action)
            assert stub.messages[-1]
        assert any(row['name'] == independent['nickname'] for row in await db.top_users('day'))
        assert await db.rank_summary(independent) is None
        await send(solo, '/join')
        await send(solo, room['join_code'])
        await send(solo, callback='pair:' + pair_code)
        joined = await db.user_by_telegram(solo)
        assert joined['id'] == independent['id'] and joined['class_id'] == room['id']
        assert joined['points'] == earned
        assert len(await db.select('answers', user_id=joined['id'])) == 1
        print(
            'PASS independent student, real task and points, menu identity, join preserves progress'
        )

        # A separate fragment is needed because fragment/lang_pair is unique.
        fragment2 = (
            api.table('fragments')
            .insert(
                {
                    'source_id': stored['source'],
                    'position': 2,
                    'text_ba': 'TECHNICAL CORRECTION FIXTURE',
                }
            )
            .execute()
            .data[0]['id']
        )
        stored['fragment2'] = fragment2
        extra = (
            api.table('fragment_pairs')
            .insert(
                {
                    'fragment_id': fragment2,
                    'lang_pair': pair_code,
                    'auto_translation': 'Другой технический вариант.',
                }
            )
            .execute()
            .data[0]['id']
        )
        pairs.append(extra)
        await send(tg, callback='flow:next')
        assert (await db.user_by_telegram(tg))['current_fragment_pair_id'] == extra
        before = (await db.user_by_telegram(tg))['points']
        await send(tg, callback='task:invalid:' + extra)
        assert (await db.user_by_telegram(tg))['points'] == before
        await send(tg, callback='task:skip:' + extra)
        await send(tg, callback='task:skip:' + extra)
        assert not api.table('answers').select('id').eq('fragment_pair_id', extra).execute().data
        assert (await db.user_by_telegram(tg))['points'] == before
        await send(tg, '/task')
        await send(tg, callback='task:correct:' + extra)
        await send(tg, '/pair')
        assert (await db.user_by_telegram(tg))['state'] == 'awaiting_correction'
        await db.update_user(
            user['id'],
            {
                'current_shown_at': (
                    datetime.now(timezone.utc) - timedelta(seconds=10)
                ).isoformat(),
                'last_answer_at': (datetime.now(timezone.utc) - timedelta(seconds=10)).isoformat(),
            },
        )
        # Fresh interpreter + real Dispatcher: no shared in-memory FSM or cached user rows.
        subprocess.run([sys.executable, __file__, '--resume', str(tg), extra], check=True)
        after = await db.user_by_telegram(tg)
        assert after['state'] == 'idle' and after['points'] == before + 10
        assert (
            len(api.table('answers').select('id').eq('fragment_pair_id', extra).execute().data) == 1
        )
        await send(tg, callback='task:confirm:' + extra)
        assert (await db.user_by_telegram(tg))['points'] == after['points']
        print(
            'PASS skip, invalid callbacks, correction across process restart, duplicate protection'
        )
        await send(tg, callback='task:confirm:' + stored['pair'])
        assert (await db.user_by_telegram(tg))['points'] == after['points']
        await send(tg, '/report')
        assert 'Отчёт доступен преподавателю' in stub.messages[-1]
        for command in ('/me', '/top', '/help', '/privacy', '/pair', '/cancel', '/start'):
            await send(tg, command)
            assert stub.messages[-1]
        for period, label in (
            ('day', 'день'),
            ('week', 'неделю'),
            ('month', 'месяц'),
            ('year', 'год'),
        ):
            await send(tg, callback='top:' + period)
            assert 'за ' + label in stub.messages[-1]
        assert any(row['name'] == after['nickname'] for row in await db.top_users('day'))
        await send(tg, '/delete_me')
        await send(tg, callback='delete:no')
        assert await db.user_by_telegram(tg)
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
            ('status_history', 'fragment_pair_id', pairs),
            ('fragment_pairs', 'id', pairs),
            ('fragments', 'id', [stored.get('fragment'), stored.get('fragment2')]),
            ('sources', 'id', [stored.get('source')]),
            ('classes', 'id', [stored.get('room')]),
            ('schools', 'id', [stored.get('school')]),
            ('lang_pairs', 'code', [stored.get('pair_code')]),
        ]:
            values = [value for value in values if value]
            if values:
                api.table(table).delete().in_(field, values).execute()
        await bot.session.close()


async def resume_correction(telegram_id, pair):
    stub = TelegramStub()
    bot = Bot('123456:transport-is-stubbed-no-real-token', session=stub)
    dispatcher = create_dispatcher()
    try:
        user = await db.user_by_telegram(telegram_id)
        assert user['state'] == 'awaiting_correction' and user['current_fragment_pair_id'] == pair
        for index, text in enumerate(('/start', 'Исправленный технический вариант.'), 1):
            await dispatcher.feed_update(
                bot,
                Update(
                    update_id=index,
                    message=Message(
                        message_id=index,
                        date=datetime.now(timezone.utc),
                        from_user=User(id=telegram_id, is_bot=False, first_name='Test'),
                        chat=Chat(id=telegram_id, type='private'),
                        text=text,
                    ),
                ),
            )
        assert (await db.user_by_telegram(telegram_id))['state'] == 'idle'
        print('PASS fresh process restores PostgreSQL FSM and submits correction')
    finally:
        await bot.session.close()


if __name__ == '__main__':
    asyncio.run(
        resume_correction(int(sys.argv[2]), sys.argv[3])
        if len(sys.argv) == 4 and sys.argv[1] == '--resume'
        else main()
    )
