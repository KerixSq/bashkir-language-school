import unittest
from pathlib import Path

from bot import texts


class MessageTests(unittest.TestCase):
    def test_daily_goal_message(self):
        answer = {
            'points_awarded': 10,
            'points': 50,
            'level': 1,
            'status': 'confirmed',
            'caught_planted_error': False,
            'daily_goal': 5,
            'today_answers': 5,
            'goal_just_reached': True,
            'goal_streak': 2,
        }
        output = texts.result(answer)
        self.assertIn('Цель дня выполнена: 5 из 5', output)
        self.assertIn('Серия: 2 дн.', output)

    def test_planted_error_feedback_is_html_safe(self):
        output = texts.result(
            {
                'points_awarded': 0,
                'points': 0,
                'level': 1,
                'status': 'collecting',
                'caught_planted_error': False,
                'correct_translation': 'Перевод <script>',
                'daily_goal': 5,
                'today_answers': 1,
                'goal_just_reached': False,
            }
        )
        self.assertIn('Перевод &lt;script&gt;', output)
        self.assertNotIn('Перевод <script>', output)

    def test_next_task_button_is_connected(self):
        root = Path(__file__).resolve().parents[1]
        keyboard = (root / 'bot/keyboards.py').read_text(encoding='utf-8')
        handlers = (root / 'bot/handlers/tasks.py').read_text(encoding='utf-8')
        self.assertIn("'flow:next'", keyboard)
        self.assertIn("F.data == 'flow:next'", handlers)

    def test_result_suggests_next_task(self):
        answer = {
            'points_awarded': 10,
            'points': 10,
            'level': 1,
            'status': 'collecting',
            'daily_goal': 5,
            'today_answers': 1,
        }
        self.assertIn('Следующее задание', texts.result(answer))

    def test_duplicates_do_not_award_points(self):
        self.assertIn('уже учтён', texts.result({'duplicate': True}))


if __name__ == '__main__':
    unittest.main()
