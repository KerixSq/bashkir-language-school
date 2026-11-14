"""Real PostgreSQL checks in a newly created disposable database.

Set PG_TEST_ADMIN_DSN to a local administrator connection. Only the randomly
named database created by this process is dropped. No application DB is reset.
"""

import os
import unittest
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import psycopg
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict, make_conninfo

ROOT = Path(__file__).resolve().parents[1]


class PostgreSQLTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        admin_dsn = os.environ.get('PG_TEST_ADMIN_DSN')
        if not admin_dsn:
            raise unittest.SkipTest('PG_TEST_ADMIN_DSN is required; PostgreSQL was NOT RUN')
        info = conninfo_to_dict(admin_dsn)
        if info.get('host') not in ('localhost', '127.0.0.1', '::1'):
            raise RuntimeError('Tests require an explicitly local PostgreSQL host')
        cls.admin = psycopg.connect(admin_dsn, autocommit=True)
        cls.database = 'bsk_check_' + uuid.uuid4().hex
        # Supabase creates these roles. A standalone test cluster needs them too.
        roles = {r[0] for r in cls.admin.execute('select rolname from pg_roles')}
        if not {'anon', 'authenticated', 'service_role'} <= roles:
            cls.admin.close()
            raise RuntimeError('Create the anon, authenticated and service_role roles first')
        cls.admin.execute(
            sql.SQL(
                "create database {} template template0 encoding 'UTF8' "
                "locale_provider icu icu_locale 'ru-RU'"
            ).format(sql.Identifier(cls.database))
        )
        cls.dsn = make_conninfo(admin_dsn, dbname=cls.database)
        cls.addClassCleanup(cls.remove_database)
        with psycopg.connect(cls.dsn, autocommit=True) as db:
            db.execute('grant usage on schema public to anon,authenticated,service_role')
            for name in ('schema.sql', 'seed.sql', 'logic.sql'):
                db.execute((ROOT / 'sql' / name).read_text(encoding='utf-8'))

    @classmethod
    def remove_database(cls):
        cls.admin.execute(
            sql.SQL('drop database {} with (force)').format(sql.Identifier(cls.database))
        )
        cls.admin.close()

    def setUp(self):
        self.db = psycopg.connect(self.dsn, autocommit=True)
        self.addCleanup(self.db.close)
        school = self.scalar("insert into public.schools(name) values ('Integration') returning id")
        code = uuid.uuid4().hex[:8].upper().replace('0', 'X').replace('1', 'Y')
        self.room = self.scalar(
            'insert into public.classes(school_id,name,join_code,teacher_code) '
            "values (%s,'Integration',%s,%s) returning id",
            (school, code, uuid.uuid4().hex),
        )
        self.source = self.scalar(
            'insert into public.sources(title,kind,license) '
            "values ('Integration','text','test') returning id"
        )

    def scalar(self, query, args=()):
        return self.db.execute(query, args).fetchone()[0]

    def pair(self):
        fragment = self.scalar(
            'insert into public.fragments(source_id,text_ba,position) '
            "values (%s,'TECHNICAL FIXTURE',1) returning id",
            (self.source,),
        )
        return self.scalar(
            'insert into public.fragment_pairs(fragment_id,lang_pair,auto_translation,'
            "bad_translation) values (%s,'ba-ru','Исходный текст.','Подставной текст.') "
            'returning id',
            (fragment,),
        )

    def user(self):
        return self.scalar(
            'insert into public.users(telegram_id,nickname,role,class_id,lang_pair) '
            "values (%s,'Integration','student',%s,'ba-ru') returning id",
            (-uuid.uuid4().int % (2**60) - 2**60, self.room),
        )

    def test_independent_student_and_teacher_class_guard(self):
        user = self.user()
        self.pair()
        self.db.execute('update users set class_id=null where id=%s', (user,))
        task = self.scalar('select public.get_next_fragment(%s)', (user,))
        self.assertIsNotNone(task)
        migration = (ROOT / 'sql/migrations/20261114_stage11_independent_students.sql').read_text(
            encoding='utf-8'
        )
        self.db.execute(migration)
        self.db.execute(migration)
        self.db.execute("update users set role='teacher' where id=%s", (user,))
        with self.assertRaisesRegex(psycopg.Error, 'Завершите регистрацию'):
            self.scalar('select public.get_next_fragment(%s)', (user,))

    def test_original_audio_import_transaction_and_task_metadata(self):
        import sys
        import tempfile

        from audio_fixture import audio_fixture
        from psycopg.types.json import Jsonb

        sys.path.insert(0, str(ROOT))
        from scripts.import_audio import plan

        with tempfile.TemporaryDirectory() as directory:
            audio, annotation, _ = audio_fixture(Path(directory))
            source, segments = plan(audio, annotation, 'Technical QA tone, not speech', 'CC0 test')
        migration = (ROOT / 'sql/migrations/20261114_stage13_original_audio.sql').read_text(
            encoding='utf-8'
        )
        self.db.execute(migration)
        self.db.execute(migration)
        for _ in range(2):
            self.scalar('select import_audio_fragments(%s,%s)', (Jsonb(source), Jsonb(segments)))
        pair = segments[0]['pair_id']
        self.assertEqual(
            self.scalar('select count(*) from fragments where source_id=%s', (source['id'],)), 1
        )
        self.assertEqual(self.scalar('select count(*) from fragment_pairs where id=%s', (pair,)), 1)
        self.db.execute('set role anon')
        try:
            with self.assertRaises(psycopg.errors.InsufficientPrivilege):
                self.scalar(
                    'select import_audio_fragments(%s,%s)', (Jsonb(source), Jsonb(segments))
                )
        finally:
            self.db.execute('reset role')
        broken_source = {**source, 'id': str(uuid.uuid4())}
        broken_rows = [
            {**segments[0], 'id': str(uuid.uuid4()), 'pair_id': str(uuid.uuid4()), 'time_end': -1}
        ]
        with self.assertRaisesRegex(psycopg.Error, 'Invalid audio segment'):
            self.scalar(
                'select import_audio_fragments(%s,%s)', (Jsonb(broken_source), Jsonb(broken_rows))
            )
        self.assertEqual(
            self.scalar('select count(*) from sources where id=%s', (broken_source['id'],)), 0
        )
        for _ in range(3):
            user = self.user()
            self.assign(user, pair)
            task = self.scalar('select get_next_fragment(%s)', (user,))
            self.assertEqual(task['source_kind'], 'audio')
            self.assertEqual(task['source_url'], source['url'])
            self.assertEqual((task['time_start'], task['time_end']), (0.2, 0.7))
            self.vote(user, pair)
        self.scalar('select import_audio_fragments(%s,%s)', (Jsonb(source), Jsonb(segments)))
        row = self.db.execute(
            'select translation,source,status,confirmed from translations_export where fragment_id=%s',
            (segments[0]['id'],),
        ).fetchone()
        self.assertEqual((row[0], row[2], row[3]), (segments[0]['translation'], 'confirmed', 3))
        self.assertIn('сек.', row[1])
        with self.assertRaisesRegex(psycopg.Error, 'Audio translation conflict'):
            self.scalar(
                'select import_audio_fragments(%s,%s)',
                (
                    Jsonb(source),
                    Jsonb([{**segments[0], 'translation': 'Different technical text'}]),
                ),
            )

    def test_expert_similarity_is_advisory_and_resolution_is_stable(self):
        pair, untouched = self.pair(), self.pair()
        code = uuid.uuid4().hex
        self.db.execute(
            "update config set value=private.secret_hash(%s) where key='expert_access_hash'",
            (code,),
        )
        synonyms_before = self.scalar('select count(*) from synonym_map')
        variants = [
            'Technical expert review fixture variant A.',
            'Technical expert review fixture variant B.',
            'Unrelated technical QA value.',
        ]
        people = []
        for index in range(6):
            user = self.user()
            people.append(user)
            self.assign(user, pair, correction=True)
            self.vote(user, pair, variants[index % 3])
        self.assertEqual(
            self.scalar('select status from fragment_pairs where id=%s', (pair,)), 'expert_review'
        )
        snapshot = self.scalar('select sum(points) from users')
        migration = (ROOT / 'sql/migrations/20261114_stage12_expert_similarity.sql').read_text(
            encoding='utf-8'
        )
        self.db.execute(migration)
        self.db.execute(migration)
        with self.assertRaisesRegex(psycopg.Error, 'Неверный код'):
            self.scalar('select expert_list_queue(%s)', ('wrong',))
        with self.assertRaisesRegex(psycopg.Error, 'Неверный код'):
            self.scalar('select expert_resolve(%s,%s,%s)', ('wrong', pair, variants[0]))
        queue = self.scalar('select expert_list_queue(%s)', (code,))
        item = next(row for row in queue if row['fragment_pair_id'] == str(pair))
        self.assertTrue(item['similar_variants'])
        self.assertTrue(item['similarity_candidates'])
        candidate = next(
            row
            for row in item['similarity_candidates']
            if {row['left_translation'], row['right_translation']} == set(variants[:2])
        )
        self.assertEqual((candidate['left_votes'], candidate['right_votes']), (2, 2))
        self.assertGreaterEqual(candidate['similarity'], 0.65)
        self.assertLessEqual(candidate['similarity'], 1)
        self.assertEqual(self.scalar('select sum(points) from users'), snapshot)
        self.assertEqual(self.scalar('select count(*) from synonym_map'), synonyms_before)
        self.scalar('select expert_resolve(%s,%s,%s)', (code, pair, variants[0]))
        result = self.db.execute(
            'select status,final_translation,resolved_by from fragment_pairs where id=%s', (pair,)
        ).fetchone()
        self.assertEqual(result, ('confirmed', variants[0], 'expert'))
        self.assertEqual(
            self.scalar(
                'select translation from translations_export where fragment_id=(select fragment_id from fragment_pairs where id=%s)',
                (pair,),
            ),
            variants[0],
        )
        points = self.scalar('select sum(points) from users')
        with self.assertRaisesRegex(psycopg.Error, 'очереди экспертов'):
            self.scalar('select expert_resolve(%s,%s,%s)', (code, pair, variants[1]))
        self.scalar('select private.reconcile_fragment(%s)', (pair,))
        self.assertEqual(self.scalar('select sum(points) from users'), points)
        self.assertEqual(
            self.db.execute(
                'select status,final_translation,resolved_by from fragment_pairs where id=%s',
                (pair,),
            ).fetchone(),
            result,
        )
        self.assertEqual(
            self.scalar('select status from fragment_pairs where id=%s', (untouched,)), 'collecting'
        )
        self.assertEqual(
            self.scalar('select count(*) from expert_decisions where fragment_pair_id=%s', (pair,)),
            1,
        )

    def assign(self, user, pair, variant='auto', correction=False):
        self.db.execute(
            'update public.users set current_fragment_pair_id=%s,'
            "current_shown_variant=%s,current_shown_at=now()-interval '1 minute',"
            "last_answer_at=now()-interval '1 minute',state=%s where id=%s",
            (pair, variant, 'awaiting_correction' if correction else 'idle', user),
        )

    def vote(self, user, pair, text=None):
        with psycopg.connect(self.dsn, autocommit=True) as db:
            db.execute("set statement_timeout='10s'")
            db.execute('set role service_role')
            return db.execute(
                'select public.submit_answer(%s,%s,%s,%s)',
                (user, pair, 'correct' if text else 'confirm', text),
            ).fetchone()[0]

    def test_concurrent_duplicate_is_counted_once(self):
        pair, user = self.pair(), self.user()
        self.assign(user, pair)
        with ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(lambda _: self.vote(user, pair), range(16)))
        self.assertEqual(sum(bool(r.get('duplicate')) for r in results), 15)
        self.assertEqual(
            self.scalar('select count(*) from public.answers where user_id=%s', (user,)), 1
        )
        self.assertEqual(self.scalar('select points from public.users where id=%s', (user,)), 10)

    def test_concurrent_consensus_and_readable_translation(self):
        pair = self.pair()
        users = [self.user() for _ in range(3)]
        for user in users:
            self.assign(user, pair, correction=True)
        with ThreadPoolExecutor(max_workers=3) as pool:
            list(pool.map(lambda user: self.vote(user, pair, 'Читаемый перевод!'), users))
        self.assertEqual(
            self.db.execute(
                'select status,final_translation,confirmed_count '
                'from public.fragment_pairs where id=%s',
                (pair,),
            ).fetchone(),
            ('confirmed', 'Читаемый перевод!', 3),
        )
        self.assertEqual(
            self.scalar('select sum(points) from public.users where id=any(%s)', (users,)), 45
        )

    def test_leader_change_removes_old_bonus(self):
        pair = self.pair()
        first = []
        for text in ['Вариант А.'] * 3 + ['Вариант Б.'] * 5:
            user = self.user()
            self.assign(user, pair, correction=True)
            self.vote(user, pair, text)
            if text == 'Вариант А.':
                first.append(user)
        self.assertEqual(
            self.scalar('select final_translation from public.fragment_pairs where id=%s', (pair,)),
            'Вариант Б.',
        )
        self.assertEqual(
            self.scalar('select sum(points) from public.users where id=any(%s)', (first,)), 30
        )

    def test_stale_correction_does_not_restore_fsm(self):
        pair, user = self.pair(), self.user()
        self.assign(user, pair)
        self.vote(user, pair)
        self.assertFalse(self.scalar('select public.begin_correction(%s,%s)', (user, pair)))
        self.assertEqual(self.scalar('select state from public.users where id=%s', (user,)), 'idle')

    def test_correction_and_confirm_race(self):
        pair, user = self.pair(), self.user()
        self.assign(user, pair)

        def begin():
            with psycopg.connect(self.dsn, autocommit=True) as db:
                return db.execute('select public.begin_correction(%s,%s)', (user, pair)).fetchone()[
                    0
                ]

        def confirm():
            try:
                return self.vote(user, pair)
            except psycopg.errors.RaiseException:
                return None  # Correction acquired the row first; confirmation is rejected.

        with ThreadPoolExecutor(max_workers=2) as pool:
            left, right = pool.submit(begin), pool.submit(confirm)
            left.result()
            right.result()
        state, current = self.db.execute(
            'select state,current_fragment_pair_id from public.users where id=%s', (user,)
        ).fetchone()
        count = self.scalar('select count(*) from public.answers where user_id=%s', (user,))
        self.assertIn(
            (state, current, count), [('idle', None, 1), ('awaiting_correction', pair, 0)]
        )

    def test_migration_twice_preserves_answers(self):
        pair, user = self.pair(), self.user()
        self.assign(user, pair)
        self.vote(user, pair)
        before = self.db.execute(
            'select * from public.answers where user_id=%s', (user,)
        ).fetchall()
        migration = (ROOT / 'sql/migrations/20261113_stage7_runtime_fixes.sql').read_text(
            encoding='utf-8'
        )
        self.db.execute(migration)
        self.db.execute(migration)
        self.assertEqual(
            before,
            self.db.execute('select * from public.answers where user_id=%s', (user,)).fetchall(),
        )

    def test_public_permissions_and_fields(self):
        for function in (
            'get_next_fragment(uuid)',
            'begin_correction(uuid,uuid)',
            'submit_answer(uuid,uuid,text,text)',
            'skip_fragment(uuid,uuid)',
        ):
            self.assertFalse(
                self.scalar(
                    "select has_function_privilege('anon',%s,'EXECUTE')", ('public.' + function,)
                )
            )
        for view in (
            'leaderboard_users',
            'leaderboard_classes',
            'leaderboard_schools',
            'adventure_progress',
            'translations_export',
        ):
            columns = {
                r[0]
                for r in self.db.execute(
                    'select column_name from information_schema.columns '
                    "where table_schema='public' and table_name=%s",
                    (view,),
                )
            }
            self.assertFalse(columns & {'user_id', 'telegram_id', 'username', 'display_name'})

    def test_points_are_scoped_to_selected_period(self):
        user = self.user()
        first, second = self.pair(), self.pair()
        self.assign(user, first)
        self.vote(user, first)
        self.assign(user, second)
        self.vote(user, second)
        self.db.execute(
            "update public.answers set created_at=date_trunc('year',now())-interval '1 day' where fragment_pair_id=%s",
            (first,),
        )
        row = self.db.execute(
            "select points,day_points,year_points from public.leaderboard_users where name='Integration' and points=20 order by day_points desc limit 1"
        ).fetchone()
        self.assertEqual(row, (20, 10, 10))
        migration = (ROOT / 'sql/migrations/20261114_stage10_period_points.sql').read_text(
            encoding='utf-8'
        )
        self.db.execute(migration)
        self.db.execute(migration)


if __name__ == '__main__':
    unittest.main(verbosity=2)
