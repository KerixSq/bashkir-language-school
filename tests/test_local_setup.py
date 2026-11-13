"""Local setup must never leak credentials or accept a failed permissions check."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import configure_local_env as env_tool
from scripts import doctor


class LocalEnvironmentTests(unittest.TestCase):
    def setUp(self):
        self.status = '\n'.join(
            [
                'API_URL="http://127.0.0.1:54321"',
                'ANON_KEY="public-example"',
                'SERVICE_ROLE_KEY="secret-example"',
            ]
        )

    def test_status_mapping_and_legacy_keys(self):
        self.assertEqual(
            env_tool.local_values(self.status),
            {
                'SUPABASE_URL': 'http://127.0.0.1:54321',
                'SUPABASE_PUBLIC_KEY': 'public-example',
                'SUPABASE_SECRET_KEY': 'secret-example',
            },
        )

    def test_new_style_keys_take_precedence(self):
        text = self.status + '\nPUBLISHABLE_KEY="new-pub"\nSECRET_KEY="new-secret"'
        self.assertEqual(env_tool.local_values(text)['SUPABASE_PUBLIC_KEY'], 'new-pub')
        self.assertEqual(env_tool.local_values(text)['SUPABASE_SECRET_KEY'], 'new-secret')

    def test_missing_keys_or_remote_url_are_rejected(self):
        for text in ('', 'API_URL="https://example.supabase.co"\nANON_KEY=a\nSERVICE_ROLE_KEY=b'):
            with self.subTest(text=text), self.assertRaises(ValueError):
                env_tool.local_values(text)

    def test_keep_bot_token_and_all_custom_settings(self):
        previous = '\n'.join(
            [
                '# Team configuration',
                'TELEGRAM_BOT_TOKEN=existing-bot-secret',
                'SUPABASE_URL=https://previous.example',
                'CUSTOM_SETTING=42',
                'SUPABASE_SECRET_KEY=old-key',
                'SUPABASE_PUBLIC_KEY=old-public',
                'SUPABASE_PUBLIC_KEY=duplicate-old-public',
                '',
            ]
        )
        updated = env_tool.merge_env(previous, env_tool.local_values(self.status))
        self.assertIn('TELEGRAM_BOT_TOKEN=existing-bot-secret', updated)
        self.assertIn('CUSTOM_SETTING=42', updated)
        self.assertIn('# Team configuration', updated)
        self.assertNotIn('old-public', updated)
        self.assertEqual(updated.count('SUPABASE_PUBLIC_KEY='), 1)
        self.assertIn('SUPABASE_URL=http://127.0.0.1:54321', updated)

    def test_write_makes_backup_without_changing_token(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / '.env'
            path.write_text('TELEGRAM_BOT_TOKEN=keep-me\nSUPABASE_URL=remote\n', encoding='utf-8')
            content = env_tool.merge_env(path.read_text(), env_tool.local_values(self.status))
            self.assertTrue(env_tool.write_env(path, content))
            self.assertFalse(env_tool.write_env(path, content))
            self.assertEqual(len(list(Path(temp).glob('.env.backup-*'))), 1)
            self.assertIn('TELEGRAM_BOT_TOKEN=keep-me', path.read_text(encoding='utf-8'))


class LocalDoctorTests(unittest.TestCase):
    def setUp(self):
        self.good = {
            'SUPABASE_URL': 'http://127.0.0.1:54321',
            'SUPABASE_PUBLIC_KEY': 'sb_publishable_sample',
            'SUPABASE_SECRET_KEY': 'sb_secret_sample',
            'TELEGRAM_BOT_TOKEN': 'fake-bot',
        }

    def test_remote_and_secret_as_public_rejected(self):
        for updates in (
            {'SUPABASE_URL': 'https://remote.example'},
            {'SUPABASE_PUBLIC_KEY': 'sb_secret_sample'},
        ):
            with self.subTest(updates=updates), self.assertRaises(ValueError):
                doctor.validate_settings({**self.good, **updates})

    def test_public_view_and_closed_table_pass(self):
        rows = [{'lang_pair': 'ba-ru', 'confirmed': 2, 'collecting': 1, 'expert_review': 0}]
        with patch('scripts.doctor.rest_get', side_effect=[(200, rows), (403, None)]) as request:
            doctor.check_public_api('http://127.0.0.1:54321', 'public-key')
            self.assertEqual(request.call_count, 2)

    def test_empty_public_table_read_must_fail(self):
        with patch('scripts.doctor.rest_get', side_effect=[(200, []), (200, [])]):
            with self.assertRaisesRegex(RuntimeError, 'can SELECT users'):
                doctor.check_public_api('http://127.0.0.1:54321', 'key')

    def test_run_local_requires_token(self):
        with self.assertRaisesRegex(ValueError, 'TELEGRAM_BOT_TOKEN'):
            doctor.validate_settings({**self.good, 'TELEGRAM_BOT_TOKEN': ''}, require_bot=True)

    def test_broken_api_is_not_a_false_pass(self):
        for response in ((503, None), (200, {'unexpected': 'body'})):
            with self.subTest(response=response):
                with patch('scripts.doctor.rest_get', return_value=response):
                    with self.assertRaises(RuntimeError):
                        doctor.check_public_api('http://127.0.0.1:54321', 'key')

    def test_read_env_does_not_print_secrets(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / '.env'
            path.write_text(
                'TELEGRAM_BOT_TOKEN="test-value"\n# X\nSUPABASE_URL=http://127.0.0.1:54321\n'
            )
            self.assertEqual(doctor.read_env(path)['TELEGRAM_BOT_TOKEN'], 'test-value')


if __name__ == '__main__':
    unittest.main()
