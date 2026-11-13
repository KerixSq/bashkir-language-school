"""Checks for the jury-facing interface without network access."""

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HTML = (ROOT / 'web' / 'index.html').read_text(encoding='utf-8')
SQL = (ROOT / 'sql' / 'logic.sql').read_text(encoding='utf-8')


class JuryHomeChecks(unittest.TestCase):
    def test_daily_actions_are_connected_to_original_buttons(self):
        for name in ('jury-fast-confirm', 'jury-fast-correct', 'web-confirm', 'web-correct-toggle'):
            self.assertIn(f'id="{name}"', HTML)
        self.assertIn('focusTask', HTML)
        self.assertIn('button.click()', HTML)

    def test_rankings_are_marked_demo_until_live_data(self):
        self.assertIn('ДЕМО', HTML)
        self.assertIn('Вымышленные примеры для демонстрации дизайна', HTML)
        self.assertIn('window.JuryHome?.update({loaded:true,users,classes,schools}', HTML)
        for kind in ('schools', 'classes', 'users'):
            self.assertIn(f'data-jury-kind="{kind}"', HTML)

    def test_export_buttons_share_real_export_implementation(self):
        self.assertIn('id="jury-export-csv"', HTML)
        self.assertIn('id="jury-export-json"', HTML)
        self.assertIn('window.BashkirExports={csv:downloadTranslations,json:downloadJson}', HTML)
        self.assertIn('async function downloadTranslations()', HTML)
        self.assertIn('async function downloadJson()', HTML)

    def test_public_export_has_exactly_seven_columns(self):
        view = SQL.split('create or replace view public.translations_export', 1)[1].split(
            'from public.fragment_pairs fp', 1
        )[0]
        expected = [
            'as fragment_id',
            'f.text_ba',
            'fp.lang_pair',
            'as translation',
            'as source',
            'as confirmed',
            'fp.status',
        ]
        for field in expected:
            self.assertIn(field, view)
        self.assertIn(
            "['fragment_id', 'text_ba', 'lang_pair', 'translation', 'source', 'confirmed', 'status']",
            HTML,
        )

    def test_expert_review_requires_code(self):
        self.assertIn('id="jury-open-expert"', HTML)
        self.assertIn('id="expert-code"', HTML)
        self.assertIn("if (!code) throw new Error('Введи отдельный код эксперта.')", HTML)

    def test_images_exist_and_brand_refresh_replaces_legend_section(self):
        for asset in (
            'akbuzat.webp',
            'adventure-world.webp',
            'humay.svg',
            'ural-batyr.svg',
            'ural-map.svg',
            'akbuzat-chibi.webp',
            'bashkir-mark.svg',
        ):
            self.assertTrue((ROOT / 'web' / 'assets' / asset).is_file(), asset)
        self.assertNotIn('class="legend-zone"', HTML)
        self.assertIn('src="assets/bashkir-mark.svg"', HTML)
        self.assertIn('src="assets/akbuzat-chibi.webp"', HTML)

    def test_no_repeated_html_ids(self):
        ids = re.findall(r'\bid="([^"]+)"', HTML)
        self.assertEqual(len(ids), len(set(ids)))


if __name__ == '__main__':
    unittest.main()
