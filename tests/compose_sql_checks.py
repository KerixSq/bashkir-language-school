import json
import os
import uuid
from pathlib import Path

import psycopg
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict, make_conninfo

root = Path(__file__).resolve().parents[1]
dsn = os.environ['PG_TEST_ADMIN_DSN']

if conninfo_to_dict(dsn).get('host') not in ('127.0.0.1', 'localhost', '::1'):
    raise ValueError('Local test database required')
admin = psycopg.connect(dsn, autocommit=True)
if not admin.execute("select 1 from pg_roles where rolname='supabase_auth_admin'").fetchone():
    admin.execute('create role supabase_auth_admin login')
name = 'bsk_fix_' + uuid.uuid4().hex
admin.execute(
    sql.SQL("create database {} template template0 locale_provider icu icu_locale 'ru-RU'").format(
        sql.Identifier(name)
    )
)
try:
    with psycopg.connect(make_conninfo(dsn, dbname=name), autocommit=True) as db:
        db.execute(
            'create schema auth authorization supabase_auth_admin; grant usage on schema auth,public to authenticated,anon,service_role'
        )
        db.execute(
            "create function auth.uid() returns uuid language sql stable as $$ select (current_setting('request.jwt.claims',true)::jsonb->>'sub')::uuid $$"
        )
        db.execute('set role supabase_auth_admin')
        try:
            db.execute(
                "create or replace function auth.uid() returns uuid language sql stable as $$ select (current_setting('request.jwt.claims',true)::jsonb->>'sub')::uuid $$"
            )
            raise AssertionError('Expected original ownership failure')
        except psycopg.errors.InsufficientPrivilege:
            print('REPRODUCED original GoTrue auth.uid owner failure (42501)')
        db.execute('reset role')
        for _ in range(2):
            db.execute(
                (root / 'sql/migrations/20261114_stage9_auth_owner.sql').read_text(encoding='utf-8')
            )
        db.execute('set role supabase_auth_admin')
        db.execute(
            "create or replace function auth.uid() returns uuid language sql stable as $$ select (current_setting('request.jwt.claims',true)::jsonb->>'sub')::uuid $$"
        )
        db.execute('reset role')
        print('PASS owner migration twice; GoTrue role can replace auth.uid')
        for f in ['schema.sql', 'seed.sql', 'logic.sql']:
            db.execute((root / 'sql' / f).read_text(encoding='utf-8'))
        print('PASS complete current schema/seed/logic installation on PostgreSQL 17.12')
        # Only a real, source-attributed corpus phrase; three technical auth IDs.
        deck = json.loads((root / 'web/assets/learning-deck.json').read_text(encoding='utf-8'))
        phrase = next(r for r in deck['items'] if r['lang_pair'] == 'ba-ru')
        source = db.execute(
            "insert into sources(title,kind,license) values ('Technical integration with BGPU phrase','text','CC BY 4.0') returning id"
        ).fetchone()[0]
        frag = db.execute(
            'insert into fragments(source_id,text_ba,chapter,position) values (%s,%s,%s,1) returning id',
            (source, phrase['text_ba'], phrase['source']),
        ).fetchone()[0]
        pair = db.execute(
            "insert into fragment_pairs(fragment_id,lang_pair,auto_translation) values (%s,'ba-ru',%s) returning id",
            (frag, phrase['translation']),
        ).fetchone()[0]
        for i in range(3):
            db.execute('set role authenticated')
            db.execute(
                "select set_config('request.jwt.claims',%s,false)",
                (json.dumps({'sub': str(uuid.uuid4()), 'role': 'authenticated'}),),
            )
            db.execute("select web_register(%s,'ba-ru',null)", (f'Test Student {i}',))
            task = db.execute('select web_next_fragment()').fetchone()[0]
            assert task['fragment_pair_id'] == str(pair)
            db.execute('reset role')
            db.execute(
                "update users set current_shown_at=now()-interval '10 seconds' where current_fragment_pair_id=%s",
                (pair,),
            )
            db.execute('set role authenticated')
            db.execute("select web_submit_answer(%s,'confirm',null)", (pair,))
            db.execute('reset role')
        assert db.execute(
            'select status,confirmed_count from fragment_pairs where id=%s', (pair,)
        ).fetchone() == ('confirmed', 3)
        print('PASS three independent authenticated SQL identities -> web RPC -> confirmed=3')
finally:
    admin.execute(sql.SQL('drop database {} with (force)').format(sql.Identifier(name)))
    admin.close()
