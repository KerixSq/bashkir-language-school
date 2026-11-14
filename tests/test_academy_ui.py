"""Static checks for the learner-first academy shell and real game wiring."""

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PAGE = (ROOT / 'web' / 'index.html').read_text(encoding='utf-8')


class AcademyUiTests(unittest.TestCase):
    def test_guest_cta_opens_a_real_lesson(self):
        navigation = (ROOT / 'web/assets/navigation.js').read_text(encoding='utf-8')
        self.assertIn('src="assets/navigation.js"', PAGE)
        self.assertIn("byId('path-stage-1').click()", navigation)
        self.assertIn("document.querySelectorAll('[data-game-stage]')", PAGE)
        self.assertIn('function stageTo(index)', PAGE)

    def test_locked_stages_preserve_their_state_after_requests(self):
        self.assertIn('const controls = [...document.querySelectorAll', PAGE)
        self.assertIn('button.disabled=wasDisabled', PAGE)
        self.assertIn("button.classList.toggle('is-locked',button.disabled)", PAGE)

    def test_progress_and_original_art_present(self):
        self.assertIn('id="path-count"', PAGE)
        self.assertIn('id="top-streak"', PAGE)
        self.assertIn('id="top-xp"', PAGE)
        self.assertIn('textContent = `${mastered()} изученных фраз`', PAGE)
        for file in ('akbuzat.webp', 'ural-journey.webp', 'learning-deck.json'):
            self.assertTrue((ROOT / 'web' / 'assets' / file).is_file(), file)

    def test_immersive_lesson_and_keyboard_options(self):
        self.assertIn('class="game-word-mascot"', PAGE)
        self.assertIn('/^[1-4]$/.test(event.key)', PAGE)
        self.assertIn('body.lesson-active .app-mobile-nav {display:none!important}', PAGE)
        self.assertIn('id="game-finish"', PAGE)

    def test_no_duplicate_ids(self):
        ids = re.findall(r'\bid="([^"]+)"', PAGE)
        self.assertEqual(len(ids), len(set(ids)))


if __name__ == '__main__':
    unittest.main()
