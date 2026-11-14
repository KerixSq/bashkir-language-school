"""Real scroll, tab navigation and contextual sidebar; no successful API stubs."""

import threading
from functools import partial
from http.server import ThreadingHTTPServer

from browser_checks import lesson
from browser_visual_checks import ROOT, QuietHandler, no_overflow
from playwright.sync_api import expect, sync_playwright

OUT = ROOT / 'test-results/visual-polish/after'


def boundary_stability(page):
    """Tiny reversals around a real boundary must not toggle context repeatedly."""
    page.evaluate('scrollTo({top:0,behavior:"instant"})')
    expect(page.locator('#sidebar-context')).to_have_attribute('data-section', 'learn')
    trace = page.evaluate(
        """async () => {
        const boundary = document.querySelector('.path-preview').getBoundingClientRect().top
          + scrollY - innerHeight * .25;
        const trace = [];
        for (const offset of [-30, 30, 3, -3, 3, -3, 3, -3]) {
          scrollTo({top:boundary+offset,behavior:'instant'});
          await new Promise(resolve => setTimeout(resolve, 50));
          trace.push(document.getElementById('sidebar-context').dataset.section);
        }
        return trace;
        }"""
    )
    changes = [dest for i, dest in enumerate(trace) if i == 0 or dest != trace[i - 1]]
    assert len(changes) <= 2, f'Boundary flicker: {trace}'
    page.evaluate('scrollTo({top:0,behavior:"instant"})')


def sequence_checks(page, width):
    trace = page.evaluate(
        """async () => {
        const context = document.getElementById('sidebar-context');
        const frame = () => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)));
        const max = document.documentElement.scrollHeight-innerHeight;
        const down=[], up=[];
        for (let y=0;y<=max+100;y+=100) {
          scrollTo({top:Math.min(y,max),behavior:'instant'}); await frame();
          down.push(context.dataset.section);
        }
        for (let y=max;y>=-100;y-=100) {
          scrollTo({top:Math.max(0,y),behavior:'instant'}); await frame();
          up.push(context.dataset.section);
        }
        return {down,up};
        }"""
    )
    order = ['learn', 'lessons', 'practice', 'lessons', 'library', 'lessons', 'rewards', 'ratings']
    for direction, legal in (('down', order), ('up', order[::-1])):
        values = trace[direction]
        changes = [dest for i, dest in enumerate(values) if not i or dest != values[i - 1]]
        position = 0
        for dest in changes:
            assert dest in legal[position:], (direction, changes)
            position = legal.index(dest, position) + 1
    # Observe writes as well as labels: an unchanged section must not churn context.
    writes = page.evaluate(
        """async () => {
        let writes=0;
        const observer=new MutationObserver(rows=>writes+=rows.length);
        observer.observe(document.getElementById('sidebar-context'),{attributes:true,subtree:true,childList:true});
        for (const y of [0,20,40,60,40,20,0]) {
          scrollTo({top:y,behavior:'instant'}); await new Promise(resolve=>setTimeout(resolve,25));
        }
        observer.disconnect();return writes;
        }"""
    )
    assert writes == 0, f'Unchanged context rewritten {writes} times'
    # Actual click + smooth native scroll. Sample every frame, not just the endpoint.
    page.emulate_media(reduced_motion='no-preference')
    selector = (
        '.app-sidebar [data-app-dest="ratings"]'
        if width > 850
        else '.app-mobile-nav [data-app-dest="ratings"]'
    )
    page.locator(selector).click()
    samples = page.evaluate(
        """async () => {
        const values=[];
        for(let i=0;i<45;i++) {await new Promise(requestAnimationFrame);values.push(document.getElementById('sidebar-context').dataset.section);}
        return values;
        }"""
    )
    assert set(samples) == {'ratings'}, samples
    page.locator('#tab-translations').click()
    expect(page.locator('#sidebar-context')).to_have_attribute('data-section', 'translations')
    # Interrupt a fresh long transition using a real wheel event.
    home = (
        '.app-sidebar [data-app-dest="learn"]'
        if width > 850
        else '.app-mobile-nav [data-app-dest="learn"]'
    )
    page.locator(home).click()
    page.mouse.move(width - 40, 100)
    page.mouse.wheel(0, 240)
    page.wait_for_timeout(100)
    page.evaluate('scrollTo({top:0,behavior:"instant"})')
    expect(page.locator('#sidebar-context')).to_have_attribute('data-section', 'learn')
    page.emulate_media(reduced_motion='reduce')
    # Async content growth, then rapid jumps; no stale intersection state remains.
    page.locator('#web-profile-area').evaluate("node => node.style.paddingBottom='250px'")
    for target, dest in (
        ('#game-zone', 'lessons'),
        ('#web-profile-area', 'practice'),
        ('.community-quest', 'library'),
    ):
        page.locator(target).evaluate(
            "node => node.scrollIntoView({block:'start',behavior:'instant'})"
        )
        expect(page.locator('#sidebar-context')).to_have_attribute('data-section', dest)
    page.locator('#web-profile-area').evaluate("node => node.style.paddingBottom=''")
    page.evaluate('scrollTo({top:0,behavior:"instant"})')
    expect(page.locator('#sidebar-context')).to_have_attribute('data-section', 'learn')


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
                    if width in (1440, 390):
                        boundary_stability(page)
                        sequence_checks(page, width)
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
                            ), sidebar.evaluate(
                                'node => ({height:node.clientHeight, scroll:node.scrollHeight})'
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
                    # A reduced-motion jump is complete immediately. Returning
                    # manually must not remain pinned to the previous tab.
                    page.evaluate('scrollTo({top:0,behavior:"instant"})')
                    active('learn')
                    page.evaluate(
                        'scrollTo({top:document.documentElement.scrollHeight,behavior:"instant"})'
                    )
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
