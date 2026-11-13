"""Собирает игровой набор из локальных JSONL-разговорников БГПУ."""

import argparse
import json
import random
from collections import Counter
from pathlib import Path

if __package__:
    from .import_phrasebooks import DATASET_URL, read_phrasebooks, select_translations
else:
    from import_phrasebooks import DATASET_URL, read_phrasebooks, select_translations


LICENSE = 'CC BY 4.0'


def build_learning_deck(folder: Path, per_pair: int = 350, seed: int = 42) -> dict:
    if per_pair < 5 or per_pair > 2000:
        raise ValueError('Число фраз на пару должно быть от 5 до 2000')
    rows, statistics = read_phrasebooks(folder)
    fragments, pairs, report = select_translations(rows, '5e5d2e40-a98c-568b-b2a7-90f2be963a26')
    by_id = {item['id']: item for item in fragments}
    originals = {}
    for row in rows:
        originals.setdefault((row.key, row.file_name, 'ba-ru', row.text_ru), row)
        if row.book == 'kk':
            originals.setdefault((row.key, row.file_name, 'ba-kk', row.text_other), row)
    seen = set()
    grouped: dict[str, list[dict]] = {'ba-ru': [], 'ba-kk': []}
    for pair in pairs:
        if pair.lang_pair not in grouped:
            continue
        fragment = by_id[pair.fragment_id]
        key = (pair.lang_pair, pair.key)
        if key in seen:
            continue
        seen.add(key)
        original = originals[(pair.key, pair.file_name, pair.lang_pair, pair.translation)]
        source = f'bgpu-{original.book} · {original.row_id} · строка {original.position}'
        grouped[pair.lang_pair].append(
            {
                'id': f'{pair.lang_pair}:{pair.fragment_id}',
                'lang_pair': pair.lang_pair,
                'text_ba': fragment['text_ba'],
                'translation': pair.translation,
                'source': source,
                'verified': False,
            }
        )
    rng = random.Random(seed)
    items = []
    for lang_pair, candidates in grouped.items():
        # Сохраняем короткие и длинные фразы: игра использует несколько уровней.
        bands: dict[int, list[dict]] = {0: [], 1: [], 2: []}
        for row in candidates:
            length = len(row['text_ba'])
            bands[0 if length < 50 else 1 if length < 100 else 2].append(row)
        picked = []
        for band in bands.values():
            rng.shuffle(band)
            picked += band[: max(1, per_pair // 4)]
        rest = [row for row in candidates if row['id'] not in {r['id'] for r in picked}]
        rng.shuffle(rest)
        picked += rest[: max(0, per_pair - len(picked))]
        items.extend(picked[:per_pair])
    return {
        'version': 1,
        'dataset': DATASET_URL,
        'license': LICENSE,
        'license_url': 'https://creativecommons.org/licenses/by/4.0/',
        'rights_holder': 'ФГБОУ ВО «БГПУ им. М. Акмуллы»',
        'publisher': 'АНО «Фонд сохранения и развития башкирского языка»',
        'notice': (
            'Учебные соответствия из открытого корпуса БГПУ. '
            'Они не проверены носителями языка построчно. '
            'Веб-очки не равны очкам Telegram-бота.'
        ),
        'stats': {
            'read': statistics['read'],
            'selected': len(items),
            'pairs': dict(Counter(item['lang_pair'] for item in items)),
            'normalized_duplicates': report['normalized_duplicates'],
        },
        'items': items,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dir', type=Path, required=True, help='Папка с пятью JSONL')
    parser.add_argument(
        '--output',
        type=Path,
        default=Path(__file__).resolve().parents[1] / 'web/assets/learning-deck.json',
    )
    parser.add_argument('--per-pair', type=int, default=350)
    parser.add_argument('--seed', type=int, default=42)
    args = parser.parse_args()
    deck = build_learning_deck(args.dir, args.per_pair, args.seed)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(deck, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(f'Готова учебная колода: {len(deck["items"])} фраз -> {args.output}')
    print('Внимание: переводы корпуса не проверены носителем языка построчно.')
    for lang_pair, count in deck['stats']['pairs'].items():
        print(f'  {lang_pair}: {count}')


if __name__ == '__main__':
    main()
