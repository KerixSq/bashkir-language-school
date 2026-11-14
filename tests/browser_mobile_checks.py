"""Real local corpus/audio on mobile Chromium and WebKit; records review evidence."""

import json
import threading
import traceback
from functools import partial
from http.server import ThreadingHTTPServer

from browser_checks import lesson
from browser_tts_checks import playing, ready, stopped
from browser_visual_checks import ROOT, QuietHandler, no_overflow
from playwright.sync_api import expect, sync_playwright

OUT = ROOT / 'test-results/mobile'


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    server = ThreadingHTTPServer(('127.0.0.1', 0), partial(QuietHandler, directory=str(ROOT)))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    results = []
    try:
        with sync_playwright() as playwright:
            for engine, device in (('chromium', 'Pixel 7'), ('webkit', 'iPhone 13')):
                browser = getattr(playwright, engine).launch()
                context = browser.new_context(
                    **playwright.devices[device],
                    reduced_motion='reduce',
                    record_video_dir=str(OUT / engine),
                    record_video_size={'width': 390, 'height': 844},
                )
                page = context.new_page()
                errors = []
                console_errors = []
                network_failures = []
                page.on('pageerror', lambda error: errors.append(str(error)))
                page.on(
                    'console',
                    lambda message: (
                        console_errors.append(message.text) if message.type == 'error' else None
                    ),
                )
                page.on(
                    'requestfailed',
                    lambda request: network_failures.append(
                        {'url': request.url, 'failure': request.failure}
                    ),
                )
                page.route('https://**/*', lambda route: route.abort())
                try:
                    ready(page, f'http://127.0.0.1:{server.server_port}/web/')
                    no_overflow(page)
                    expect(page.locator('#lesson-close')).to_be_focused()
                    page.locator('#game-tts').click()
                    playing(page)
                    # A screenshot can outlast a short real WAV on a busy runner.
                    # Stop first so the next tap cannot restart an already-ended clip.
                    page.locator('#game-tts').click()
                    stopped(page)
                    page.screenshot(path=str(OUT / f'{engine}-audio.png'))
                    page.on('dialog', lambda dialog: dialog.accept())
                    page.locator('#lesson-close').click()
                    # The uploaded subset contains only actual corpus entries with real WAVs.
                    lesson(page, wrong_first=True)
                    no_overflow(page)
                    page.screenshot(path=str(OUT / f'{engine}-finish.png'))
                    saved = page.evaluate(
                        "JSON.parse(localStorage.getItem('bashkir_story_game_v1'))"
                    )
                    assert saved['answers'] == 5 and saved['xp'] > 0, saved
                    page.locator('#game-back-to-map').click()
                    expect(page.locator('#game-ready')).to_be_visible()
                    page.reload()
                    expect(page.locator('#game-score')).to_have_text(str(saved['xp']))
                    profile = page.locator('#web-profile-area')
                    profile.scroll_into_view_if_needed()
                    expect(profile).to_be_visible()
                    no_overflow(page)
                    page.screenshot(path=str(OUT / f'{engine}-profile.png'))
                    page.locator('#tab-ratings').click()
                    expect(page.locator('#notice')).to_contain_text('подключи публичный ключ')
                    page.locator('#tab-ratings').press('ArrowRight')
                    expect(page.locator('#tab-translations')).to_be_focused()
                    # Real failed resource, not a fabricated successful server response.
                    page.route('**/learning-deck.json', lambda route: route.abort())
                    page.reload()
                    expect(page.locator('#game-empty')).to_be_visible()
                    no_overflow(page)
                    assert not errors, errors
                    unexpected = [
                        message
                        for message in console_errors
                        if not message.startswith('Failed to load resource:')
                    ]
                    assert not unexpected, unexpected
                    results.append(
                        {
                            'engine': engine,
                            'device': device,
                            'status': 'PASS',
                            'console_errors': console_errors,
                            'network_failures': network_failures,
                        }
                    )
                    print(f'PASS {engine}/{device}: real lesson, WAV, persistence, focus, outage')
                except Exception as error:
                    traceback.print_exc()
                    page.screenshot(path=str(OUT / f'{engine}-failure.png'))
                    results.append(
                        {'engine': engine, 'status': 'FAIL', 'error': traceback.format_exc()}
                    )
                    print(f'FAIL {engine}: {error}')
                finally:
                    video = page.video
                    context.close()
                    if video:
                        video.save_as(str(OUT / f'{engine}-mobile.webm'))
                    browser.close()
    finally:
        server.shutdown()
        server.server_close()
        (OUT / 'results.json').write_text(json.dumps(results, indent=2), encoding='utf-8')
    assert len(results) == 2 and all(row['status'] == 'PASS' for row in results), results


if __name__ == '__main__':
    main()
