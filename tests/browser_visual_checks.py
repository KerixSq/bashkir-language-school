"""Responsive UI regressions; local server, real deck, CDN unavailable.

Run: python tests/browser_visual_checks.py
Screenshots: test-results/visual/ (override WEB_SCREENSHOT_DIR).
"""

import os
import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from browser_checks import TRANSLATIONS, lesson
from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[1]
OUT = Path(os.getenv('WEB_SCREENSHOT_DIR', str(ROOT / 'test-results/visual')))
SIZES = ((360, 800), (390, 844), (768, 1024), (1024, 768), (1440, 900), (1920, 1080))


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, *_args):
        pass


def no_overflow(page):
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), 'page overflow'
    if page.locator('body.lesson-active').count():
        assert page.locator('#game-console').evaluate(
            '(node) => node.scrollWidth <= node.clientWidth'
        ), 'lesson overflow'


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    server = ThreadingHTTPServer(('127.0.0.1', 0), partial(QuietHandler, directory=str(ROOT)))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            for width, height in SIZES:
                context = browser.new_context(
                    viewport={'width': width, 'height': height},
                    reduced_motion='reduce',
                    color_scheme='dark',
                )
                page = context.new_page()
                errors = []
                page.on('pageerror', lambda error: errors.append(str(error)))
                page.route('https://**/*', lambda route: route.abort())
                page.goto(f'http://127.0.0.1:{server.server_port}/web/')
                expect(page.locator('#game-ready')).to_be_visible()
                page.locator('img').evaluate_all(
                    "(nodes) => nodes.forEach(node => node.loading = 'eager')"
                )
                page.wait_for_function('[...document.images].every(img => img.complete)')
                expect(page.locator('.legend-zone')).to_have_count(0)
                expect(page.locator('.app-brand-icon img')).to_have_attribute(
                    'src', 'assets/bashkir-mark.svg'
                )
                expect(page.locator('.app-sidebar-bottom img')).to_have_attribute(
                    'src', 'assets/akbuzat-chibi.webp'
                )
                expect(page.locator('link[rel="icon"]')).to_have_attribute(
                    'href', 'assets/bashkir-mark.svg'
                )
                assert page.locator('.app-brand-icon img, .app-sidebar-bottom img').evaluate_all(
                    '(images) => images.every(image => image.naturalWidth > 0)'
                )
                no_overflow(page)
                page.screenshot(path=str(OUT / f'home-{width}.png'))
                # Mascot must occupy its own area rather than cover mobile CTAs/copy.
                if width <= 760:
                    copy = page.locator('.quest-hero-content').bounding_box()
                    art = page.locator('.quest-mascot').bounding_box()
                    footnote = page.locator('.hero-footnote').bounding_box()
                    assert footnote['y'] + footnote['height'] <= art['y'] + 10
                    assert copy['width'] > 0
                page.locator('.path-preview').screenshot(path=str(OUT / f'map-{width}.png'))
                for name, selector in (
                    ('profile', '#web-play'),
                    ('ratings', '#tab-ratings'),
                    ('translations', '#tab-translations'),
                    ('expert', '#tab-expert'),
                ):
                    node = page.locator(selector)
                    if selector.startswith('#tab-'):
                        node.click()
                        page.locator(f'#{name}').scroll_into_view_if_needed()
                    else:
                        node.scroll_into_view_if_needed()
                    no_overflow(page)
                    page.screenshot(path=str(OUT / f'{name}-{width}.png'))
                page.locator('#game-start').click()
                expect(page.locator('#lesson-close')).to_be_focused()
                page.locator('#lesson-close').press('Shift+Tab')
                expect(page.locator('#game-skip')).to_be_focused()
                page.locator('#game-skip').press('Tab')
                expect(page.locator('#lesson-close')).to_be_focused()
                page.screenshot(path=str(OUT / f'lesson-{width}.png'))
                no_overflow(page)
                # A real wrong answer must look different from success, even in dark OS mode.
                phrase = page.locator('#game-bashkir-text').inner_text()
                translation = TRANSLATIONS[('ba-ru', phrase)]
                next(
                    button
                    for button in page.locator('#game-answers button').all()
                    if button.inner_text() != translation
                ).click()
                page.locator('#game-check').click()
                feedback = page.locator('#game-feedback')
                expect(feedback).to_have_class('game-feedback is-wrong')
                assert feedback.evaluate('node => getComputedStyle(node).backgroundColor') == (
                    'rgb(255, 244, 223)'
                )
                page.locator('#game-bashkir-text').evaluate(
                    "node => node.textContent = ('Ә ө ү ҙ ҡ ң ғ һ ҫ. Длинная фраза '.repeat(18))"
                )
                no_overflow(page)
                page.locator('#game-next').click()
                assert page.locator('#game-console').evaluate('node => node.scrollTop') == 0
                page.on('dialog', lambda dialog: dialog.accept())
                page.locator('#lesson-close').click()
                assert page.evaluate('!document.querySelector("[inert]")')
                expect(page.locator('#game-start')).to_be_focused()
                # Full five-task lesson and XP persistence are exercised against real corpus.
                lesson(page, wrong_first=True)
                page.screenshot(path=str(OUT / f'finish-{width}.png'))
                page.locator('#lesson-close').click()
                # Reflow viewport corresponding to desktop browser zoom at 200%.
                page.set_viewport_size({'width': max(320, width // 2), 'height': height})
                no_overflow(page)
                page.screenshot(path=str(OUT / f'zoom-{width}.png'))
                assert not errors, errors
                print(
                    f'PASS {width}x{height}: offline CDN, dark OS, focus, long text, lesson, 200% equivalent reflow'
                )
                context.close()
            browser.close()
    finally:
        server.shutdown()
        server.server_close()


if __name__ == '__main__':
    main()
