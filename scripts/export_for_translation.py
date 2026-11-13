"""Список фрагментов без перевода в CSV или JSON."""

import argparse
import csv
import json
from pathlib import Path

from common import all_rows, client


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--lang-pair', required=True, choices=['ba-ru', 'ba-en', 'ba-kk'])
    parser.add_argument('--format', choices=['csv', 'json'], default='csv')
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    db = client()
    fragments = all_rows(
        lambda: db.table('fragments').select('id,text_ba,chapter,position').order('created_at')
    )
    pairs = all_rows(
        lambda: db.table('fragment_pairs').select('fragment_id').eq('lang_pair', args.lang_pair)
    )
    translated = {p['fragment_id'] for p in pairs}
    rows = [
        {
            'fragment_id': f['id'],
            'text_ba': f['text_ba'],
            'lang_pair': args.lang_pair,
            'chapter': f['chapter'],
            'position': f['position'],
        }
        for f in fragments
        if f['id'] not in translated
    ]
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    if args.format == 'json':
        out.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding='utf-8')
    else:
        with out.open('w', encoding='utf-8-sig', newline='') as fp:
            writer = csv.DictWriter(
                fp, fieldnames=['fragment_id', 'text_ba', 'lang_pair', 'chapter', 'position']
            )
            writer.writeheader()
            writer.writerows(rows)
    print(f'Экспортировано {len(rows)} фрагментов в {out}')


if __name__ == '__main__':
    main()
