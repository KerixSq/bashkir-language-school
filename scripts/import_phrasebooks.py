"""Загрузка локальных разговорников БГПУ в Supabase без внешнего API."""

import argparse
import csv
import hashlib
import json
import random
import re
import unicodedata
import uuid
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path

if __package__:
    from .pure import normalize_translation
else:
    from pure import normalize_translation

DATASET_URL = 'https://huggingface.co/datasets/bashkorttele/trilingual-parallel-phrasebooks-bgpu'
SOURCE_TITLE = 'Башкирские разговорники БГПУ (Фонд башкирского языка)'
SOURCE_LICENSE = 'CC BY 4.0'
SOURCE_HASH = hashlib.sha256(DATASET_URL.encode('utf-8')).hexdigest()
BOOKS = ('alt', 'ar', 'kk', 'sah', 'zh')
BATCH_SIZE = 200


def normalize_bashkir(value: str) -> str:
    # Source identity is stricter than answer comparison: ? and ! change meaning.
    text = re.sub(r'\s+', ' ', unicodedata.normalize('NFC', value)).strip()
    return text.strip(' «»„“”".').casefold()


@dataclass(frozen=True)
class PhraseRow:
    row_id: str
    file_name: str
    book: str
    position: int
    text_ba: str
    text_ru: str
    text_other: str
    record_hash: str

    @property
    def key(self) -> str:
        return normalize_bashkir(self.text_ba)

    @property
    def storage_id(self) -> str:
        # Два разных разговорника могут использовать один и тот же исходный ID.
        return f'{self.file_name}::{self.row_id}'


@dataclass(frozen=True)
class PairPlan:
    fragment_id: str
    key: str
    lang_pair: str
    translation: str
    file_name: str


def readable(value: object) -> str:
    return value.strip() if isinstance(value, str) else ''


def stable_hash(payload: dict) -> str:
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
    return hashlib.sha256(raw.encode('utf-8')).hexdigest()


def read_phrasebooks(folder: Path) -> tuple[list[PhraseRow], dict[str, int]]:
    """Строгая валидация пяти файлов, без обращения к сети."""
    if not folder.is_dir():
        raise ValueError(f'Нет папки: {folder}')
    paths = [folder / f'data-ba-ru-{book}.jsonl' for book in BOOKS]
    missing = [path.name for path in paths if not path.is_file()]
    if missing:
        raise ValueError('Отсутствуют JSONL-файлы: ' + ', '.join(missing))

    stats = {'read': 0, 'invalid': 0, 'duplicate_ids': 0, 'lang_mismatch': 0}
    rows = []
    seen_ids: dict[str, str] = {}
    for book, path in zip(BOOKS, paths):
        with path.open(encoding='utf-8-sig') as stream:
            for number, raw in enumerate(stream, 1):
                stats['read'] += 1
                if not raw.strip():
                    stats['invalid'] += 1
                    continue
                try:
                    data = json.loads(raw)
                except json.JSONDecodeError as exc:
                    raise ValueError(f'{path.name}:{number}: ошибка JSON: {exc.msg}') from exc
                if not isinstance(data, dict):
                    raise ValueError(f'{path.name}:{number}: ожидается JSON-объект')
                original_id = data.get('id')
                row_id = (
                    str(original_id).strip()
                    if isinstance(original_id, (str, int)) and not isinstance(original_id, bool)
                    else ''
                )
                ba = readable(data.get('text_ba'))
                ru = readable(data.get('text_ru'))
                other = readable(data.get('text_other'))
                if not row_id or len(ba) < 2 or len(ru) < 2:
                    stats['invalid'] += 1
                    continue
                if readable(data.get('lang_other')) != book:
                    # Язык определяет имя файла; расхождение кода считаем, но не прерываем импорт.
                    stats['lang_mismatch'] += 1
                    if book == 'kk':
                        raise ValueError(f'{path.name}:{number}: язык перевода должен быть kk')
                meaningful = {
                    'id': row_id,
                    'text_ba': ba,
                    'text_ru': ru,
                    'text_other': other,
                    'lang_other': book,
                }
                digest = stable_hash(meaningful)
                storage_id = f'{path.name}::{row_id}'
                if storage_id in seen_ids:
                    if seen_ids[storage_id] != digest:
                        raise ValueError(f'{path.name}:{number}: ID {row_id} имеет разные данные')
                    stats['duplicate_ids'] += 1
                    continue
                seen_ids[storage_id] = digest
                rows.append(PhraseRow(row_id, path.name, book, number, ba, ru, other, digest))
    if not rows:
        raise ValueError('Нет подходящих строк для импорта')
    return rows, stats


def most_frequent(values: list[str]) -> str:
    counts = Counter(values)
    if not counts:
        raise ValueError('Невозможно выбрать перевод из пустого списка')
    return min(counts, key=lambda value: (-counts[value], value.casefold(), value))


