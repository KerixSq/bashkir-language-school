import unittest

from scripts.pure import (
    JOIN_ALPHABET,
    display_translation,
    new_join_code,
    normalize_translation,
    split_fragments,
    valid_nickname,
)


class PureTests(unittest.TestCase):
    def test_normalization_preserves_inner_punctuation(self):
        self.assertEqual(
            normalize_translation('  «Сегодня   мы учим слова!»  '),
            'сегодня мы учим слова',
        )
        self.assertEqual(normalize_translation('Нью-Йорк, город.'), 'нью-йорк, город')
        self.assertEqual(normalize_translation(''), '')

    def test_display_keeps_original_auto(self):
        self.assertEqual(
            display_translation('сегодня мы учим слова', 'Сегодня мы учим слова.', []),
            'Сегодня мы учим слова.',
        )

    def test_display_most_frequent_original(self):
        corrections = [
            'Совсем другой текст.',
            'совсем другой текст',
            'Совсем другой текст.',
            'Несовпадающий ответ.',
        ]
        self.assertEqual(
            display_translation('совсем другой текст', 'Автотекст.', corrections),
            'Совсем другой текст.',
        )

    def test_display_deterministic_tie(self):
        self.assertEqual(
            display_translation('новый текст', 'Исходный текст.', ['новый текст.', 'Новый текст.']),
            'Новый текст.',
        )

    def test_display_missing(self):
        with self.assertRaises(ValueError):
            display_translation('пропавший вариант', 'Другой.', [])

    def test_nicknames(self):
        for value in ('Демо_3', 'Башҡорт-123', 'English Name', 'abc'):
            with self.subTest(value=value):
                self.assertTrue(valid_nickname(value))
        for value in (
            'ab',
            '@user',
            'https://example.org',
            'a' * 21,
            ' имя ',
            'имя\nфамилия',
            '___',
        ):
            with self.subTest(value=value):
                self.assertFalse(valid_nickname(value))

    def test_codes(self):
        self.assertFalse(set('O0I1') & set(JOIN_ALPHABET))
        for size in (6, 7, 8):
            code = new_join_code(size)
            self.assertEqual(len(code), size)
            self.assertRegex(code, r'^[A-HJ-NP-Z2-9]{6,8}$')
        with self.assertRaises(ValueError):
            new_join_code(5)

    def test_split_text(self):
        text = 'Это пример тестового предложения. Ещё одна длинная фраза для проверки.'
        fragments = split_fragments(text)
        self.assertTrue(fragments)
        self.assertTrue(all(20 <= len(value) <= 300 for value in fragments))
        self.assertEqual(' '.join(fragments), text)

    def test_long_text_and_tail(self):
        text = 'Длинное учебное предложение без внешнего источника. ' * 16
        fragments = split_fragments(text)
        self.assertGreater(len(fragments), 1)
        self.assertTrue(all(20 <= len(value) <= 300 for value in fragments))
        self.assertEqual(' '.join(fragments), text.strip())

    def test_short_text_fails_without_silent_loss(self):
        with self.assertRaises(ValueError):
            split_fragments('три')
        self.assertEqual(split_fragments(''), [])


if __name__ == '__main__':
    unittest.main()
