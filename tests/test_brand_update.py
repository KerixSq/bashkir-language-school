"""Brand patch preserves the current application and shared CSS on reapplication."""

import contextlib
import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import apply_brand_update


class BrandUpdateTests(unittest.TestCase):
    def test_patch_is_idempotent_and_preserves_shared_rules(self):
        original = """<html><head><style>
.legend-card {color:red;}
.legend-card,.panel,.app-rail-card{border-radius:22px;}
</style></head><body>
<span class="app-brand-icon"><img src="assets/akbuzat.webp"></span>
<div class="app-sidebar-bottom"><img src="assets/akbuzat.webp"></div>
<div class="app-guide-illustration"><img src="assets/akbuzat.webp"></div>
<section class="legend-zone"><h2>Герои башкирских легенд</h2></section>
<section id="start-guide">Keep this guide</section>
<script>const task = 'preserve learning logic';</script></body></html>"""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            assets = root / 'web/assets'
            assets.mkdir(parents=True)
            for name in ('akbuzat-chibi.webp', 'bashkir-mark.svg'):
                (assets / name).touch()
            html = root / 'web/index.html'
            html.write_text(original, encoding='utf-8')
            with (
                patch.multiple(apply_brand_update, ROOT=root, HTML=html, ASSETS=assets),
                contextlib.redirect_stdout(io.StringIO()),
            ):
                apply_brand_update.main()
                updated = html.read_bytes()
                apply_brand_update.main()
                self.assertEqual(updated, html.read_bytes())
            text = updated.decode('utf-8')
            self.assertNotIn('class="legend-zone"', text)
            self.assertNotIn('.legend-card {color:red;}', text)
            self.assertIn('.legend-card,.panel,.app-rail-card{border-radius:22px;}', text)
            self.assertIn('Keep this guide', text)
            self.assertIn("const task = 'preserve learning logic';", text)
            self.assertEqual(text.count('src="assets/akbuzat-chibi.webp"'), 2)
            self.assertEqual(text.count('rel="icon"'), 1)
            self.assertEqual(
                (root / '.index.html.before-brand-update.bak').read_text(encoding='utf-8'),
                original,
            )
