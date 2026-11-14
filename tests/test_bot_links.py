import unittest

from bot.links import public_web_url


class BotLinkTests(unittest.TestCase):
    def test_public_https_only_without_credentials(self):
        self.assertEqual(
            public_web_url('https://school.example/web/'), 'https://school.example/web'
        )
        for value in (
            '',
            'http://127.0.0.1:54321/web',
            'https://localhost',
            'https://192.168.1.1',
            'https://user:secret@school.example',
            'javascript:alert(1)',
            'https://school.example?secret=value',
        ):
            self.assertIsNone(public_web_url(value))
