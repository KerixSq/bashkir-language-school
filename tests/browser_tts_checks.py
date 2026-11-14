"""Real WAV decoding/playback, cancellation and unavailable audio; no TTS model needed."""

import json
import threading
from functools import partial
from http.server import ThreadingHTTPServer

from browser_checks import DECK
from browser_visual_checks import OUT, ROOT, QuietHandler, no_overflow
from playwright.sync_api import expect, sync_playwright

MANIFEST = json.loads((ROOT / 'web/assets/audio/manifest.json').read_text(encoding='utf-8'))
SOURCES = {source for entry in MANIFEST['entries'] for source in entry['source_ids']}
DEMO = dict(DECK, items=[row for row in DECK['items'] if row['id'] in SOURCES])


def ready(page, url):
    page.goto(url)
    expect(page.locator('#game-ready')).to_be_visible()
    page.locator('#game-local-file').set_input_files(
        {
            'name': 'real-corpus-audio-demo.json',
            'mimeType': 'application/json',
            'buffer': json.dumps(DEMO, ensure_ascii=False).encode('utf-8'),
        }
    )
    expect(page.locator('#game-source')).to_contain_text('Локальный JSON')
    page.locator('#game-start').click()


def playing(page):
    page.wait_for_function(
        """() => { const audio = document.getElementById('bashkir-audio');
        return !audio.paused && audio.readyState >= 2 && audio.currentTime > 0; }"""
    )


def stopped(page):
    assert page.locator('#bashkir-audio').evaluate(
        "audio => audio.paused && !audio.hasAttribute('src')"
    ), 'Bashkir audio must be paused with its source cleared'


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    server = ThreadingHTTPServer(('127.0.0.1', 0), partial(QuietHandler, directory=str(ROOT)))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    url = f'http://127.0.0.1:{server.server_port}/web/'
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            for width in (390, 1440):
                context = browser.new_context(viewport={'width': width, 'height': 900})
                page = context.new_page()
                errors = []
                page.on('pageerror', lambda error: errors.append(str(error)))
                page.route('https://**/*', lambda route: route.abort())
                page.add_init_script(
                    "speechSynthesis.speak = () => { throw Error('Browser voice substitution forbidden'); };"
                )
                ready(page, url)
                stopped(page)  # No autoplay.
                button = page.locator('#game-tts')
                expect(button).to_be_enabled()
                option = page.locator('#game-answers button').first
                box = option.bounding_box()
                page.mouse.move(box['x'] + 10, box['y'] + box['height'] - 1)
                assert option.evaluate(
                    """async node => {
                    const positions = [];
                    for (let i = 0; i < 12; i++) {
                      await new Promise(requestAnimationFrame);
                      positions.push(node.getBoundingClientRect().y);
                    }
                    return Math.max(...positions) - Math.min(...positions) < 0.5;
                    }"""
                ), 'Answer button moves under pointer'
                option.click()
                expect(page.locator('#game-check')).to_be_enabled()
                button.focus()
                button.press('Enter')
                playing(page)
                expect(page.locator('#game-feedback')).to_be_hidden()
                no_overflow(page)
                page.screenshot(path=str(OUT / f'tts-lesson-{width}.png'))
                button.press('Space')
                stopped(page)
                expect(page.locator('#game-feedback')).to_be_hidden()
                page.locator('#game-phrase-details summary').press('Enter')
                expect(page.locator('#game-word-source')).to_be_visible()
                expect(page.locator('#game-feedback')).to_be_hidden()
                page.locator('#game-phrase-details summary').press('Enter')
                expect(page.locator('#game-word-source')).to_be_hidden()
                button.click()
                playing(page)
                page.locator('#game-skip').click()
                stopped(page)
                expect(button).to_be_enabled()
                button.click()
                playing(page)
                page.on('dialog', lambda dialog: dialog.accept())
                page.locator('#game-answers button').first.click()
                expect(page.locator('#game-check')).to_be_enabled()
                page.locator('#lesson-close').press('Enter')
                stopped(page)
                expect(page.locator('#game-ready')).to_be_visible()
                # The API control is exercised in isolation with a real corpus phrase,
                # without pretending an authenticated backend response occurred.
                page.evaluate(
                    """text => {
                    document.getElementById('web-onboarding').hidden = true;
                    document.getElementById('web-session').hidden = false;
                    document.getElementById('web-task').hidden = false;
                    document.getElementById('web-task-intro').hidden = true;
                    document.getElementById('web-original').textContent = text;
                    window.BashkirTTS.setPhrase('web', text);
                    }""",
                    MANIFEST['entries'][0]['text'],
                )
                expect(page.locator('#web-tts')).to_be_enabled()
                page.locator('#web-tts').click()
                playing(page)
                page.screenshot(path=str(OUT / f'tts-api-control-{width}.png'))
                page.evaluate("window.BashkirTTS.setPhrase('web','')")
                stopped(page)
                expect(page.locator('#web-tts')).to_be_disabled()
                assert not errors, errors
                context.close()
                print(f'PASS TTS {width}: real WAV, keyboard, stop, next, close, API control')

            page = browser.new_page()
            ready(page, url)
            page.route('**/assets/audio/*.wav', lambda route: route.fulfill(status=404, body=''))
            page.locator('#game-tts').click()
            expect(page.locator('#game-tts-status')).to_contain_text('Не удалось воспроизвести')
            page.unroute('**/assets/audio/*.wav')
            page.locator('#game-tts').click()
            playing(page)
            page.evaluate("window.BashkirTTS.setPhrase('game','')")
            stopped(page)
            expect(page.locator('#game-tts-status')).to_contain_text('пока недоступна')
            expect(page.locator('#game-answers button').first).to_be_enabled()
            page.close()
            print('PASS TTS: 404, retry with real file, absent phrase keeps text exercise')

            for body in (
                None,
                {'version': 1, 'entries': [dict(MANIFEST['entries'][0], path='../secret.wav')]},
            ):
                page = browser.new_page()
                page.route(
                    '**/audio/manifest.json',
                    lambda route, _request, body=body: route.fulfill(
                        status=404 if body is None else 200,
                        content_type='application/json',
                        body=json.dumps(body),
                    ),
                )
                ready(page, url)
                expect(page.locator('#game-tts')).to_be_disabled()
                expect(page.locator('#game-tts-status')).to_contain_text(
                    'Каталог озвучки недоступен'
                )
                expect(page.locator('#game-answers button').first).to_be_enabled()
                page.close()
            print('PASS TTS: missing manifest and unsafe paths rejected; no voice substitution')
            browser.close()
    finally:
        server.shutdown()
        server.server_close()


if __name__ == '__main__':
    main()
