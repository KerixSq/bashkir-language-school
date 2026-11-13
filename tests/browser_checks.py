"""Browser interactions against the real static site; no mocked API successes.

Run a local server, then: python tests/browser_checks.py
Optional WEB_TEST_URL and WEB_SCREENSHOT_DIR override the local defaults.
"""

import json
import os
from pathlib import Path

from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[1]
URL = os.getenv('WEB_TEST_URL', 'http://127.0.0.1:8000/web/')
DECK = json.loads((ROOT / 'web/assets/learning-deck.json').read_text(encoding='utf-8'))
TRANSLATIONS = {(r['lang_pair'], r['text_ba']): r['translation'] for r in DECK['items']}
SCREENSHOTS = Path(os.getenv('WEB_SCREENSHOT_DIR', str(ROOT / 'test-results')))


def lesson(page, pair='ba-ru', wrong_first=False):
    page.locator('#game-pair').select_option(pair)
    page.locator('#game-start').click()
    missed = None
    for index in range(5):
        expect(page.locator('#game-question-count')).to_have_text(f'{index + 1} / 5')
        phrase = page.locator('#game-bashkir-text').inner_text()
        translation = TRANSLATIONS[(pair, phrase)]
        kind = page.locator('#game-question-type').inner_text()
        area = page.locator('#game-answers')
        if wrong_first and index == 0:
            missed = phrase
            if kind == 'Выбери перевод':
                options = area.locator('button').all()
                next(button for button in options if button.inner_text() != translation).click()
            else:
                area.locator('textarea').fill('TECHNICAL WRONG ANSWER')
        elif kind == 'Выбери перевод':
            area.get_by_role('button', name=translation, exact=True).click()
        elif kind == 'Есть ли ошибка?':
            shown = area.locator('.game-word-card').inner_text()
            area.get_by_role(
                'button', name='Да, верно' if shown == translation else 'Есть ошибка', exact=True
            ).click()
        elif kind == 'Собери перевод':
            for token in translation.split():
                area.locator('.game-word-bank').get_by_role(
                    'button', name=token, exact=True
                ).first.click()
        else:
            area.locator('textarea').fill(translation)
        page.locator('#game-check').click()
        expect(page.locator('#game-feedback')).to_be_visible()
        if not (wrong_first and index == 0):
            expect(page.locator('#game-feedback')).to_contain_text('Верно по варианту корпуса')
        # A queued double click must not skip the next task.
        page.locator('#game-next').evaluate('(button) => { button.click(); button.click(); }')
    expect(page.locator('#game-finish')).to_be_visible()
    return missed


def main():
    SCREENSHOTS.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            **(
                {'executable_path': os.environ['BROWSER_EXECUTABLE']}
                if os.getenv('BROWSER_EXECUTABLE')
                else {}
            )
        )
        for width in (360, 390, 430, 768, 1280):
            context = browser.new_context(
                viewport={'width': width, 'height': 900}, reduced_motion='reduce'
            )
            page = context.new_page()
            errors = []
            page.on('pageerror', lambda error: errors.append(str(error)))
            page.goto(URL)
            expect(page.locator('#game-ready')).to_be_visible()
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
            page.locator('img').evaluate_all(
                "(items) => items.forEach(img => img.loading = 'eager')"
            )
            page.wait_for_function(
                '[...document.images].every(img => img.complete && img.naturalWidth > 0)'
            )
            missed = lesson(page, 'ba-kk' if width == 430 else 'ba-ru', wrong_first=width == 360)
            saved = page.evaluate("JSON.parse(localStorage.getItem('bashkir_story_game_v1'))")
            assert saved['answers'] == 5 and saved['xp'] == (62 if missed else 75)
            page.reload()
            expect(page.locator('#game-score')).to_have_text(str(saved['xp']))
            if missed:
                page.locator('#game-start').click()
                expect(page.locator('#game-bashkir-text')).to_have_text(missed)
                page.reload()
            page.locator('#tab-ratings').click()
            expect(page.locator('#notice')).to_contain_text('подключи публичный ключ')
            page.locator('#tab-ratings').press('ArrowRight')
            expect(page.locator('#tab-translations')).to_be_focused()
            page.locator('#tab-teacher').click()
            page.locator('#load-report').click()
            expect(page.locator('#report-content')).to_contain_text('Введи секретный код')
            page.locator('#tab-expert').click()
            page.locator('#load-expert').click()
            expect(page.locator('#expert-queue')).to_contain_text('Введи отдельный код')
            page.locator('#tab-api').click()
            expect(page.locator('#api-example')).to_contain_text('translations_export')
            page.locator('#community-refresh').click()
            expect(page.locator('#community-status')).to_contain_text('Подключи публичный API')
            page.locator('#toggle-connection').click()
            page.locator('#supabase-key').fill('sb_secret_test-key-must-be-rejected')
            page.locator('#connect').click()
            expect(page.locator('#notice')).to_contain_text('Секретный ключ')
            page.locator('#supabase-key').fill('')
            page.locator('#toggle-connection').click()
            page.screenshot(path=str(SCREENSHOTS / f'web-{width}.png'), full_page=True)
            assert not errors, errors
            print(f'PASS viewport {width}: lesson, persistence, review, tabs, errors, key guard')
            context.close()

        context = browser.new_context()
        page = context.new_page()
        errors = []
        page.on('pageerror', lambda error: errors.append(str(error)))
        page.add_init_script(
            "localStorage.setItem('bashkir_story_game_v1', JSON.stringify({mastered:null,seen:[],xp:-5,mistakes:null}))"
        )
        page.goto(URL)
        expect(page.locator('#game-ready')).to_be_visible()
        expect(page.locator('#game-score')).to_have_text('0')
        assert not errors, errors
        print('PASS malformed local profile recovers')
        context.close()

        context = browser.new_context()
        page = context.new_page()
        # Simulate an unavailable file, never a successful backend result.
        page.route('**/learning-deck.json', lambda route: route.abort())
        page.goto(URL)
        expect(page.locator('#game-empty')).to_be_visible()
        page.locator('#game-local-file').set_input_files(
            {'name': 'invalid.json', 'mimeType': 'application/json', 'buffer': b'{broken'}
        )
        expect(page.locator('#game-empty-reason')).to_contain_text('Не получилось открыть JSON')
        page.locator('#game-local-file').set_input_files(
            str(ROOT / 'web/assets/learning-deck.json')
        )
        expect(page.locator('#game-ready')).to_be_visible()
        print('PASS unavailable deck, invalid JSON, local file recovery')
        context.close()
        browser.close()


if __name__ == '__main__':
    main()
