import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class GameContractTest(unittest.TestCase):
    def test_web_game_has_all_real_actions(self):
        site = (ROOT / 'web/index.html').read_text(encoding='utf-8')
        for action in (
            'game-start',
            'game-check',
            'game-next',
            'game-skip',
            'game-repeat',
            'game-reset',
            'game-answers',
            'game-feedback',
        ):
            self.assertIn(f'id="{action}"', site)
        self.assertIn('window.matchMedia', site)
        self.assertIn('Asia/Yekaterinburg', site)
        self.assertIn('localStorage', site)
        self.assertIn('assets/learning-deck.json', site)
        self.assertNotIn('.innerHTML', site)

    def test_starter_is_provenanced_not_fiction(self):
        deck = json.loads((ROOT / 'web/assets/learning-deck.json').read_text(encoding='utf-8'))
        self.assertEqual(deck['license'], 'CC BY 4.0')
        self.assertTrue(deck['dataset'].startswith('https://huggingface.co/datasets/bashkorttele/'))
        self.assertGreaterEqual(len(deck['items']), 5)
        self.assertTrue(all(row['source'].startswith('bgpu-') for row in deck['items']))
        self.assertTrue(all(row.get('verified') is False for row in deck['items']))
        self.assertEqual({row['lang_pair'] for row in deck['items']}, {'ba-ru', 'ba-kk'})
        for pair in ('ba-ru', 'ba-kk'):
            self.assertGreaterEqual(sum(row['lang_pair'] == pair for row in deck['items']), 20)

    def test_learning_deck_exporter_documented(self):
        readme = (ROOT / 'README.md').read_text(encoding='utf-8')
        self.assertIn('export_learning_deck.py', readme)
        self.assertIn('docs/GAMEPLAY.md', readme)


if __name__ == '__main__':
    unittest.main()
