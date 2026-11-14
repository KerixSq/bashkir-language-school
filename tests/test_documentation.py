"""Published documentation must keep working local links and content provenance."""

import json
import re
import unittest
from pathlib import Path
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]


class DocumentationTests(unittest.TestCase):
    def test_product_guide_covers_normal_user_workflow(self):
        guide = (ROOT / 'docs/PRODUCT_GUIDE.md').read_text(encoding='utf-8')
        for heading in (
            'Начать обучение',
            'Пройти урок',
            'Проверить перевод',
            'Telegram',
            'Экспорт',
        ):
            self.assertIn('## ' + heading, guide)
        self.assertNotRegex(guide, r'\b\d:\d\d[–-]\d:\d\d\b')

    def test_local_markdown_links_resolve(self):
        documents = list(ROOT.glob('*.md')) + list((ROOT / 'docs').glob('*.md'))
        documents += [
            ROOT / 'scripts/IMPORT_GUIDE.md',
            ROOT / 'web/assets/ART_NOTES.md',
            ROOT / 'web/assets/vendor/README.md',
        ]
        for document in documents:
            for target in re.findall(
                r'\]\(([^)\s]+)(?:\s+"[^"]*")?\)', document.read_text(encoding='utf-8')
            ):
                parsed = urlsplit(target.strip('<>'))
                if parsed.scheme or parsed.netloc:
                    continue
                with self.subTest(document=str(document.relative_to(ROOT)), target=target):
                    destination = (
                        document.parent / unquote(parsed.path) if parsed.path else document
                    )
                    self.assertTrue(destination.exists())
                    if parsed.fragment and destination.suffix == '.md':
                        body = re.sub(
                            r'```.*?```', '', destination.read_text(encoding='utf-8'), flags=re.S
                        )
                        headings = re.findall(r'^#{1,6}\s+(.+)$', body, re.M)
                        anchors = {
                            re.sub(r'[^\w -]', '', title.lower()).replace(' ', '-')
                            for title in headings
                        }
                        self.assertIn(unquote(parsed.fragment), anchors)

    def test_manual_review_samples_still_match_real_deck(self):
        content = (ROOT / 'docs/CONTENT_AND_AUDIO.md').read_text(encoding='utf-8')
        deck = json.loads((ROOT / 'web/assets/learning-deck.json').read_text(encoding='utf-8'))
        rows = {row['id']: row for row in deck['items']}
        samples = re.findall(r'### \d+\. ([^\n]+)\n+(.*?)(?=\n### |\Z)', content, re.S)
        self.assertEqual(len(samples), 20)
        for identifier, sample in samples:
            with self.subTest(identifier=identifier):
                row = rows[identifier.strip()]
                self.assertIn('- Башкирский: ' + row['text_ba'], sample)
                self.assertIn('- Перевод (' + row['lang_pair'] + '): ' + row['translation'], sample)
                self.assertIn('- Источник:', sample)
                self.assertIn('Вердикт носителя: не проверено', sample)

    def test_translation_csv_contract_remains_documented(self):
        content = (ROOT / 'docs/CONTENT_AND_AUDIO.md').read_text(encoding='utf-8')
        self.assertIn('fragment_id,lang_pair,auto_translation,bad_translation', content)
        self.assertIn('кавычки внутри удваивают', content)


if __name__ == '__main__':
    unittest.main()
