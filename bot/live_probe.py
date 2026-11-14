"""Opt-in receipts for one live QA account; never record message bodies or secrets."""

import asyncio
import contextvars
import hashlib
import json
import os
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from aiogram import BaseMiddleware
from aiogram.client.session.middlewares.base import BaseRequestMiddleware

CURRENT = contextvars.ContextVar('live_telegram_receipt', default=None)
COMMANDS = {
    'start',
    'task',
    'cancel',
    'me',
    'top',
    'report',
    'privacy',
    'help',
    'pair',
    'delete_me',
}


def db_fingerprint(url):
    return hashlib.sha256(url.rstrip('/').encode()).hexdigest()


def classify(event):
    if event.callback_query:
        parts = (event.callback_query.data or '').split(':')
        action = ':'.join(parts[:2])
        allowed = {
            'role:student',
            'role:teacher',
            'task:confirm',
            'task:correct',
            'task:skip',
            'flow:next',
            'top:day',
            'top:week',
            'top:month',
            'top:year',
            'delete:yes',
            'delete:no',
        }
        if parts[0] == 'pair':
            action = 'pair'
        elif action not in allowed:
            action = 'other_callback'
        target = None
        if action.startswith('task:') and len(parts) == 3:
            try:
                target = str(uuid.UUID(parts[2]))
            except ValueError:
                pass
        return event.callback_query.from_user.id, action, target
    if event.message and event.message.from_user:
        first = (event.message.text or '').split(maxsplit=1)
        command = first[0].split('@')[0].removeprefix('/') if first else ''
        action = (
            '/' + command if first and first[0].startswith('/') and command in COMMANDS else 'text'
        )
        return event.message.from_user.id, action, None
    return None, None, None


class Probe:
    def __init__(self, path, user_id, bot_id, url):
        self.path = Path(path)
        self.user_id = user_id
        self.data = {
            'version': 1,
            'session': uuid.uuid4().hex,
            'pid': os.getpid(),
            'bot_id': bot_id,
            'db': db_fingerprint(url),
            'user_id': user_id,
            'mode': 'polling',
            'events': [],
            'stopped': False,
        }

    def save(self):
        self.data['heartbeat'] = time.time()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix('.tmp')
        temporary.write_text(json.dumps(self.data), encoding='utf-8')
        temporary.replace(self.path)

    def record(self, kind, update_id, action=None, target=None, method=None):
        self.data['events'].append(
            {
                'at': time.time(),
                'kind': kind,
                'update': update_id,
                'action': action,
                'target': target,
                'method': method,
            }
        )
        self.data['events'] = self.data['events'][-500:]
        self.save()


class Incoming(BaseMiddleware):
    def __init__(self, probe):
        self.probe = probe

    async def __call__(self, handler, event, data):
        user, action, target = classify(event)
        message = event.message or (event.callback_query.message if event.callback_query else None)
        if user != self.probe.user_id or not message or message.chat.type != 'private':
            return None  # Test-only mode must not message unrelated accounts.
        context = (event.update_id, action, target)
        token = CURRENT.set(context)
        self.probe.record('incoming', *context)
        try:
            result = await handler(event, data)
            self.probe.record('handled', *context)
            return result
        finally:
            CURRENT.reset(token)


class Outgoing(BaseRequestMiddleware):
    def __init__(self, probe):
        self.probe = probe

    async def __call__(self, make_request, bot, method):
        chat = getattr(method, 'chat_id', None)
        if chat is not None and str(chat) != str(self.probe.user_id):
            raise ValueError('Test-only mode refuses requests to an unrelated chat')
        result = await make_request(bot, method)
        context = CURRENT.get()
        if (
            result is not None
            and result is not False
            and context
            and str(chat) == str(self.probe.user_id)
            and method.__api_method__
            in {
                'sendMessage',
                'sendDocument',
                'editMessageText',
                'editMessageReplyMarkup',
            }
        ):
            self.probe.record('delivered', *context, method=method.__api_method__)
        return result


@asynccontextmanager
async def observe_polling(bot, dispatcher):
    """Off in normal operation. Does not call getUpdates or change webhook."""
    if os.getenv('LIVE_TELEGRAM_TEST_ONLY') != '1':
        yield
        return
    path = os.getenv('LIVE_TELEGRAM_PROBE_FILE')
    user_id = int(os.getenv('LIVE_TELEGRAM_TEST_USER_ID', '0'))
    if not path or user_id <= 0:
        raise ValueError('Live probe needs an explicit file and test user ID')
    webhook = await bot.get_webhook_info(request_timeout=15)
    if webhook.url:
        raise ValueError('Webhook is active; live polling was not started or reconfigured')
    probe = Probe(path, user_id, bot.id, os.getenv('SUPABASE_URL', ''))
    lock = Path(path).with_suffix('.lock')
    lock.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    os.close(descriptor)
    dispatcher.update.outer_middleware(Incoming(probe))
    bot.session.middleware(Outgoing(probe))
    probe.save()

    async def heartbeat():
        while True:
            await asyncio.sleep(3)
            probe.save()

    ticker = asyncio.create_task(heartbeat())
    try:
        yield
    finally:
        ticker.cancel()
        try:
            await ticker
        except asyncio.CancelledError:
            pass
        probe.data['stopped'] = True
        probe.save()
        lock.unlink(missing_ok=True)