def select_translations(
    rows: list[PhraseRow], source_id: str
) -> tuple[list[dict], list[PairPlan], dict[str, int]]:
    """Один фрагмент на нормализованную башкирскую фразу."""
    grouped: dict[str, list[PhraseRow]] = defaultdict(list)
    endings: dict[str, set[str]] = defaultdict(set)
    for row in rows:
        grouped[row.key].append(row)
        endings[normalize_translation(row.text_ba)].add(row.text_ba.rstrip()[-1:])

    fragments = []
    pairs = []
    conflicts = discarded_variants = 0
    punctuation_conflicts = sum(len(marks & {'?', '!', '.'}) > 1 for marks in endings.values())
    for key, group in sorted(grouped.items()):
        # Совпадение нормализованного текста не гарантирует одинаковый смысл.
        russian = most_frequent([row.text_ru for row in group])
        distinct = {row.text_ru for row in group}
        if len(distinct) > 1:
            conflicts += 1
            discarded_variants += sum(row.text_ru != russian for row in group)
        # Координаты берём у строки, давшей победивший русский перевод.
        representative = next(row for row in group if row.text_ru == russian)
        fragment_id = str(uuid.uuid5(uuid.UUID(source_id), key))
        fragments.append(
            {
                'id': fragment_id,
                'source_id': source_id,
                'text_ba': representative.text_ba,
                'chapter': f'bgpu-{representative.book}',
                'position': representative.position,
            }
        )
        pairs.append(PairPlan(fragment_id, key, 'ba-ru', russian, representative.file_name))
        kazakh = [row.text_other for row in group if row.book == 'kk' and len(row.text_other) >= 2]
        if kazakh:
            pairs.append(
                PairPlan(
                    fragment_id,
                    key,
                    'ba-kk',
                    most_frequent(kazakh),
                    'data-ba-ru-kk.jsonl',
                )
            )
    return (
        fragments,
        pairs,
        {
            'normalized_duplicates': len(rows) - len(grouped),
            'ru_conflict_groups': conflicts,
            'ru_alternatives_discarded': discarded_variants,
            'punctuation_conflicts': punctuation_conflicts,
        },
    )


def choose_bad_translation(
    correct: str, key: str, candidates: list[tuple[str, str]], rng: random.Random
) -> str | None:
    """Подставной текст берётся только от другой фразы той же книги."""
    normalized_correct = normalize_translation(correct)
    length = len(correct)
    if not length:
        return None
    eligible = []
    for other_key, other_text in candidates:
        normalized_other = normalize_translation(other_text)
        if other_key == key or not normalized_other:
            continue
        if not 0.7 * length <= len(other_text) <= 1.3 * length:
            continue
        if normalized_other in normalized_correct or normalized_correct in normalized_other:
            continue
        eligible.append(other_text)
    unique = sorted(set(eligible))
    return rng.choice(unique) if unique else None


def assign_bad_variants(
    rows: list[PhraseRow], pairs: list[PairPlan], bad_share: float, seed: int
) -> dict[tuple[str, str], str]:
    """Сначала выбираем допустимые пары, затем ровно округлённую долю."""
    if not 0 <= bad_share <= 1:
        raise ValueError('--bad-share должен быть между 0 и 1')
    if bad_share == 0:
        return {}
    pools: dict[tuple[str, str], list[tuple[str, str]]] = defaultdict(list)
    for row in rows:
        pools[(row.file_name, 'ba-ru')].append((row.key, row.text_ru))
        if row.book == 'kk' and len(row.text_other) >= 2:
            pools[(row.file_name, 'ba-kk')].append((row.key, row.text_other))

    rng = random.Random(seed)
    eligible = []
    for pair in pairs:
        # Отдельный ГПСЧ делает выбор варианта независимым от размера выборки.
        variant_rng = random.Random(
            stable_hash({'key': pair.key, 'pair': pair.lang_pair, 'seed': seed})
        )
        bad = choose_bad_translation(
            pair.translation, pair.key, pools[(pair.file_name, pair.lang_pair)], variant_rng
        )
        if bad:
            eligible.append((pair.fragment_id, pair.lang_pair, bad))

    desired = min(round(len(pairs) * bad_share), len(eligible))
    selected = rng.sample(eligible, desired)
    return {(fragment_id, lang_pair): bad for fragment_id, lang_pair, bad in selected}


def batched(items: list[dict], size: int = BATCH_SIZE):
    for offset in range(0, len(items), size):
        yield items[offset : offset + size]


def existing_rows(db, table: str, columns: str, source_column: str, source_id: str):
    # Supabase ограничивает размер выдачи, поэтому читаем все страницы.
    results = []
    offset = 0
    while True:
        part = (
            db.table(table)
            .select(columns)
            .eq(source_column, source_id)
            .range(offset, offset + BATCH_SIZE - 1)
            .execute()
            .data
            or []
        )
        results.extend(part)
        if len(part) < BATCH_SIZE:
            return results
        offset += BATCH_SIZE


