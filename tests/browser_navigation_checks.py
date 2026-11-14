"""Real scroll, tab navigation and contextual sidebar; no successful API stubs."""

import threading
from functools import partial
from http.server import ThreadingHTTPServer

from browser_checks import lesson
from browser_visual_checks import ROOT, QuietHandler, no_overflow
from playwright.sync_api import expect, sync_playwright

OUT = ROOT / 'test-results/visual-polish/after'


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    server = ThreadingHTTPServer(('127.0.0.1', 0), partial(QuietHandler, directory=str(ROOT)))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        with sync_playwright() as playwright:
            for engine in ('chromium', 'webkit'):
                browser = getattr(playwright, engine).launch()
                # 1152/960/720 widths cover reflow equivalent to 125/150/200%
                # browser zoom on a 1440x900 display, without changing site CSS.
                for width, height in (
                    (1440, 900),
                    (1152, 720),
                    (960, 600),
                    (720, 450),
                    (1024, 600),
                    (390, 844),
                ):
                    page = browser.new_page(
                        viewport={'width': width, 'height': height}, reduced_motion='reduce'
                    )
                    errors = []
                    page.on('pageerror', lambda error: errors.append(str(error)))
                    page.route('https://**/*', lambda route: route.abort())
                    page.goto(f'http://127.0.0.1:{server.server_port}/web/')
                    expect(page.locator('#game-ready')).to_be_visible()

                    def active(dest):
                        expect(page.locator('.app-sidebar .is-active')).to_have_count(1)
                        expect(page.locator('.app-sidebar .is-active')).to_have_attribute(
                            'data-app-dest', dest
                        )
                        expect(page.locator('#sidebar-context')).to_have_attribute(
                            'data-section', dest
                        )

                    active('learn')
                    expect(page.locator('#jury-ranking-list')).not_to_contain_text('1280')
                    assert 'демо)' not in page.locator('#jury-ranking-list').inner_text()
                    for selector, dest in (
                        ('#web-profile-area', 'practice'),
                        ('#game-zone', 'lessons'),
                        ('.community-quest', 'library'),
                        ('.game-achievements', 'rewards'),
                    ):
                        page.locator(selector).evaluate(
                            "node => node.scrollIntoView({block:'start',behavior:'instant'})"
                        )
                        active(dest)
                        no_overflow(page)
                    page.evaluate('scrollTo(0,0)')
                    active('learn')
                    if width > 850:
                        sidebar = page.locator('.app-sidebar')
                        assert abs(sidebar.bounding_box()['y']) < 1
                        if height >= 900:
                            assert sidebar.evaluate(
                                'node => node.scrollHeight <= node.clientHeight'
                            )
                        for item in page.locator('.app-sidebar .app-nav-item').all():
                            item.focus()
                            box = item.bounding_box()
                            assert box['y'] >= 0 and box['y'] + box['height'] <= height
                        page.locator('.app-sidebar [data-app-dest="ratings"]').click()
                    else:
                        page.locator('.app-mobile-nav [data-app-dest="ratings"]').click()
                    expect(page.locator('#ratings')).to_be_visible()
                    active('ratings')
                    requests = []
                    page.on('request', lambda request: requests.append(request.url))
                    page.locator('[data-app-dest="ratings"]:visible').first.click()
                    assert not [url for url in requests if '/rest/v1/' in url]
                    page.locator('#tab-translations').click()
                    active('translations')
                    page.reload()
                    page.locator('#game-zone').evaluate(
                        "node => node.scrollIntoView({block:'start',behavior:'instant'})"
                    )
                    active('lessons')
                    expect(page.locator('.app-mobile-nav .is-active')).to_have_attribute(
                        'data-app-dest', 'learn'
                    )
                    page.screenshot(path=str(OUT / f'{engine}-navigation-{width}.png'))
                    if width > 850:
                        page.locator('.app-sidebar [data-app-dest="library"]').focus()
                        page.keyboard.press('Enter')
                        active('library')
                    assert not errors, errors
                    page.evaluate('scrollTo(0,0)')
                    page.locator('#play-entry').click()
                    expect(page.locator('#game-question')).to_be_visible()
                    page.on('dialog', lambda dialog: dialog.accept())
                    page.keyboard.press('Escape')
                    expect(page.locator('#game-ready')).to_be_visible()
                    if width == 1440 and engine == 'chromium':
                        lesson(page)
                        page.locator('#game-back-to-map').click()
                        active('lessons')
                        expect(page.locator('#sidebar-context-detail')).to_contain_text(
                            page.locator('#game-score').inner_text() + ' тренировочных XP'
                        )
                    print(
                        f'PASS {engine} {width}x{height}: scrollspy, context, tabs, reload, keyboard'
                    )
                    page.close()
                browser.close()
    finally:
        server.shutdown()
        server.server_close()


if __name__ == '__main__':
    main()
