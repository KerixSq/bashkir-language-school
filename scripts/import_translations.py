"""Загружает проверенный CSV переводов. Не меняет пары с ответами."""

import argparse
import csv

from common import client

FIELDS = {'fragment_id', 'lang_pair', 'auto_translation', 'bad_translation'}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--file', required=True)
    args = parser.parse_args()
    db = client()
    added = skipped = 0
    with open(args.file, 'r', encoding='utf-8-sig', newline='') as fp:
        reader = csv.DictReader(fp)
        if set(reader.fieldnames or []) != FIELDS:
            raise SystemExit('CSV должен содержать ровно: ' + ', '.join(sorted(FIELDS)))
        for line, row in enumerate(reader, 2):
            if None in row or any(row.get(field) is None for field in FIELDS):
                raise SystemExit(f'Строка {line}: нарушено количество CSV-полей')
            pair = row['lang_pair'].strip()
            text = row['auto_translation'].strip()
            if pair not in ('ba-ru', 'ba-en', 'ba-kk') or not text:
                raise SystemExit(f'Строка {line}: неверная языковая пара или пустой перевод')
            fragment_id = row['fragment_id'].strip()
            existing = (
                db.table('fragment_pairs')
                .select('id')
                .eq('fragment_id', fragment_id)
                .eq('lang_pair', pair)
                .execute()
                .data
            )
            if existing:
                has_answers = (
                    db.table('answers')
                    .select('id')
                    .eq('fragment_pair_id', existing[0]['id'])
                    .limit(1)
                    .execute()
                    .data
                )
                if has_answers:
                    skipped += 1
                    continue
            db.table('fragment_pairs').upsert(
                {
                    'fragment_id': fragment_id,
                    'lang_pair': pair,
                    'auto_translation': text,
                    'bad_translation': row['bad_translation'].strip() or None,
                },
                on_conflict='fragment_id,lang_pair',
            ).execute()
            added += 1
    print(f'Импортировано/обновлено: {added}; с ответами не тронуто: {skipped}')


if __name__ == '__main__':
    main()