def create_source(db) -> str:
    matches = (
        db.table('sources')
        .select('id,license')
        .eq('title', SOURCE_TITLE)
        .eq('url', DATASET_URL)
        .limit(2)
        .execute()
        .data
        or []
    )
    if len(matches) > 1:
        raise ValueError('В sources найдено несколько одинаковых источников')
    if matches:
        if matches[0]['license'] != SOURCE_LICENSE:
            raise ValueError('Лицензия существующего источника отличается от CC BY 4.0')
        return matches[0]['id']
    proposed_id = str(uuid.uuid5(uuid.NAMESPACE_URL, DATASET_URL))
    db.table('sources').upsert(
        {
            'id': proposed_id,
            'title': SOURCE_TITLE,
            'kind': 'text',
            'license': SOURCE_LICENSE,
            'url': DATASET_URL,
        },
        on_conflict='id',
        ignore_duplicates=True,
    ).execute()
    return proposed_id


def import_to_supabase(db, rows: list[PhraseRow], stats: dict, bad_share: float, seed: int):
    source_id = create_source(db)
    fragments, pair_plans, selected = select_translations(rows, source_id)
    bad_variants = assign_bad_variants(rows, pair_plans, bad_share, seed)
    existing_fragments = {
        row['id'] for row in existing_rows(db, 'fragments', 'id', 'source_id', source_id)
    }
    mapped = {
        row['row_id']: row
        for row in existing_rows(
            db, 'phrasebook_rows', 'row_id,record_hash,fragment_id', 'source_hash', SOURCE_HASH
        )
    }
    for row in rows:
        previous = mapped.get(row.storage_id)
        if previous and previous['record_hash'] != row.record_hash:
            raise ValueError(f'Строка {row.row_id} изменилась; проверь версию датасета')
        expected_id = str(uuid.uuid5(uuid.UUID(source_id), row.key))
        if previous and previous['fragment_id'] != expected_id:
            raise ValueError(
                'Обнаружена прежняя нормализация корпуса. Импорт остановлен до записи: '
                'сначала проверь объединённые фразы на копии БД; ответы не изменены.'
            )

    new_fragments = [fragment for fragment in fragments if fragment['id'] not in existing_fragments]
    for batch in batched(new_fragments):
        db.table('fragments').upsert(
            batch, on_conflict='id', ignore_duplicates=True, returning='minimal'
        ).execute()

    pairs_in_db = set()
    for batch in batched(fragments):
        ids = [row['id'] for row in batch]
        found = (
            db.table('fragment_pairs')
            .select('fragment_id,lang_pair')
            .in_('fragment_id', ids)
            .execute()
            .data
            or []
        )
        pairs_in_db.update((row['fragment_id'], row['lang_pair']) for row in found)
    new_pairs = []
    for pair in pair_plans:
        if (pair.fragment_id, pair.lang_pair) not in pairs_in_db:
            new_pairs.append(
                {
                    'fragment_id': pair.fragment_id,
                    'lang_pair': pair.lang_pair,
                    'auto_translation': pair.translation,
                    'bad_translation': bad_variants.get((pair.fragment_id, pair.lang_pair)),
                }
            )
    for batch in batched(new_pairs):
        db.table('fragment_pairs').upsert(
            batch, on_conflict='fragment_id,lang_pair', ignore_duplicates=True, returning='minimal'
        ).execute()

    fragment_by_key = {
        normalize_bashkir(fragment['text_ba']): fragment['id'] for fragment in fragments
    }
    new_mappings = []
    for row in rows:
        if row.storage_id in mapped:
            continue
        new_mappings.append(
            {
                'source_hash': SOURCE_HASH,
                'row_id': row.storage_id,
                'record_hash': row.record_hash,
                'source_id': source_id,
                'fragment_id': fragment_by_key[row.key],
                'file_name': row.file_name,
                'line_number': row.position,
            }
        )
    for batch in batched(new_mappings):
        db.table('phrasebook_rows').upsert(
            batch, on_conflict='source_hash,row_id', ignore_duplicates=True, returning='minimal'
        ).execute()

    return {
        **stats,
        **selected,
        'imported': len(new_fragments),
        'new_pairs': len(new_pairs),
        'new_row_ids': len(new_mappings),
        'existing_row_ids': len(mapped),
        'bad_variants': len(bad_variants),
        'new_bad_variants': sum(bool(row['bad_translation']) for row in new_pairs),
        'source_id': source_id,
        'skipped': stats['read'] - len(new_fragments),
    }


