"""Real REST, isolated technical fixtures, browser expert decision; no mocked successes."""

import hashlib
import os
import secrets
import sys
import threading
from datetime import datetime, timedelta, timezone
from functools import partial
from http.server import ThreadingHTTPServer

from browser_visual_checks import ROOT, QuietHandler
from playwright.sync_api import expect, sync_playwright

sys.path.insert(0, str(ROOT))
from scripts.common import client


def main():
    if os.environ.get('BASHKIR_QA_ISOLATED') != '1':
        raise SystemExit('SKIP: set BASHKIR_QA_ISOLATED=1 only for a dedicated QA database')
    api = client()
    code = secrets.token_urlsafe(32)
    previous = (
        api.table('config')
        .select('value')
        .eq('key', 'expert_access_hash')
        .single()
        .execute()
        .data['value']
    )
    users = []
    source = fragment = pair = None
    server = ThreadingHTTPServer(('127.0.0.1', 0), partial(QuietHandler, directory=str(ROOT)))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    variants = [
        'Technical expert review fixture variant A.',
        'Technical expert review fixture variant B.',
        'Unrelated technical QA value.',
    ]
    try:
        api.table('config').update({'value': hashlib.sha256(code.encode()).hexdigest()}).eq(
            'key', 'expert_access_hash'
        ).execute()
        source = (
            api.table('sources')
            .insert({'title': 'EXPERT QA TECHNICAL', 'kind': 'text', 'license': 'test'})
            .execute()
            .data[0]['id']
        )
        fragment = (
            api.table('fragments')
            .insert({'source_id': source, 'position': 1, 'text_ba': 'TECHNICAL EXPERT FIXTURE'})
            .execute()
            .data[0]['id']
        )
        pair = (
            api.table('fragment_pairs')
            .insert(
                {
                    'fragment_id': fragment,
                    'lang_pair': 'ba-ru',
                    'auto_translation': 'Технический исходный текст.',
                }
            )
            .execute()
            .data[0]['id']
        )
        ago = (datetime.now(timezone.utc) - timedelta(seconds=30)).isoformat()
        for index in range(6):
            user = (
                api.table('users')
                .insert(
                    {
                        'telegram_id': -(8_800_000_000_000 + secrets.randbelow(100_000_000)),
                        'nickname': 'Expert QA',
                        'role': 'student',
                        'lang_pair': 'ba-ru',
                        'state': 'awaiting_correction',
                        'current_fragment_pair_id': pair,
                        'current_shown_variant': 'auto',
                        'current_shown_at': ago,
                    }
                )
                .execute()
                .data[0]['id']
            )
            users.append(user)
            api.rpc(
                'submit_answer',
                {
                    'p_user_id': user,
                    'p_fragment_pair_id': pair,
                    'p_action': 'correct',
                    'p_text': variants[index % 3],
                },
            ).execute()
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            page = browser.new_page(viewport={'width': 390, 'height': 844}, reduced_motion='reduce')
            errors = []
            page.on('pageerror', lambda error: errors.append(str(error)))
            page.goto(f'http://127.0.0.1:{server.server_port}/web/')
            page.locator('#toggle-connection').click()
            page.locator('#supabase-url').fill(os.environ['SUPABASE_URL'])
            page.locator('#supabase-key').fill(os.environ['SUPABASE_PUBLIC_KEY'])
            page.locator('#connect').click()
            page.locator('#tab-expert').click()
            page.locator('#expert-code').fill('wrong')
            page.locator('#load-expert').click()
            expect(page.locator('#notice')).to_contain_text('Неверный код')
            page.locator('#expert-code').fill(code)
            page.locator('#load-expert').click()
            card = page.locator('#expert-queue article').filter(has_text='TECHNICAL EXPERT FIXTURE')
            card.locator('.expert-similarity summary').click()
            expect(card.locator('.expert-similarity')).to_contain_text(
                'Текстовое сходство pg_trgm:'
            )
            expect(card.locator('.expert-similarity')).to_contain_text('голосов: 2')
            assert (
                api.table('fragment_pairs')
                .select('status')
                .eq('id', pair)
                .single()
                .execute()
                .data['status']
                == 'expert_review'
            )
            card.locator('input[type=radio]').first.check()
            chosen = card.locator('textarea').input_value()
            out = ROOT / 'test-results/visual'
            out.mkdir(parents=True, exist_ok=True)
            page.screenshot(path=str(out / 'expert-similarity-mobile.png'))
            card.get_by_role('button', name='Утвердить перевод').click()
            expect(card).to_have_count(0)
            exported = (
                api.table('translations_export')
                .select('*')
                .eq('fragment_id', fragment)
                .single()
                .execute()
                .data
            )
            assert exported['translation'] == chosen and exported['status'] == 'confirmed'
            assert len(exported) == 7
            assert not errors, errors
            browser.close()
        print(
            'PASS real expert REST/browser: denied code, similarity/votes, manual decision, 7-field export'
        )
    finally:
        api.table('config').update({'value': previous}).eq('key', 'expert_access_hash').execute()
        for table, column, values in [
            ('user_badges', 'user_id', users),
            ('answers', 'user_id', users),
            ('users', 'id', users),
            ('expert_decisions', 'fragment_pair_id', [pair]),
            ('status_history', 'fragment_pair_id', [pair]),
            ('fragment_pairs', 'id', [pair]),
            ('fragments', 'id', [fragment]),
            ('sources', 'id', [source]),
        ]:
            ids = [value for value in values if value]
            if ids:
                api.table(table).delete().in_(column, ids).execute()
        server.shutdown()
        server.server_close()


if __name__ == '__main__':
    main()
