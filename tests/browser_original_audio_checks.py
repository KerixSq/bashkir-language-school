"""Called by isolated Docker E2E: real import, Auth user, source playback and answer."""

import re
import shutil
import subprocess
import sys
import tempfile
import threading
from functools import partial
from http.server import ThreadingHTTPServer
from pathlib import Path

from audio_fixture import audio_fixture
from browser_visual_checks import ROOT, QuietHandler
from playwright.sync_api import expect, sync_playwright

sys.path.insert(0, str(ROOT))
from scripts.import_audio import import_audio, plan


def check_original_audio(api, page, compose, sql, root):
    with tempfile.TemporaryDirectory() as directory:
        folder = Path(directory)
        audio, annotation, _ = audio_fixture(folder)
        output = folder / 'assets'
        source, segments = import_audio(
            api,
            audio,
            annotation,
            'TECHNICAL QA tone - not human speech',
            'CC0 technical fixture',
            output,
        )
        self_repeat = import_audio(
            api, audio, annotation, source['title'], source['license'], output
        )
        assert self_repeat == (source, segments)
        assert (
            len(api.table('fragments').select('id').eq('source_id', source['id']).execute().data)
            == 1
        )
        compose(
            'exec', '-T', 'app', 'mkdir', '-p', '/usr/share/nginx/html/web/assets/original-audio'
        )
        compose(
            'cp',
            str(output / Path(source['url']).name),
            'app:/usr/share/nginx/html/web/assets/original-audio/',
        )
        published = page.request.get('http://127.0.0.1:54321' + source['url'])
        assert published.ok, (
            f'Nginx cannot read the published original audio: HTTP {published.status}'
        )
        pair = segments[0]['pair_id']
        user = sql("select id from users where nickname='Integration 0';")
        sql(
            f"update users set state='idle',current_fragment_pair_id='{pair}',current_shown_variant='auto',current_shown_at=now()-interval '30 seconds',last_answer_at=now()-interval '30 seconds' where id='{user}';"
        )
        page.reload()
        expect(page.locator('#web-session')).to_be_visible()
        page.locator('#web-next').click()
        expect(page.locator('#web-original-audio')).to_be_visible()
        expect(page.locator('#original-audio-status')).to_contain_text('not human speech')
        audio_node = page.locator('#original-audio-player')
        button = page.locator('#original-audio-play')
        button.focus()
        button.press('Enter')
        page.wait_for_function(
            "() => {const a=document.getElementById('original-audio-player');return !a.paused && a.currentTime>=0.2 && a.currentTime<0.8}"
        )
        page.wait_for_function("() => document.getElementById('original-audio-player').paused")
        assert audio_node.evaluate('a=>a.currentTime') <= 0.8
        button.click()
        page.wait_for_function("() => !document.getElementById('original-audio-player').paused")
        button.click()
        assert audio_node.evaluate('a=>a.paused')
        # Failure changes only the audio status, never fabricates a successful answer.
        task = api.rpc('get_next_fragment', {'p_user_id': user}).execute().data
        page.route('**/original-audio/*.wav', lambda route: route.abort())
        page.evaluate('task=>window.OriginalAudio.setTask(task)', task)
        button.click()
        expect(page.locator('#original-audio-status')).to_contain_text('Не удалось')
        page.unroute('**/original-audio/*.wav')
        button.click()
        page.wait_for_function("() => !document.getElementById('original-audio-player').paused")
        out = root / 'test-results/visual'
        out.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(out / 'original-audio-mobile.png'))
        page.context.set_offline(True)
        page.locator('#web-confirm').click()
        expect(page.locator('#web-status')).to_have_class(re.compile('.*is-error.*'))
        expect(page.locator('#web-original-audio')).to_be_visible()
        assert audio_node.evaluate('a=>a.paused && a.hasAttribute("src")')
        assert (
            not api.table('answers')
            .select('id')
            .eq('user_id', user)
            .eq('fragment_pair_id', pair)
            .execute()
            .data
        )
        page.context.set_offline(False)
        page.locator('#web-confirm').click()
        expect(page.locator('#web-feedback')).to_contain_text('Ответ принят')
        assert audio_node.evaluate('a=>a.paused && !a.hasAttribute("src")')
        saved = (
            api.table('answers')
            .select('id')
            .eq('user_id', user)
            .eq('fragment_pair_id', pair)
            .execute()
            .data
        )
        assert len(saved) == 1
        export = (
            api.table('translations_export')
            .select('*')
            .eq('fragment_id', segments[0]['id'])
            .single()
            .execute()
            .data
        )
        assert len(export) == 7 and 'сек.' in export['source']
        print(
            'PASS original audio: repeat import, real PCM segment, keyboard, range stop, 404/retry, browser answer, PostgreSQL timecodes'
        )