def write_review(
    path: Path,
    fragments: list[dict],
    pairs: list[PairPlan],
    selected: dict[tuple[str, str], str],
    rows: list[PhraseRow],
) -> None:
    """CSV для ручной проверки. Открытие в Excel не должно исполнять формулы."""
    fragment_text = {item['id']: item['text_ba'] for item in fragments}
    file_rows = {(row.file_name, row.key): row for row in rows}

    def safe(value: str) -> str:
        return "'" + value if value.lstrip().startswith(('=', '+', '-', '@')) else value

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', encoding='utf-8-sig', newline='') as output:
        writer = csv.writer(output)
        writer.writerow(
            [
                'file',
                'source_id',
                'line',
                'lang_pair',
                'text_ba',
                'auto_translation',
                'bad_translation',
                'review_required',
            ]
        )
        for pair in pairs:
            original = file_rows.get((pair.file_name, pair.key))
            bad = selected.get((pair.fragment_id, pair.lang_pair), '')
            writer.writerow(
                [
                    pair.file_name,
                    safe(original.row_id if original else ''),
                    original.position if original else '',
                    pair.lang_pair,
                    safe(fragment_text[pair.fragment_id]),
                    safe(pair.translation),
                    safe(bad),
                    'да' if bad else 'проверить соответствие',
                ]
            )


def preview(
    rows: list[PhraseRow], stats: dict, bad_share: float, seed: int, review_out: Path | None
) -> None:
    source_id = str(uuid.uuid5(uuid.NAMESPACE_URL, DATASET_URL))
    fragments, pairs, details = select_translations(rows, source_id)
    bad = assign_bad_variants(rows, pairs, bad_share, seed)
    print('Предпросмотр без обращения к базе:')
    print('Прочитано:', stats['read'], '| подходящих строк:', len(rows))
    print(
        'Фрагментов:',
        len(fragments),
        '| переводов:',
        len(pairs),
        '| учебных ошибочных вариантов:',
        len(bad),
    )
    print('Конфликтов русских переводов:', details['ru_conflict_groups'])
    print('Групп с различающейся конечной пунктуацией:', details['punctuation_conflicts'])
    if review_out:
        write_review(review_out, fragments, pairs, bad, rows)
        print('CSV для ручной проверки:', review_out)


def main():
    parser = argparse.ArgumentParser(description='Импорт локальных JSONL разговорников БГПУ')
    parser.add_argument('--dir', required=True, type=Path, help='Папка с пятью JSONL-файлами')
    parser.add_argument('--bad-share', type=float, default=0.2, help='Доля подставных переводов')
    parser.add_argument(
        '--seed', type=int, default=42, help='Случайное зерно для воспроизводимости'
    )
    parser.add_argument('--dry-run', action='store_true', help='Только анализ JSONL, без Supabase')
    parser.add_argument('--review-out', type=Path, help='Сохранить CSV для ручной проверки')
    args = parser.parse_args()
    if not 0 <= args.bad_share <= 1:
        parser.error('--bad-share должен быть между 0 и 1')
    try:
        rows, stats = read_phrasebooks(args.dir)
    except (ValueError, OSError) as exc:
        parser.error(str(exc))

    # Даже при штатном импорте CSV показывает то, что будет записано в базу.
    preview(rows, stats, args.bad_share, args.seed, args.review_out)
    if args.dry_run:
        return
    if __package__:
        from .common import client
    else:
        from common import client
    result = import_to_supabase(client(), rows, stats, args.bad_share, args.seed)
    print('Источник:', SOURCE_TITLE)
    print('Лицензия: CC BY 4.0; атрибуция обязательна.')
    print(
        f'Прочитано строк: {result["read"]}; пропущено: {result["skipped"]}; отфильтровано: {result["invalid"]}'
    )
    print(f'Импортировано фрагментов: {result["imported"]}; новых переводов: {result["new_pairs"]}')
    print(f'Записано исходных ID: {result["new_row_ids"]}; уже было: {result["existing_row_ids"]}')
    print(f'Дублей по башкирской фразе: {result["normalized_duplicates"]}')
    print(f'Повторных ID в файлах: {result["duplicate_ids"]}')
    print(f'Конфликтных русских вариантов: {result["ru_conflict_groups"]}')
    print(f'Отклонено альтернативных русских строк: {result["ru_alternatives_discarded"]}')
    print(f'Групп с потенциально значимой пунктуацией: {result["punctuation_conflicts"]}')
    print(
        f'Подставных вариантов выбрано: {result["bad_variants"]}; добавлено в БД: {result["new_bad_variants"]}'
    )
    if result['lang_mismatch']:
        print(
            f'Строк, где lang_other не совпал с именем файла: {result["lang_mismatch"]} '
            '(язык взят из имени файла).'
        )
    print('Внимание: выравнивание переводов в корпусе не проверено построчно.')


if __name__ == '__main__':
    main()
