"""Real REST + browser checks with isolated, explicitly technical fixtures."""

import csv
import io
import os
import secrets
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from playwright.sync_api import expect, sync_playwright

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from browser_checks import URL, lesson

from scripts.common import client
from scripts.pure import new_join_code


def main():
    api = client()
    saved = {}
    users = []
    stamp = secrets.token_hex(5)
    try:
        saved['school'] = (
            api.table('schools').insert({'name': 'Browser integration'}).execute().data[0]['id']
        )
        room = (
            api.table('classes')
            .insert(
                {
                    'school_id': saved['school'],
                    'name': 'Browser integration',
                    'join_code': new_join_code(),
                    'teacher_code': secrets.token_urlsafe(32),
                }
            )
            .execute()
            .data[0]
        )
        saved['room'] = room['id']
        saved['source'] = (
            api.table('sources')
            .insert(
                {'title': 'Browser technical fixture ' + stamp, 'kind': 'text', 'license': 'test'}
            )
            .execute()
            .data[0]['id']
        )
        saved['fragment'] = (
            api.table('fragments')
            .insert(
                {
                    'source_id': saved['source'],
                    'position': 1,
                    'text_ba': 'TECHNICAL BROWSER FIXTURE ' + stamp,
                }
            )
            .execute()
            .data[0]['id']
        )
        saved['pair'] = (
            api.table('fragment_pairs')
            .insert(
                {
                    'fragment_id': saved['fragment'],
                    'lang_pair': 'ba-ru',
                    'auto_translation': 'Технический перевод.',
                }
            )
            .execute()
            .data[0]['id']
        )
        for index in range(3):
            users.append(
                api.table('users')
                .insert(
                    {
                        'telegram_id': -(7_000_000_000_000 + secrets.randbelow(100_000_000)),
                        'nickname': f'Browser {index}',
                        'role': 'student',
                        'class_id': saved['room'],
                        'lang_pair': 'ba-ru',
                    }
                )
                .execute()
                .data[0]['id']
            )

        def progress():
            return (
                api.table('adventure_progress')
                .select('confirmed')
                .eq('lang_pair', 'ba-ru')
                .single()
                .execute()
                .data['confirmed']
            )

        before = progress()
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(
            **({'executable_path': os.environ['BROWSER_EXECUTABLE']} if os.getenv('BROWSER_EXECUTABLE') else {})
        )
            context = browser.new_context(
                viewport={'width': 390, 'height': 844}, reduced_motion='reduce'
            )
            page = context.new_page()
            errors = []
            page.on('pageerror', lambda error: errors.append(str(error)))
            page.goto(URL)
            page.locator('#toggle-connection').click()
            page.locator('#supabase-url').fill(os.environ['SUPABASE_URL'])
            page.locator('#supabase-key').fill(os.environ['SUPABASE_PUBLIC_KEY'])
            page.locator('#connect').click()
            expect(page.locator('#community-confirmed')).to_have_text(str(before))
            for user in users:
                api.table('users').update(
                    {
                        'current_fragment_pair_id': saved['pair'],
                        'current_shown_variant': 'auto',
                        'current_shown_at': (
                            datetime.now(timezone.utc) - timedelta(seconds=10)
                        ).isoformat(),
                    }
                ).eq('id', user).execute()
                api.rpc(
                    'submit_answer',
                    {
                        'p_user_id': user,
                        'p_fragment_pair_id': saved['pair'],
                        'p_action': 'confirm',
                        'p_text': None,
                    },
                ).execute()
            page.locator('#community-refresh').click()
            expect(page.locator('#community-confirmed')).to_have_text(str(before + 1))
            expect(page.locator('#community-gate-1')).to_have_class(
                'unlocked newly-unlocked' if before == 0 else 'unlocked'
            )
            page.reload()
            expect(page.locator('#community-confirmed')).to_have_text(str(before + 1))
            assert 'newly-unlocked' not in (
                page.locator('#community-gate-1').get_attribute('class') or ''
            )
            lesson(page)
            assert progress() == before + 1
            page.locator('#tab-translations').click()
            page.locator('#search').fill(stamp)
            page.locator('#find').click()
            expect(page.locator('#translations-table')).to_contain_text('Технический перевод.')
            with page.expect_download() as download:
                page.locator('#download-translations').click()
            rows = list(
                csv.reader(io.StringIO(Path(download.value.path()).read_text(encoding='utf-8-sig')))
            )
            assert len(rows[0]) == 7 and len(rows) == 2 and rows[1][5:7] == ['3', 'confirmed']
            page.locator('#tab-teacher').click()
            page.locator('#teacher-code').fill(room['teacher_code'])
            page.locator('#load-report').click()
            expect(page.locator('#report-content')).to_contain_text('Browser integration')
            expect(page.locator('#download-report')).to_be_visible()
            page.locator('#teacher-code').fill(room['join_code'])
            page.locator('#load-report').click()
            expect(page.locator('#report-content')).to_contain_text('Неверный код')
            expect(page.locator('#download-report')).to_be_hidden()
            context.set_offline(True)
            page.locator('#community-refresh').click()
            expect(page.locator('#community-status')).to_contain_text('Ошибка сети')
            assert 'unlocked' not in (
                page.locator('#community-gate-1').get_attribute('class') or ''
            )
            context.set_offline(False)
            page.locator('#community-refresh').click()
            expect(page.locator('#community-confirmed')).to_have_text(str(before + 1))
            assert not errors, errors
            browser.close()
        print(
            'PASS real REST + browser: 3 votes, chapter opens once, local XP isolation, CSV, protected report, offline recovery'
        )
    finally:
        for table, field, values in [
            ('user_badges', 'user_id', users),
            ('answers', 'user_id', users),
            ('users', 'id', users),
            ('status_history', 'fragment_pair_id', [saved.get('pair')]),
            ('fragment_pairs', 'id', [saved.get('pair')]),
            ('fragments', 'id', [saved.get('fragment')]),
            ('sources', 'id', [saved.get('source')]),
            ('classes', 'id', [saved.get('room')]),
            ('schools', 'id', [saved.get('school')]),
        ]:
            values = [value for value in values if value]
            if values:
                api.table(table).delete().in_(field, values).execute()


if __name__ == '__main__':
    main()
