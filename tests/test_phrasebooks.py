import json
import random
import tempfile
import unittest
import uuid
from pathlib import Path

from scripts.import_phrasebooks import (
    BOOKS,
    PhraseRow,
    assign_bad_variants,
    choose_bad_translation,
    import_to_supabase,
    most_frequent,
    normalize_bashkir,
    read_phrasebooks,
    select_translations,
    stable_hash,
)
from scripts.pure import normalize_translation


class FakeResponse:
    def __init__(self, data):
        self.data = data


class FakeQuery:
    def __init__(self, database, table):
        self.database = database
        self.table = table
        self.action = None
        self.fields = '*'
        self.conditions = []
        self.range_values = None
        self.maximum = None
        self.payload = None
        self.unique_keys = []

    def select(self, fields):
        self.action = 'select'
        self.fields = fields
        return self

    def eq(self, column, value):
        self.conditions.append((column, [value]))
        return self

    def in_(self, column, values):
        self.conditions.append((column, list(values)))
        return self

    def range(self, start, end):
        self.range_values = (start, end)
        return self

    def limit(self, value):
        self.maximum = value
        return self

    def upsert(self, payload, on_conflict, ignore_duplicates, returning='representation'):
        self.action = 'upsert'
        self.payload = payload if isinstance(payload, list) else [payload]
        self.unique_keys = on_conflict.split(',')
        self.ignore_duplicates = ignore_duplicates
        return self

    def execute(self):
        records = self.database.records[self.table]
        if self.action == 'select':
            selected = [
                row
                for row in records
                if all(row[column] in accepted for column, accepted in self.conditions)
            ]
            if self.range_values:
                start, end = self.range_values
                selected = selected[start : end + 1]
            if self.maximum is not None:
                selected = selected[: self.maximum]
            if self.fields != '*':
                names = self.fields.split(',')
                selected = [{name: row[name] for name in names} for row in selected]
            return FakeResponse(selected)
        if self.action == 'upsert':
            for candidate in self.payload:
                conflict = next(
                    (
                        row
                        for row in records
                        if all(row[field] == candidate[field] for field in self.unique_keys)
                    ),
                    None,
                )
                if not conflict:
                    records.append(dict(candidate))
                elif not self.ignore_duplicates:
                    conflict.update(candidate)
            return FakeResponse([])
        raise AssertionError('Неизвестная операция тестовой БД')


class FakeDatabase:
    def __init__(self):
        self.records = {
            name: [] for name in ('sources', 'fragments', 'fragment_pairs', 'phrasebook_rows')
        }

    def table(self, name):
        return FakeQuery(self, name)


