import unittest

from scripts.demo_readiness import evaluate


class ReadinessTests(unittest.TestCase):
    def test_empty_database_is_not_ready(self):
        data = {
            key: 0
            for key in (
                'corpus_sources',
                'corpus_fragments',
                'pairs_ru',
                'pairs_kk',
                'answers',
                'confirmed',
                'expert_review',
                'students',
            )
        }
        self.assertGreaterEqual(len(evaluate(data)), 5)

    def test_real_data_with_confirmations_has_no_warnings(self):
        data = dict(
            corpus_sources=1,
            corpus_fragments=100,
            pairs_ru=100,
            pairs_kk=20,
            answers=30,
            confirmed=10,
            expert_review=0,
            students=15,
            voters=15,
            demonstrable_consensus=1,
        )
        self.assertEqual(evaluate(data), [])

    def test_many_answers_from_one_person_are_not_ready(self):
        data = dict(corpus_sources=1, corpus_fragments=100, pairs_ru=80, pairs_kk=20,
                    answers=30, confirmed=1, students=15, voters=1, demonstrable_consensus=0)
        self.assertTrue(evaluate(data))
