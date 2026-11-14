import ast
import contextlib
import io
import json
import os
import tempfile
import threading
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from bot.live_probe import Incoming, Outgoing, Probe, classify, observe_polling
from scripts.live_telegram_smoke import (
    Report,
    confirmed_once,
    read_probe,
    registration_plan,
    registration_steps,
    settings,
    task_steps,
    timed_input,
    unchanged,
    witnessed,
)


def event(user=42, text='/start', callback=None):
    message = SimpleNamespace(
        from_user=SimpleNamespace(id=user), text=text, chat=SimpleNamespace(type='private')
    )
    call = (
        SimpleNamespace(from_user=message.from_user, data=callback, message=message)
        if callback
        else None
    )
    return SimpleNamespace(update_id=8, message=None if call else message, callback_query=call)


class LiveSmokeTests(unittest.TestCase):
    def test_partial_registration_resumes_without_reset(self):
        user = {'nickname': 'QA', 'role': 'student', 'class_id': None, 'lang_pair': None}
        plan = registration_plan(user, 'student')
        self.assertEqual(
            [step.name for step in plan],
            ['registration/resume', 'registration/class', 'registration/pair'],
        )
        self.assertTrue(plan[0].check({}, {'user': {'state': 'joining_class'}}))
        self.assertEqual(
            registration_plan({**user, 'class_id': 'test-room', 'lang_pair': 'ba-ru'}, 'student'),
            [],
        )

    def test_previous_report_is_preserved_on_resume(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'report.json'
            path.write_text('[{"scenario":"old","status":"PASS"}]', encoding='utf-8')
            Report(path)
            archived = list(path.parent.glob('report-previous-*.json'))
            self.assertEqual(len(archived), 1)
            self.assertEqual(archived[0].read_bytes(), path.read_bytes())
            self.assertEqual(
                json.loads(path.with_suffix('.summary.json').read_text())['complete'], False
            )
            with contextlib.redirect_stdout(io.StringIO()):
                report = Report(path)
                report.progress('registration/resume', 'ready')
                self.assertEqual(report.finish(path), 2)
            self.assertEqual(
                json.loads(path.with_suffix('.progress.json').read_text()),
                {'scenario': 'completed', 'phase': 'SKIP'},
            )

    def test_confirmation_requires_actual_points_not_just_a_row(self):
        before = {'user': {'points': 0}, 'answers': {}}
        row = {'action': 'confirm', 'points_awarded': 10}
        after = {'user': {'points': 10}, 'answers': {'pair': row}}
        self.assertTrue(confirmed_once(before, after))
        self.assertFalse(confirmed_once(before, {**after, 'user': {'points': 0}}))
        self.assertFalse(
            confirmed_once(
                before, {'user': {'points': 0}, 'answers': {'pair': {**row, 'points_awarded': 0}}}
            )
        )

    def test_observer_has_no_polling_or_webhook_mutation_calls(self):
        source = Path(__file__).resolve().parents[1] / 'scripts/live_telegram_smoke.py'
        tree = ast.parse(source.read_text(encoding='utf-8'))
        forbidden = {'get_updates', 'getUpdates', 'delete_webhook', 'set_webhook', 'send_message'}
        calls = {
            node.func.attr
            for node in ast.walk(tree)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
        }
        self.assertFalse(calls & forbidden)

    def test_settings_are_explicit_and_test_only(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / '.env.live'
            with self.assertRaises(FileNotFoundError):
                settings(path)
            path.write_text('TELEGRAM_BOT_TOKEN=DO_NOT_PRINT\n', encoding='utf-8')
            with self.assertRaises(ValueError):
                settings(path)
            path.write_text(
                'LIVE_TELEGRAM_TEST_ONLY=1\nLIVE_TELEGRAM_TEST_USER_ID=42\nTELEGRAM_BOT_TOKEN=DO_NOT_PRINT\nSUPABASE_URL=http://127.0.0.1:54321\nSUPABASE_SECRET_KEY=local-only\n',
                encoding='utf-8',
            )
            with patch.dict(os.environ, {'SUPABASE_SECRET_KEY': 'ambient-secret'}):
                self.assertEqual(settings(path)['SUPABASE_SECRET_KEY'], 'local-only')

    def test_probe_requires_fresh_correct_runtime(self):
        values = {'LIVE_TELEGRAM_TEST_USER_ID': '42', 'SUPABASE_URL': 'http://127.0.0.1:54321'}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'probe.json'
            probe = Probe(path, 42, 123, values['SUPABASE_URL'])
            probe.save()
            self.assertEqual(read_probe(path, values, 123)['pid'], os.getpid())
            for key, value in [
                ('bot_id', 999),
                ('user_id', 999),
                ('db', 'wrong'),
                ('heartbeat', 1),
                ('stopped', True),
            ]:
                body = dict(probe.data, **{key: value})
                path.write_text(json.dumps(body), encoding='utf-8')
                with self.assertRaises(ValueError):
                    read_probe(path, values, 123)

    def test_delivery_must_match_same_fresh_update_and_action(self):
        now = time.time()
        events = [
            {'at': now, 'kind': 'incoming', 'update': 4, 'action': '/start'},
            {'at': now, 'kind': 'handled', 'update': 4},
            {'at': now, 'kind': 'delivered', 'update': 4, 'method': 'sendMessage'},
        ]
        self.assertTrue(witnessed({'events': events}, now - 1, '/start'))
        self.assertFalse(witnessed({'events': events}, now + 1, '/start'))
        self.assertFalse(witnessed({'events': events}, now - 1, '/task'))
        self.assertFalse(witnessed({'events': events}, now - 1, '/start', 'sendDocument'))
        events[-1]['update'] = 9
        self.assertFalse(witnessed({'events': events}, now - 1, '/start'))

    def test_texts_and_secret_callback_payloads_are_not_recorded(self):
        self.assertEqual(classify(event(text='PRIVATE CLASS CODE'))[1], 'text')
        self.assertEqual(classify(event(callback='pair:PRIVATE'))[1:], ('pair', None))
        self.assertEqual(classify(event(callback='unknown:PRIVATE'))[1:], ('other_callback', None))
        self.assertEqual(classify(event(text='/start@qa_bot'))[1], '/start')

    def test_report_never_calls_empty_or_incomplete_run_pass(self):
        with contextlib.redirect_stdout(io.StringIO()):
            report = Report()
            self.assertEqual(report.finish(None), 2)
            report.add('scenario', 'SKIP', 'MANUAL REQUIRED')
            self.assertEqual(report.finish(None), 2)
            report.add('failure', 'FAIL', 'Timeout')
            self.assertEqual(report.finish(None), 1)

    def test_eof_is_manual_required(self):
        with patch('builtins.input', side_effect=EOFError):
            self.assertEqual(timed_input('', 1), 'skip')

    def test_input_timeout_is_bounded(self):
        gate = threading.Event()
        try:
            with patch('builtins.input', side_effect=lambda prompt: gate.wait(2)):
                started = time.monotonic()
                self.assertEqual(timed_input('', 0.02), 'skip')
                self.assertLess(time.monotonic() - started, 1)
        finally:
            gate.set()

    def test_duplicate_and_restart_predicates_preserve_database(self):
        before = {
            'user': {
                'state': 'awaiting_correction',
                'points': 10,
                'current_fragment_pair_id': 'pair',
            },
            'answers': {'pair0': {'id': 1}},
        }
        self.assertTrue(unchanged(before, before))
        duplicate = next(step for step in task_steps() if step.name == 'task/duplicate')
        self.assertTrue(duplicate.check(before, before))
        after = {**before, 'user': {**before['user'], 'points': 20}}
        self.assertFalse(duplicate.check(before, after))
        restart = next(step for step in task_steps() if step.name == 'restart/persistence')
        self.assertTrue(restart.check(before, before))
        self.assertFalse(
            restart.check(before, {**before, 'user': {**before['user'], 'state': 'idle'}})
        )
        self.assertEqual(registration_steps('teacher')[5].action, 'role:teacher')


class ProbeMiddlewareTests(unittest.IsolatedAsyncioTestCase):
    async def test_test_mode_cannot_send_to_unrelated_chat(self):
        with tempfile.TemporaryDirectory() as directory:
            probe = Probe(Path(directory) / 'probe.json', 42, 123, 'http://localhost')
            transport = AsyncMock()
            method = SimpleNamespace(chat_id=99, __api_method__='sendMessage')
            with self.assertRaises(ValueError):
                await Outgoing(probe)(transport, None, method)
            transport.assert_not_awaited()

    async def test_enabled_probe_lifecycle_and_lock(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'probe.json'
            environment = {
                'LIVE_TELEGRAM_TEST_ONLY': '1',
                'LIVE_TELEGRAM_TEST_USER_ID': '42',
                'LIVE_TELEGRAM_PROBE_FILE': str(path),
                'SUPABASE_URL': 'http://localhost',
            }
            bot = SimpleNamespace(
                id=123,
                get_webhook_info=AsyncMock(return_value=SimpleNamespace(url='')),
                session=SimpleNamespace(middleware=lambda middleware: None),
            )
            dispatcher = SimpleNamespace(
                update=SimpleNamespace(outer_middleware=lambda middleware: None)
            )
            with patch.dict(os.environ, environment):
                async with observe_polling(bot, dispatcher):
                    self.assertFalse(json.loads(path.read_text())['stopped'])
                    with self.assertRaises(FileExistsError):
                        async with observe_polling(bot, dispatcher):
                            pass
                self.assertTrue(json.loads(path.read_text())['stopped'])
                self.assertFalse(path.with_suffix('.lock').exists())

    async def test_active_webhook_never_starts_test_polling(self):
        bot = SimpleNamespace(
            get_webhook_info=AsyncMock(return_value=SimpleNamespace(url='https://private-hook'))
        )
        with patch.dict(
            os.environ,
            {
                'LIVE_TELEGRAM_TEST_ONLY': '1',
                'LIVE_TELEGRAM_TEST_USER_ID': '42',
                'LIVE_TELEGRAM_PROBE_FILE': 'unused',
            },
        ):
            with self.assertRaisesRegex(ValueError, 'Webhook'):
                async with observe_polling(bot, None):
                    self.fail('Polling must not begin')

    async def test_receipts_require_successful_real_transport_return(self):
        with tempfile.TemporaryDirectory() as directory:
            probe = Probe(Path(directory) / 'probe.json', 42, 123, 'http://localhost')
            outgoing = Outgoing(probe)

            async def handler(update, data):
                method = SimpleNamespace(
                    chat_id=42, __api_method__='sendMessage', text='PRIVATE TOKEN'
                )
                await outgoing(AsyncMock(return_value=None), None, method)
                self.assertFalse(any(e['kind'] == 'delivered' for e in probe.data['events']))
                await outgoing(AsyncMock(return_value=SimpleNamespace(message_id=3)), None, method)

            await Incoming(probe)(handler, event(text='PRIVATE TOKEN'), {})
            self.assertTrue(witnessed(probe.data, 0, 'text'))
            content = probe.path.read_text(encoding='utf-8')
            self.assertNotIn('PRIVATE', content)
            self.assertNotIn('text":', content)

    async def test_unrelated_accounts_are_not_processed_in_live_test_mode(self):
        with tempfile.TemporaryDirectory() as directory:
            probe = Probe(Path(directory) / 'probe.json', 42, 123, 'http://localhost')
            handler = AsyncMock()
            await Incoming(probe)(handler, event(user=99), {})
            handler.assert_not_called()
            self.assertFalse(probe.path.exists())

    async def test_diagnostics_are_off_in_normal_runtime(self):
        with patch.dict(os.environ, {'LIVE_TELEGRAM_TEST_ONLY': '0'}):
            async with observe_polling(None, None):
                pass
