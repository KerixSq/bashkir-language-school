import argparse
import hashlib
from pathlib import Path

if __package__:
    from .common import client
    from .pure import chapters, split_fragments
else:
    from common import client
    from pure import chapters, split_fragments


def main() -> None:
    parser = argparse.ArgumentParser(description='Импорт открытого текста (UTF-8)')
    parser.add_argument('--file', required=True)
    parser.add_argument('--title', required=True)
    parser.add_argument('--license', required=True)
    parser.add_argument('--url', default='')
    parser.add_argument('--chapter', default='Введение')
    parser.add_argument('--chapter-pattern', help='Регулярное выражение заголовка главы')
    args = parser.parse_args()
    path = Path(args.file)
    if path.suffix.lower() not in {'.txt', '.md'}:
        parser.error('Поддерживаются только .txt и .md')
    raw = path.read_text(encoding='utf-8-sig')
    parts = [
        (title, split_fragments(body))
        for title, body in chapters(raw, args.chapter, args.chapter_pattern)
        if body.strip()
    ]
    if not parts:
        parser.error('В файле нет текста для импорта')
    db = client()
    found = (
        (
            db.table('sources')
            .select('id')
            .eq('title', args.title)
            .eq('kind', 'text')
            .eq('url', args.url or '')
            .limit(1)
            .execute()
            .data
            or []
        )
        if args.url
        else (
            db.table('sources')
            .select('id')
            .eq('title', args.title)
            .eq('kind', 'text')
            .limit(1)
            .execute()
            .data
            or []
        )
    )
    if found:
        source_id = found[0]['id']
    else:
        source_id = (
            db.table('sources')
            .insert(
                {
                    'title': args.title,
                    'kind': 'text',
                    'license': args.license,
                    'url': args.url or None,
                }
            )
            .execute()
            .data[0]['id']
        )
    created = skipped = 0
    for title, pieces in parts:
        digest = hashlib.sha256(('\n'.join(pieces)).encode('utf-8')).hexdigest()
        existed = (
            db.table('import_batches')
            .select('id')
            .eq('source_id', source_id)
            .eq('chapter', title)
            .eq('content_hash', digest)
            .limit(1)
            .execute()
            .data
            or []
        )
        if existed:
            skipped += len(pieces)
            continue
        old_chunks = (
            db.table('fragments')
            .select('text_ba')
            .eq('source_id', source_id)
            .eq('chapter', title)
            .order('position')
            .execute()
            .data
            or []
        )
        if old_chunks and [row['text_ba'] for row in old_chunks] == pieces:
            db.table('import_batches').insert(
                {'source_id': source_id, 'chapter': title, 'content_hash': digest}
            ).execute()
            skipped += len(pieces)
            continue
        existing = (
            db.table('fragments')
            .select('position')
            .eq('source_id', source_id)
            .order('position', desc=True)
            .limit(1)
            .execute()
            .data
            or []
        )
        start = int(existing[0]['position']) if existing else 0
        for i, piece in enumerate(pieces, 1):
            db.table('fragments').insert(
                {'source_id': source_id, 'text_ba': piece, 'chapter': title, 'position': start + i}
            ).execute()
            created += 1
        db.table('import_batches').insert(
            {'source_id': source_id, 'chapter': title, 'content_hash': digest}
        ).execute()
    print(f'Создано {created}, пропущено {skipped}. Источник: {source_id}')


if __name__ == '__main__':
    main()