class PhrasebookImportTests(unittest.TestCase):
    def test_import_twice_preserves_rows_without_database(self):
        database = FakeDatabase()
        rows = [
            PhraseRow(
                f'bgpu-alt-{index}',
                'data-ba-ru-alt.jsonl',
                'alt',
                index,
                f'BA-ITEM-{index}',
                f'RU-ITEM-{index}',
                '',
                stable_hash({'book': 'alt', 'id': index}),
            )
            for index in range(1, 11)
        ]
        rows += [
            PhraseRow(
                'bgpu-kk-1',
                'data-ba-ru-kk.jsonl',
                'kk',
                1,
                'BA-ITEM-1',
                'RU-ITEM-1',
                'KK-ITEM-1',
                stable_hash({'book': 'kk', 'id': 1}),
            ),
        ]
        stats = {'read': len(rows), 'invalid': 0, 'duplicate_ids': 0}
        first = import_to_supabase(database, rows, stats, 0.2, 9)
        self.assertEqual(first['imported'], 10)
        self.assertEqual(first['new_pairs'], 11)
        self.assertEqual(first['new_row_ids'], 11)
        self.assertEqual(first['bad_variants'], 2)
        self.assertEqual(len(database.records['sources']), 1)
        self.assertEqual(len(database.records['phrasebook_rows']), 11)
        second = import_to_supabase(database, rows, stats, 0.2, 9)
        self.assertEqual(second['imported'], 0)
        self.assertEqual(second['new_pairs'], 0)
        self.assertEqual(second['new_row_ids'], 0)
        self.assertEqual(len(database.records['fragments']), 10)
        self.assertEqual(len(database.records['fragment_pairs']), 11)
        altered = [
            PhraseRow(
                rows[0].row_id,
                rows[0].file_name,
                rows[0].book,
                rows[0].position,
                rows[0].text_ba,
                rows[0].text_ru,
                rows[0].text_other,
                'f' * 64,
            ),
            *rows[1:],
        ]
        with self.assertRaisesRegex(ValueError, 'изменилась'):
            import_to_supabase(database, altered, stats, 0.2, 9)

    def test_normalize_bashkir_key_without_real_language_data(self):
        self.assertEqual(normalize_translation('  BA-CODE-02!  '), 'ba-code-02')
        self.assertEqual(normalize_translation('BA-CODE-02'), 'ba-code-02')
        self.assertEqual(normalize_bashkir('e\u0301'), normalize_bashkir('é'))

    def test_five_jsonl_files_and_optional_transcription(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            for book in BOOKS:
                records = [
                    {
                        'id': f'bgpu-{book}-00001',
                        'text_ba': 'BA-CODE-X',
                        'text_ru': 'RU-VALUE-X',
                        'text_other': 'OTHER-CODE',
                        'lang_other': book,
                    }
                ]
                if book == 'zh':
                    records[0]['transcription'] = 'SYMBOLS-ONLY'
                (folder / f'data-ba-ru-{book}.jsonl').write_text(
                    ''.join(json.dumps(record) + '\n' for record in records),
                    encoding='utf-8',
                )
            rows, stats = read_phrasebooks(folder)
            self.assertEqual(stats['read'], 5)
            self.assertEqual(stats['invalid'], 0)
            self.assertEqual(len(rows), 5)
            self.assertEqual(rows[0].position, 1)
            fragments, pairs, report = select_translations(rows, str(uuid.uuid4()))
            self.assertEqual(len(fragments), 1)
            self.assertEqual({pair.lang_pair for pair in pairs}, {'ba-ru', 'ba-kk'})
            self.assertEqual(report['normalized_duplicates'], 4)

    def test_invalid_short_rows_and_duplicate_ids(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            for book in BOOKS:
                path = folder / f'data-ba-ru-{book}.jsonl'
                path.write_text(
                    json.dumps(
                        {
                            'id': f'bgpu-{book}-12345',
                            'text_ba': 'BA-CODE',
                            'text_ru': 'RU-TEXT',
                            'text_other': 'OTHER-TEXT',
                            'lang_other': book,
                        }
                    )
                    + '\n',
                    encoding='utf-8',
                )
            target = folder / 'data-ba-ru-kk.jsonl'
            entry = target.read_text(encoding='utf-8')
            target.write_text(
                entry
                + entry
                + json.dumps(
                    {
                        'id': 'bgpu-kk-12346',
                        'text_ba': 'x',
                        'text_ru': 'RU-X',
                        'text_other': 'KK-X',
                        'lang_other': 'kk',
                    }
                )
                + '\n',
                encoding='utf-8',
            )
            rows, stats = read_phrasebooks(folder)
            self.assertEqual(len(rows), 5)
            self.assertEqual(stats['duplicate_ids'], 1)
            self.assertEqual(stats['invalid'], 1)
            self.assertEqual(stats['read'], 7)

    def test_majority_russian_and_tie_breaking(self):
        def row(row_id, file, book, ba, ru, other='OTHER'):
            return PhraseRow(row_id, file, book, 1, ba, ru, other, stable_hash({'id': row_id}))

        rows = [
            row('a', 'alt.jsonl', 'alt', 'BA-TOKEN-ONE', 'RU-B'),
            row('b', 'ar.jsonl', 'ar', 'ba-token-one', 'RU-A'),
            row('c', 'zh.jsonl', 'zh', 'BA-TOKEN-ONE', 'RU-B'),
            row('d', 'kk.jsonl', 'kk', 'BA-TOKEN-TWO', 'RU-Z', 'KK-Z'),
        ]
        source = str(uuid.uuid4())
        fragments, pairs, report = select_translations(rows, source)
        self.assertEqual(report['ru_conflict_groups'], 1)
        self.assertEqual(report['ru_alternatives_discarded'], 1)
        self.assertEqual(report['normalized_duplicates'], 2)
        selected = {(item.key, item.lang_pair): item.translation for item in pairs}
        self.assertEqual(selected[('ba-token-one', 'ba-ru')], 'RU-B')
        self.assertEqual(selected[('ba-token-two', 'ba-kk')], 'KK-Z')
        self.assertEqual(len(fragments), 2)
        self.assertEqual(most_frequent(['RU-B', 'RU-A']), 'RU-A')

    def test_bad_translation_conditions_and_reproducibility(self):
        candidates = [
            ('ba-1', 'TRANSLATION-ABCDE'),
            ('ba-2', 'TRANSLATION-UVWXY'),
            ('ba-3', 'SHORT'),
            ('ba-4', 'TRANSLATION-ABCDE AND MORE'),
        ]
        first = choose_bad_translation('TRANSLATION-ABCDE', 'ba-1', candidates, random.Random(1))
        second = choose_bad_translation('TRANSLATION-ABCDE', 'ba-1', candidates, random.Random(1))
        self.assertEqual(first, 'TRANSLATION-UVWXY')
        self.assertEqual(first, second)
        self.assertIsNone(
            choose_bad_translation('SHORT', 'ba-2', [('ba-1', 'LONG-CANDIDATE')], random.Random(1))
        )

    def test_bad_share_is_deterministic(self):
        rows = []
        for number in range(20):
            code = f'ba-code-{number:03}'
            rows.append(
                PhraseRow(
                    f'id-{number}',
                    'data-ba-ru-alt.jsonl',
                    'alt',
                    number + 1,
                    code,
                    f'RU-VALUE-{number:03}',
                    '',
                    stable_hash({'id': number}),
                )
            )
        _, pairs, _ = select_translations(rows, str(uuid.uuid4()))
        values_a = assign_bad_variants(rows, pairs, 0.2, 17)
        values_b = assign_bad_variants(rows, pairs, 0.2, 17)
        self.assertEqual(values_a, values_b)
        self.assertEqual(len(values_a), 4)
        self.assertEqual(assign_bad_variants(rows, pairs, 0.0, 17), {})
        with self.assertRaises(ValueError):
            assign_bad_variants(rows, pairs, -0.1, 17)

    def test_lang_other_mismatch_is_counted_not_fatal(self):
        with tempfile.TemporaryDirectory() as raw:
            folder = Path(raw)
            for book in BOOKS:
                code = 'zho' if book == 'zh' else book
                (folder / f'data-ba-ru-{book}.jsonl').write_text(
                    json.dumps(
                        {
                            'id': f'bgpu-{book}-00001',
                            'text_ba': f'BA-{book}',
                            'text_ru': f'RU-{book}',
                            'text_other': f'OTHER-{book}',
                            'lang_other': code,
                        }
                    )
                    + '\n',
                    encoding='utf-8',
                )
            rows, stats = read_phrasebooks(folder)
        self.assertEqual(len(rows), len(BOOKS))
        self.assertEqual(stats['lang_mismatch'], 1)


if __name__ == '__main__':
    unittest.main()


class PhrasebookRegressionTests(unittest.TestCase):
    def test_source_identity_preserves_question_and_exclamation(self):
        values = ['BA-TEXT', 'BA-TEXT?', 'BA-TEXT!']
        self.assertEqual(len({normalize_bashkir(value) for value in values}), 3)
        rows = [
            PhraseRow(
                str(i), 'alt.jsonl', 'alt', i + 1, text, 'RU-TEXT', '', stable_hash({'text': text})
            )
            for i, text in enumerate(values)
        ]
        fragments, _, _ = select_translations(rows, str(uuid.uuid4()))
        self.assertEqual(len(fragments), 3)

    def test_legacy_mapping_stops_before_adding_fragments(self):
        from copy import deepcopy

        database = FakeDatabase()
        row = PhraseRow('1', 'alt.jsonl', 'alt', 1, 'BA-TEXT?', 'RU-TEXT', '', 'f' * 64)
        stats = {'read': 1}
        import_to_supabase(database, [row], stats, 0, 1)
        database.records['phrasebook_rows'][0]['fragment_id'] = str(uuid.uuid4())
        before = deepcopy(database.records)
        with self.assertRaisesRegex(ValueError, 'прежняя нормализация'):
            import_to_supabase(database, [row], stats, 0, 1)
        self.assertEqual(database.records, before)

    def test_ids_are_scoped_per_file_even_when_numeric(self):
        from scripts.import_phrasebooks import read_phrasebooks

        with tempfile.TemporaryDirectory() as location:
            folder = Path(location)
            for index, book in enumerate(BOOKS):
                payload = {
                    'id': 1,
                    'text_ba': f'BA-ITEM-{index}',
                    'text_ru': f'RU-TEXT-{index}',
                    'text_other': f'OTHER-{index}',
                    'lang_other': book,
                }
                (folder / f'data-ba-ru-{book}.jsonl').write_text(
                    json.dumps(payload) + '\n', encoding='utf-8'
                )
            rows, stats = read_phrasebooks(folder)
            self.assertEqual(len(rows), 5)
            self.assertEqual(stats['duplicate_ids'], 0)
            self.assertEqual(len({row.storage_id for row in rows}), 5)
            self.assertTrue(all(row.row_id == '1' for row in rows))
            database = FakeDatabase()
            outcome = import_to_supabase(database, rows, stats, 0.0, 7)
            self.assertEqual(outcome['new_row_ids'], 5)
            self.assertEqual(import_to_supabase(database, rows, stats, 0.0, 7)['new_row_ids'], 0)

    def test_review_csv_is_safe_and_does_not_require_supabase(self):
        from scripts.import_phrasebooks import write_review

        with tempfile.TemporaryDirectory() as directory:
            source = str(uuid.uuid4())
            row = PhraseRow(
                '1', 'data-ba-ru-alt.jsonl', 'alt', 1, '=HYPERLINK(1)', 'RU-VALUE', '', 'f' * 64
            )
            fragments, pairs, _ = select_translations([row], source)
            path = Path(directory) / 'review.csv'
            write_review(path, fragments, pairs, {}, [row])
            self.assertIn("'=HYPERLINK(1)", path.read_text(encoding='utf-8-sig'))

    def test_punctuation_variants_are_flagged_for_review(self):
        rows = [
            PhraseRow('1', 'data-ba-ru-alt.jsonl', 'alt', 1, 'BA-ITEM?', 'RU-ONE', '', 'a' * 64),
            PhraseRow('2', 'data-ba-ru-alt.jsonl', 'alt', 2, 'BA-ITEM.', 'RU-TWO', '', 'b' * 64),
        ]
        _, _, report = select_translations(rows, str(uuid.uuid4()))
        self.assertEqual(report['punctuation_conflicts'], 1)
