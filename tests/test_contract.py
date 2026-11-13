import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TABLES = (
    'lang_pairs',
    'schools',
    'classes',
    'users',
    'sources',
    'fragments',
    'fragment_pairs',
    'answers',
    'config',
    'badges',
    'user_badges',
    'phrasebook_rows',
)


class ContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.schema = (ROOT / 'sql/schema.sql').read_text(encoding='utf-8')
        cls.logic = (ROOT / 'sql/logic.sql').read_text(encoding='utf-8')
        cls.migration = (ROOT / 'sql/migrations/20261113_stage2_product.sql').read_text(
            encoding='utf-8'
        )
        cls.site = (ROOT / 'web/index.html').read_text(encoding='utf-8')

    def test_all_tables_have_rls(self):
        for name in TABLES:
            self.assertIn(f'create table if not exists public.{name} (', self.schema)
            self.assertIn(f'alter table public.{name} enable row level security;', self.schema)

    def test_sql_api_contract(self):
        for rpc in ('get_next_fragment', 'submit_answer', 'get_class_report'):
            self.assertIn(f'create or replace function public.{rpc}(', self.logic)
        for view in (
            'leaderboard_users',
            'leaderboard_classes',
            'leaderboard_schools',
            'user_stats',
            'translations_export',
            'expert_review_queue',
        ):
            self.assertIn(f'create or replace view public.{view}', self.logic)

    def test_public_nicknames_only(self):
        text = self.logic.split('create or replace view public.leaderboard_users', 1)[1]
        text = text.split(';', 1)[0]
        for forbidden in ('telegram_id', 'user_id', 'display_name', 'username'):
            self.assertNotIn(forbidden, text)
        self.assertIn('nickname as name', text)
        self.assertIn("where role='student'", text)

    def test_seven_columns_in_export(self):
        text = self.logic.split('create or replace view public.translations_export', 1)[1]
        text = text.split(';', 1)[0]
        for field in (
            'fragment_id',
            'text_ba',
            'lang_pair',
            'translation',
            'source',
            'confirmed',
            'status',
        ):
            self.assertIn(field, text)

    def test_daily_goal_applies_to_existing_db(self):
        self.assertIn("('daily_goal','5')", (ROOT / 'sql/seed.sql').read_text(encoding='utf-8'))
        self.assertIn("('daily_goal','5')", self.migration)
        self.assertIn('last_goal_date', self.schema)
        self.assertIn('last_goal_date', self.migration)
        self.assertIn('goal_just_reached', self.logic)
        self.assertIn('goal_streak', self.logic)

    def test_api_source_not_inserted_as_markup(self):
        self.assertNotIn('.innerHTML', self.site)
        self.assertIn('textContent', self.site)
        self.assertIn('const PUBLISHED_PUBLIC_KEY =', self.site)
        self.assertNotIn('sb_secret_abcdefghijklmnopqrstuvwxyz', self.site)

    def test_idempotent_migration_header(self):
        self.assertTrue(self.migration.lstrip().startswith('--'))
        self.assertRegex(self.migration, r'(?i)\bbegin;')
        self.assertRegex(self.migration, r'(?i)\bcommit;')
        self.assertIn('add column if not exists', self.migration)
        self.assertIn('on conflict(key) do nothing', self.migration)

    def test_phrasebook_migration_and_import_script(self):
        migration = (ROOT / 'sql/migrations/20261113_stage4_phrasebooks.sql').read_text(
            encoding='utf-8'
        )
        self.assertIn('create table if not exists public.phrasebook_rows', migration)
        self.assertIn('primary key (source_hash, row_id)', migration)
        self.assertIn('enable row level security', migration)
        self.assertTrue(migration.lstrip().lower().startswith('begin;'))
        self.assertTrue(migration.rstrip().lower().endswith('commit;'))
        self.assertIn('CC BY 4.0', (ROOT / 'README.md').read_text(encoding='utf-8'))

    def test_stage5_migration_and_atomic_skip(self):
        migration = (ROOT / 'sql/migrations/20261113_stage5_quality.sql').read_text(
            encoding='utf-8'
        )
        self.assertTrue(migration.lstrip().lower().startswith('begin;'))
        self.assertTrue(migration.rstrip().lower().endswith('commit;'))
        self.assertIn("file_name || '::' || row_id", migration)
        self.assertIn('last_skipped_fragment_pair_id', migration)
        self.assertIn('create or replace function public.skip_fragment(', migration)
        self.assertIn('create or replace function public.skip_fragment(', self.logic)
        self.assertIn('for update', migration)
        self.assertIn('public.skip_fragment(uuid, uuid)', migration)
        self.assertIn('public.skip_fragment(uuid,uuid)', self.logic)

    def test_only_available_pairs_are_offered(self):
        db = (ROOT / 'bot/db.py').read_text(encoding='utf-8')
        registration = (ROOT / 'bot/handlers/registration.py').read_text(encoding='utf-8')
        self.assertIn(".in_('status', ['collecting', 'confirmed'])", db)
        self.assertIn("Command('pair')", registration)
        self.assertIn('current_fragment_pair_id', registration)

    def test_expected_files(self):
        for filename in (
            'bot/db.py',
            'bot/texts.py',
            'bot/keyboards.py',
            'bot/main.py',
            'bot/handlers/registration.py',
            'bot/handlers/tasks.py',
            'scripts/smoke_test.py',
            'scripts/seed_demo.py',
            'PROMPT_TRANSLATION.md',
            'README.md',
            'PITCH_NOTES.md',
        ):
            with self.subTest(filename=filename):
                self.assertTrue((ROOT / filename).exists())


if __name__ == '__main__':
    unittest.main()
