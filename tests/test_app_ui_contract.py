import unittest
from html.parser import HTMLParser
from pathlib import Path

WEB = Path(__file__).resolve().parents[1] / 'web' / 'index.html'


class DocumentStructure(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids = []
        self.stages = []
        self.navigations = []

    def handle_starttag(self, tag, attrs):
        options = dict(attrs)
        if 'id' in options:
            self.ids.append(options['id'])
        if 'data-game-stage' in options:
            self.stages.append((tag, options['data-game-stage']))
        if 'data-app-dest' in options:
            self.navigations.append((tag, options['data-app-dest']))


class AppUiContractTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.content = WEB.read_text(encoding='utf-8')
        cls.doc = DocumentStructure()
        cls.doc.feed(cls.content)

    def test_unique_ids_and_existing_game_contract(self):
        self.assertEqual(len(self.doc.ids), len(set(self.doc.ids)))
        for field in (
            'game-start',
            'game-question',
            'game-check',
            'game-next',
            'game-finish',
            'game-badges',
            'community-progressbar',
        ):
            self.assertIn(field, self.doc.ids)

    def test_path_nodes_open_actual_lesson_stages(self):
        self.assertEqual({stage for _, stage in self.doc.stages}, {'0', '1', '2'})
        self.assertTrue(all(tag == 'button' for tag, _ in self.doc.stages))
        self.assertGreaterEqual(len(self.doc.stages), 6)

    def test_navigation_uses_existing_panels(self):
        for value in ('learn', 'ratings', 'translations', 'rewards'):
            self.assertIn(value, [item[1] for item in self.doc.navigations])
        self.assertIn('lesson-close', self.doc.ids)
        self.assertIn('app-mobile-nav', self.content)
        self.assertIn('localStorage', self.content)

    def test_brand_independent_from_reference_product(self):
        self.assertIn('Акбузат', self.content)
        self.assertNotIn('duolingo', self.content.lower())


if __name__ == '__main__':
    unittest.main()
