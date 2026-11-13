import unittest

from bot import texts
from scripts.pure import (
    chapters,
    levenshtein,
    new_api_key,
    new_join_code,
    normalize_translation,
    secret_hash,
    valid_nickname,
    vote_weight,
)


class HardeningTests(unittest.TestCase):
    def test_vote_weight(self):
        self.assertEqual(vote_weight(3, 1), 1.2)
        self.assertEqual(vote_weight(100, 0), 1.5)
        self.assertEqual(vote_weight(0, 100), 0.5)
        self.assertEqual(vote_weight(0, 0), 1.0)

    def test_api_secret(self):
        secret = new_api_key()
        self.assertTrue(secret.startswith('bsk_'))
        self.assertGreaterEqual(len(secret), 40)
        self.assertEqual(len(secret_hash(secret)), 64)
        self.assertNotEqual(secret_hash(secret), secret_hash(new_api_key()))

    def test_codes_nickname(self):
        for _ in range(50):
            code = new_join_code()
            self.assertRegex(code, r'^[A-HJ-NP-Z2-9]{8}$')
            self.assertNotIn('0', code)
        self.assertTrue(valid_nickname('Мой_Ник-7'))
        self.assertFalse(valid_nickname('http://x.com'))
        self.assertFalse(valid_nickname('@ivan'))

    def test_normalize_yo(self):
        self.assertEqual(normalize_translation('  Ёжик!  '), 'ежик')
        self.assertEqual(normalize_translation('Ежик'), 'ежик')

    def test_distance(self):
        self.assertEqual(levenshtein('кот', 'кот'), 0)
        self.assertEqual(levenshtein('кот', 'коты'), 1)

    def test_chapter_pattern(self):
        data = (
            '## Одна\nДостаточно длинная первая строка.\n## Две\nДостаточно длинная вторая строка.'
        )
        result = chapters(data, 'вступление', r'^## (.+)$')
        self.assertEqual([r[0] for r in result], ['Одна', 'Две'])

    def test_fast_answer_feedback(self):
        line = texts.result({'too_fast': True, 'retry_seconds': 2})
        self.assertIn('2', line)
        self.assertNotIn('Очки за ответ', line)

    def test_no_html_leaks(self):
        self.assertNotIn(
            '<script>', texts.new_class({'join_code': 'AAAAAA', 'teacher_code': '<script>'})
        )


if __name__ == '__main__':
    unittest.main()
