import json
import tempfile
import unittest
from pathlib import Path

from scripts.export_learning_deck import build_learning_deck


class LearningDeckTests(unittest.TestCase):
    def test_export_without_invented_phrases(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for book in ('alt', 'ar', 'kk', 'sah', 'zh'):
                records = []
                for index in range(12):
                    records.append(
                        {
                            'id': f'{book}-{index:03d}',
                            'text_ba': f'BA_SAMPLE_{index:03d}',
                            'text_ru': f'RU_SAMPLE_{index:03d}',
                            'text_other': f'KK_SAMPLE_{index:03d}'
                            if book == 'kk'
                            else 'OTHER_SAMPLE',
                            'lang_other': book,
                        }
                    )
                (root / f'data-ba-ru-{book}.jsonl').write_text(
                    '\n'.join(json.dumps(row, ensure_ascii=False) for row in records),
                    encoding='utf-8',
                )
            deck = build_learning_deck(root, per_pair=20, seed=3)
            self.assertEqual(set(deck['stats']['pairs']), {'ba-ru', 'ba-kk'})
            self.assertEqual(len(deck['items']), 24)
            self.assertTrue(all('SAMPLE' in item['text_ba'] for item in deck['items']))
            self.assertTrue(all(item['verified'] is False for item in deck['items']))
            self.assertEqual(len({row['id'] for row in deck['items']}), len(deck['items']))
            self.assertEqual(build_learning_deck(root, 20, 3), deck)

    def test_input_requires_all_files(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError, 'Отсутствуют'):
                build_learning_deck(Path(directory))


if __name__ == '__main__':
    unittest.main()
