import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class ExpeditionContractTests(unittest.TestCase):
    def test_migration_is_transactional_and_no_personal_fields(self):
        sql = (ROOT / 'sql/migrations/20261113_stage6_expedition.sql').read_text(encoding='utf-8')
        self.assertTrue(sql.strip().startswith('begin;'))
        self.assertTrue(sql.strip().endswith('commit;'))
        self.assertIn('create or replace view public.adventure_progress', sql)
        self.assertIn("s.license <> 'demo'", sql)
        self.assertIn('grant select on public.adventure_progress to anon, service_role', sql)
        for personal in ('telegram_id', 'username', 'display_name', 'user_id'):
            self.assertNotIn(personal, sql)

    def test_fresh_install_and_update_share_view(self):
        original = (ROOT / 'sql/logic.sql').read_text(encoding='utf-8')
        updated = (ROOT / 'sql/migrations/20261113_stage6_expedition.sql').read_text(
            encoding='utf-8'
        )
        self.assertIn('create or replace view public.adventure_progress', original)
        self.assertIn('create or replace view public.adventure_progress', updated)
        self.assertIn('grant select on public.adventure_progress to anon, service_role', original)

    def test_browser_uses_public_rpc_and_localhost_only(self):
        site = (ROOT / 'web/index.html').read_text(encoding='utf-8')
        for marker in (
            'id="community-confirmed"',
            'id="community-pair"',
            'id="community-refresh"',
            "request('adventure_progress'",
            '127\\.0\\.0\\.1',
            '1, 5, 15',
        ):
            self.assertIn(marker, site)
        self.assertNotIn('.innerHTML', site)

    def test_setup_script_restricts_listen_address(self):
        setup = (ROOT / 'scripts/setup_local.ps1').read_text(encoding='utf-8')
        self.assertIn('127.0.0.1', setup)
        self.assertIn('local-network', setup)
        self.assertNotIn('db reset', setup)
        self.assertNotIn('--no-backup', setup)


if __name__ == '__main__':
    unittest.main()
