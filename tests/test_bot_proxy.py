import unittest
from pathlib import Path

from bot.proxy import proxy_url


class BotProxyTests(unittest.TestCase):
    def test_explicit_transport_and_secret_safe_validation(self):
        self.assertIsNone(proxy_url(None))
        self.assertIsNone(proxy_url('  '))
        self.assertIsNone(proxy_url('direct'))
        self.assertEqual(proxy_url('socks5://tor:9050'), 'socks5://tor:9050')
        for value in (
            'ftp://user:SECRET@host:21',
            'socks5://user:SECRET@host:bad',
            'http://host:80/path',
        ):
            with self.assertRaises(ValueError) as error:
                proxy_url(value)
            self.assertNotIn('SECRET', str(error.exception))

    def test_tor_is_optional_for_site_and_does_not_gate_bot_health(self):
        compose = (Path(__file__).resolve().parents[1] / 'docker-compose.yml').read_text(
            encoding='utf-8'
        )
        bot = compose.split('\n  bot:', 1)[1].split('\n  tor:', 1)[0]
        tor = compose.split('\n  tor:', 1)[1].split('\nnetworks:', 1)[0]
        self.assertNotIn('      tor:', bot)
        self.assertIn('profiles: [bot]', tor)
        self.assertNotIn('container_name:', tor)
        self.assertIn('${BOT_PROXY_URL-socks5://tor:9050}', bot)
        self.assertIn('--max-time 8', tor)
