"""Проверки связности браузерного режима без обращения к базе."""

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class BrowserFirstContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = (ROOT / 'web/index.html').read_text(encoding='utf-8')
        cls.logic = (ROOT / 'sql/logic.sql').read_text(encoding='utf-8')
        cls.schema = (ROOT / 'sql/schema.sql').read_text(encoding='utf-8')
        cls.migration = (ROOT / 'sql/migrations/20261113_stage8_browser_first.sql').read_text(
            encoding='utf-8'
        )

    def test_all_required_cdn_scripts(self):
        for marker in (
            'cdn.tailwindcss.com',
            'fonts.googleapis.com',
            'font-awesome/6.7.2/css/all.min.css',
            'gsap.min.js',
            'ScrollTrigger.min.js',
            'lenis.min.js',
            'assets/vendor/supabase.min.js',
        ):
            self.assertIn(marker, self.html)

    def test_all_rpc_have_consistent_signatures(self):
        for name in (
            'web_register',
            'web_profile',
            'web_next_fragment',
            'web_submit_answer',
            'web_skip_fragment',
        ):
            self.assertRegex(self.logic, rf'create or replace function public\.{name}\s*\(')
            self.assertRegex(self.migration, rf'create or replace function public\.{name}\s*\(')
            self.assertIn(f"rpc('{name}'", self.html)

    def test_browser_rpc_uses_authenticated_not_anon(self):
        self.assertIn('to authenticated;', self.logic)
        self.assertIn('auth.uid()', self.logic)
        self.assertIn('security definer set search_path', self.logic)
        self.assertNotIn('sb_secret_', self.html[: self.html.index('<body')])
        self.assertNotRegex(self.html, r'PUBLISHED_(?:SERVICE|SECRET)_KEY')
        self.assertIn('users_identity_present', self.schema)
        self.assertIn('users_identity_present', self.migration)
        self.assertIn('alter column telegram_id drop not null', self.migration)

    def test_no_direct_browser_writes_to_users(self):
        html = self.html
        self.assertNotRegex(html, r'from\(\s*["\']users["\']\s*\)\.insert')
        self.assertNotRegex(html, r'from\(\s*["\']answers["\']\s*\)\.insert')
        self.assertIn('auth.signInAnonymously()', html)

    def test_main_features_in_dom(self):
        for name in (
            'web-play',
            'web-register-form',
            'web-next',
            'web-confirm',
            'web-correction',
            'web-correct-form',
            'web-skip',
            'web-points',
            'web-level',
            'web-streak',
            'web-badges',
            'web-progress',
        ):
            self.assertIn(f'id="{name}"', self.html)

    def test_migration_transaction_and_no_destroy(self):
        self.assertTrue(self.migration.strip().startswith('begin;'))
        self.assertTrue(self.migration.strip().endswith('commit;'))
        self.assertNotRegex(self.migration, re.compile(r'\bdrop\s+table\b', re.I))
        self.assertNotRegex(self.migration, re.compile(r'\btruncate\b', re.I))


if __name__ == '__main__':
    unittest.main()
