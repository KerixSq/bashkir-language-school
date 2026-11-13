"""Real Compose stack, anonymous browser accounts, votes and persistent restart.

Requires Docker and a free loopback port 54321. Creates a unique Compose project,
never touches the normal project and never removes volumes. No mocked Auth/API.
"""

import re
import secrets
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    from scripts.create_docker_env import jwt

    subprocess.run(['docker', 'info'], check=True, stdout=subprocess.DEVNULL)
    with socket.socket() as probe:
        probe.bind(('127.0.0.1', 54321))  # Refuse to interfere with an existing stack.
    project = 'bsk-integration-' + secrets.token_hex(6)
    with tempfile.TemporaryDirectory() as directory:
        envfile = Path(directory) / '.env.docker'
        secret = secrets.token_hex(32)
        values = {
            key: secrets.token_hex(24)
            for key in ('POSTGRES_PASSWORD', 'AUTHENTICATOR_PASSWORD', 'AUTH_ADMIN_PASSWORD')
        }
        values.update(
            JWT_SECRET=secret,
            ANON_KEY=jwt(secret, 'anon'),
            SERVICE_ROLE_KEY=jwt(secret, 'service_role'),
            TELEGRAM_BOT_TOKEN='',
        )
        envfile.write_text(''.join(f'{k}={v}\n' for k, v in values.items()), encoding='utf-8')
        base = [
            'docker',
            'compose',
            '-p',
            project,
            '--env-file',
            str(envfile),
            '-f',
            str(ROOT / 'docker-compose.yml'),
        ]

        def compose(*args, stdin=None):
            result = subprocess.run(
                base + list(args), input=stdin, text=True, capture_output=True, cwd=ROOT
            )
            if result.returncode:
                # No credentials or SQL statements in exception/log output.
                detail = result.stderr
                for value in values.values():
                    if value:
                        detail = detail.replace(value, '[redacted]')
                raise RuntimeError(f'Compose {args[0]} failed: {detail[-5000:]}')
            return result.stdout

        def sql(statement):
            return compose(
                'exec',
                '-T',
                'db',
                'psql',
                '-U',
                'postgres',
                '-d',
                'bashkir',
                '-At',
                '-v',
                'ON_ERROR_STOP=1',
                stdin=statement,
            ).strip()

        try:
            compose('up', '-d', '--build', '--wait', '--wait-timeout', '240')
            print('PASS Docker: PostgreSQL, Auth, PostgREST, Nginx healthy')
            # Real, pinned BGPU data. The normal development database is not used.
            subprocess.run(
                [sys.executable, 'scripts/download_phrasebooks.py'], cwd=ROOT, check=True
            )
            compose(
                'run',
                '--rm',
                '--no-deps',
                'bot',
                'python',
                'scripts/import_phrasebooks.py',
                '--dir',
                'data/phrasebooks',
                '--bad-share',
                '0',
                '--seed',
                '42',
            )
            assert int(sql('select count(*) from phrasebook_rows;')) > 9000
            sql("update config set value='0' where key='bad_variant_probability';")
            sql("update config set value='5' where key='min_answer_seconds';")
            print('PASS real corpus imported with source-row mappings')

            with sync_playwright() as playwright:
                browser = playwright.chromium.launch()
                sessions = []
                pair = None
                for index in range(3):
                    context = browser.new_context(
                        viewport={'width': 390, 'height': 844}, reduced_motion='reduce'
                    )
                    # Block every external CDN, leave local Nginx/Auth/REST untouched.
                    context.route(
                        '**/*',
                        lambda route: (
                            route.abort()
                            if route.request.url.startswith('https://')
                            else route.continue_()
                        ),
                    )
                    page = context.new_page()
                    page.goto('http://127.0.0.1:54321/web/')
                    assert page.evaluate("typeof window.supabase?.createClient === 'function'")
                    page.locator('#web-nickname').fill(f'Integration {index}')
                    page.locator('#web-register').click()
                    expect(page.locator('#web-session')).to_be_visible(timeout=20000)
                    page.locator('#web-next').click()
                    expect(page.locator('#web-original')).not_to_be_empty()
                    original = page.locator('#web-original').inner_text()
                    if index == 0:
                        pair = original
                    assert original == pair, 'Started votes must be prioritised'
                    if index == 0:
                        page.locator('#web-confirm').click()
                        expect(page.locator('#web-status')).to_contain_text('Подожди')
                    time.sleep(6)
                    page.locator('#web-confirm').click()
                    expect(page.locator('#web-feedback')).to_contain_text('Ответ принят')
                    expect(page.locator('#web-points')).not_to_have_text('0')
                    expect(page.locator('#top-xp')).to_have_text('0')
                    expect(page.locator('#jury-ranking-list')).to_contain_text('Integration')
                    session = page.evaluate("""() => Object.values(localStorage).map(v=>{
                      try{return JSON.parse(v)}catch{return null}
                    }).find(v=>v?.access_token)""")
                    assert session and session['user']['is_anonymous']
                    sessions.append((context, page, session['access_token']))
                assert len({token for _, _, token in sessions}) == 3
                assert (
                    sql("select max(confirmed_count) from fragment_pairs where status='confirmed';")
                    == '3'
                )
                assert (
                    sql("select confirmed from adventure_progress where lang_pair='ba-ru';") == '1'
                )
                print('PASS CDN blocked: anonymous signup -> browser vote -> SQL consensus=3')

                context, page, token = sessions[0]
                headers = {'apikey': values['ANON_KEY'], 'Authorization': 'Bearer ' + token}
                export = context.request.get(
                    'http://127.0.0.1:54321/rest/v1/translations_export?status=eq.confirmed',
                    headers=headers,
                )
                assert export.ok
                rows = export.json()
                assert len(rows) == 1 and set(rows[0]) == {
                    'fragment_id',
                    'text_ba',
                    'lang_pair',
                    'translation',
                    'source',
                    'confirmed',
                    'status',
                }
                for auth in (values['ANON_KEY'], token):
                    denied = context.request.get(
                        'http://127.0.0.1:54321/rest/v1/users?select=*',
                        headers={'apikey': values['ANON_KEY'], 'Authorization': 'Bearer ' + auth},
                    )
                    assert denied.status in (401, 403)
                ratings = context.request.get(
                    'http://127.0.0.1:54321/rest/v1/leaderboard_users', headers=headers
                ).json()
                assert len(ratings) == 3
                assert all(
                    not set(r) & {'user_id', 'telegram_id', 'username', 'display_name'}
                    for r in ratings
                )
                print('PASS HTTP export, public fields and real RLS denial')
                confirmed_pair = sql("select id from fragment_pairs where status='confirmed';")
                duplicate = context.request.post(
                    'http://127.0.0.1:54321/rest/v1/rpc/web_submit_answer',
                    headers=headers,
                    data={
                        'p_fragment_pair_id': confirmed_pair,
                        'p_action': 'confirm',
                        'p_text': None,
                    },
                )
                assert duplicate.ok and duplicate.json()['duplicate'] is True
                context.set_offline(True)
                page.locator('#web-after-answer').click()
                expect(page.locator('#web-status')).to_have_class(re.compile('.*is-error.*'))
                context.set_offline(False)
                print('PASS fast answer, duplicate, network failure and training XP isolation')

                snapshot = sql('select count(*),sum(points_awarded) from answers;')
                compose('restart', 'db', 'auth', 'rest', 'app')
                compose('up', '-d', '--wait', '--wait-timeout', '180')
                assert sql('select count(*),sum(points_awarded) from answers;') == snapshot
                for context, page, token in sessions:
                    page.reload()
                    expect(page.locator('#web-session')).to_be_visible(timeout=20000)
                    expect(page.locator('#web-points')).not_to_have_text('0')
                    expect(page.locator('#top-xp')).to_have_text('0')
                    context.close()
                browser.close()
                print('PASS Docker restart preserves answers, points and browser Auth sessions')
        except Exception:
            logs = compose('logs', '--no-color', '--tail', '40', 'auth', 'db', 'rest', 'app')
            for value in values.values():
                if value:
                    logs = logs.replace(value, '[redacted]')
            print(logs, flush=True)
            raise
        finally:
            compose('down')  # Intentionally retain the unique project's volume.
            print('Retained integration volume for project:', project)


if __name__ == '__main__':
    main()
