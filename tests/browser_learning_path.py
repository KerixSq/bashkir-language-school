"""Optional local learning-path smoke test; no database or HTTP server needed.

Install requirements-dev.txt and Chromium with `python -m playwright install chromium`.
Run `python tests/browser_learning_path.py` from the repository root.
"""

import base64
import mimetypes
import os
import re
import tempfile
from pathlib import Path

from playwright.sync_api import sync_playwright

WEB = Path(__file__).resolve().parents[1] / "web"


def mime(path):
    return mimetypes.guess_type(path.name)[0] or "application/octet-stream"


def inline_assets(html):
    html = re.sub(r"<script[^>]*\bsrc=[^>]*></script>", "", html)
    html = re.sub(r"<link[^>]*href=\"https://[^\"]+\"[^>]*>", "", html)
    html = html.replace("</head>", '<base href="https://school.test/web/"></head>', 1)

    def encode_src(match):
        path = WEB / match.group(1)
        if not path.is_file():
            return match.group(0)
        data = base64.b64encode(path.read_bytes()).decode()
        return f'src="data:{mime(path)};base64,{data}"'

    html = re.sub(r'src="(assets/[\w./-]+)"', encode_src, html)

    def encode_css(match):
        path = WEB / match.group(1)
        if not path.is_file():
            return match.group(0)
        data = base64.b64encode(path.read_bytes()).decode()
        return f'url("data:{mime(path)};base64,{data}")'

    return re.sub(r"url\(['\"]?(assets/[\w./-]+)['\"]?\)", encode_css, html)


def main():
    page_html = inline_assets((WEB / "index.html").read_text(encoding="utf-8"))
    deck = (WEB / "assets/learning-deck.json").read_bytes()

    with sync_playwright() as playwright:
        options = {"headless": True}
        if os.getenv("BROWSER_EXECUTABLE"):
            options["executable_path"] = os.environ["BROWSER_EXECUTABLE"]
        browser = playwright.chromium.launch(**options)
        for width, height, label in ((1440, 900, "desktop"), (390, 844, "mobile")):
            page = browser.new_page(viewport={"width": width, "height": height})
            errors = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.route(
                "**/web/assets/learning-deck.json",
                lambda route: route.fulfill(body=deck, content_type="application/json"),
            )
            page.set_content(page_html, wait_until="domcontentloaded", timeout=30_000)
            assert page.locator("#game-ready").is_visible(), "game deck not loaded"
            assert page.locator("#path-stage-2").is_disabled(), "stage unlocked too early"
            page.locator("#play-entry").click()

            for _ in range(5):
                assert page.locator("#game-question").is_visible(), "question not shown"
                answers = page.locator("#game-answers")
                options = answers.locator("button.game-answer")
                bank = answers.locator(".game-word-bank button")
                typed = answers.locator("textarea,input")
                if options.count():
                    options.first.click()
                elif bank.count():
                    bank.first.click()
                elif typed.count():
                    typed.first.fill("Проверочный ответ")
                else:
                    raise AssertionError("question lacks input control")

                assert page.locator("#game-check").is_enabled()
                page.locator("#game-check").click()
                assert page.locator("#game-next").is_visible()
                page.locator("#game-next").click()

            assert page.locator("#game-finish").is_visible()
            assert int(page.locator("#top-xp").text_content()) > 0
            assert not page.locator(".app-mobile-nav").is_visible()
            assert page.evaluate("document.documentElement.scrollWidth") <= width + 1
            assert not errors, errors
            image = Path(tempfile.gettempdir()) / f"bashkir-academy-{label}.png"
            page.screenshot(path=str(image))
            print(f"PASS {label}: full lesson, XP, layout, no JS errors; {image}")
            page.close()
        browser.close()


if __name__ == "__main__":
    main()