def main():
    """Standalone real-file widget test; full Auth/answer flow runs in Docker."""
    with tempfile.TemporaryDirectory() as directory:
        audio, annotation, _ = audio_fixture(Path(directory))
        source, rows = plan(
            audio, annotation, 'TECHNICAL QA tone - not speech', 'CC0 technical fixture'
        )
        task = {
            **rows[0],
            'source_kind': 'audio',
            'source_url': source['url'],
            'source': source['title'],
        }
        files = {source['url']: audio}
        mp3_task = None
        if shutil.which('ffmpeg') and shutil.which('ffprobe'):
            mp3 = Path(directory) / 'technical-tone.mp3'
            subprocess.run(
                [shutil.which('ffmpeg'), '-v', 'error', '-i', str(audio), str(mp3)],
                check=True,
                timeout=30,
            )
            mp3_source, mp3_rows = plan(
                mp3, annotation, 'TECHNICAL MP3 tone - not speech', 'CC0 technical fixture'
            )
            files[mp3_source['url']] = mp3
            mp3_task = {
                **mp3_rows[0],
                'source_kind': 'audio',
                'source_url': mp3_source['url'],
                'source': mp3_source['title'],
            }
        else:
            print('SKIP MP3 widget: existing ffmpeg/ffprobe unavailable; WAV still tested')

        class AudioHandler(QuietHandler):
            def translate_path(self, path):
                if path in files:
                    return str(files[path])
                return super().translate_path(path)

        server = ThreadingHTTPServer(('127.0.0.1', 0), partial(AudioHandler, directory=str(ROOT)))
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            with sync_playwright() as playwright:
                for engine in ('chromium', 'webkit'):
                    browser = getattr(playwright, engine).launch()
                    page = browser.new_page(viewport={'width': 390, 'height': 844})
                    errors = []
                    page.on('pageerror', lambda error: errors.append(str(error)))
                    # Real local HTTP serves PCM bytes; no mocked API/media response.
                    page.goto(f'http://127.0.0.1:{server.server_port}/web/')
                    page.evaluate(
                        "task=>{document.getElementById('web-session').hidden=false;document.getElementById('web-task').hidden=false;window.OriginalAudio.setTask(task)}",
                        task,
                    )
                    button = page.locator('#original-audio-play')
                    expect(button).to_be_visible()
                    button.focus()
                    button.press('Enter')
                    try:
                        page.wait_for_function(
                            "() => {const a=document.getElementById('original-audio-player');return !a.paused && a.currentTime>=0.2}",
                            timeout=5000,
                        )
                    except Exception:
                        print(
                            engine,
                            page.locator('#original-audio-player').evaluate(
                                "a=>({paused:a.paused,time:a.currentTime,ready:a.readyState,error:a.error?.message,status:document.getElementById('original-audio-status').textContent})"
                            ),
                            errors,
                        )
                        raise
                    page.wait_for_function(
                        "() => document.getElementById('original-audio-player').paused"
                    )
                    assert (
                        page.locator('#original-audio-player').evaluate('a=>a.currentTime') <= 0.8
                    )
                    button.click()
                    page.wait_for_function(
                        "() => !document.getElementById('original-audio-player').paused"
                    )
                    page.evaluate('window.OriginalAudio.clear()')
                    assert page.locator('#original-audio-player').evaluate(
                        'a=>a.paused && !a.hasAttribute("src")'
                    )
                    page.evaluate(
                        'task=>window.OriginalAudio.setTask(task)',
                        {**task, 'source_url': 'https://evil.example/file.wav'},
                    )
                    expect(page.locator('#web-original-audio')).to_be_hidden()
                    if mp3_task:
                        page.evaluate('task=>window.OriginalAudio.setTask(task)', mp3_task)
                        button.click()
                        page.wait_for_function(
                            "() => {const a=document.getElementById('original-audio-player');return !a.paused && a.currentTime>=0.2}"
                        )
                        page.wait_for_function(
                            "() => document.getElementById('original-audio-player').paused"
                        )
                        assert (
                            page.locator('#original-audio-player').evaluate('a=>a.currentTime')
                            <= 0.8
                        )
                        print(f'PASS {engine}: real MP3 range playback')
                    assert not errors, errors
                    browser.close()
                    print(
                        f'PASS {engine}: real original PCM widget, range, keyboard, cancellation, unsafe URL'
                    )
        finally:
            server.shutdown()
            server.server_close()


if __name__ == '__main__':
    main()
