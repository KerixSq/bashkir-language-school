"""Read-only проверка готовности демонстрации на подключённом Supabase."""

import argparse

if __package__:
    from .import_phrasebooks import DATASET_URL
else:
    from import_phrasebooks import DATASET_URL


def evaluate(metrics: dict[str, int]) -> list[str]:
    warnings = []
    if not metrics['corpus_sources'] or not metrics['corpus_fragments']:
        warnings.append('Реальный корпус ещё не импортирован')
    if not metrics['pairs_ru']:
        warnings.append('Не найдены задания ba-ru')
    if not metrics['pairs_kk']:
        warnings.append('Не найдены задания ba-kk')
    if metrics['answers'] < 3 or metrics.get('voters', 0) < 3:
        warnings.append('Для живого согласования нужны ответы как минимум трёх учеников')
    if not metrics.get('demonstrable_consensus', 0):
        warnings.append('Нет подтверждённой фразы корпуса с тремя независимыми учениками')
    if not metrics['confirmed']:
        warnings.append('В базе пока нет подтверждённых переводов для показа')
    if not metrics['students']:
        warnings.append('Нужны зарегистрированные ученики для рейтинга')
    return warnings


def count_rows(db, table: str, **filters) -> int:
    builder = db.table(table).select('id', count='exact').limit(1)
    for field, value in filters.items():
        builder = builder.eq(field, value)
    result = builder.execute()
    if result.count is None:
        raise RuntimeError(f'{table}: Supabase не вернул count')
    return result.count


def collect_metrics(db) -> dict[str, int]:
    sources = db.table('sources').select('id').eq('url', DATASET_URL).limit(2).execute().data or []
    if len(sources) > 1:
        raise RuntimeError('У корпуса несколько источников в БД: проверь дубли')
    source_id = sources[0]['id'] if sources else None

    def source_pairs(lang_pair: str | None = None, status: str | None = None) -> int:
        if not source_id:
            return 0
        builder = (
            db.table('fragment_pairs')
            .select('id,fragments!inner(source_id)', count='exact')
            .eq('fragments.source_id', source_id)
            .limit(1)
        )
        if lang_pair:
            builder = builder.eq('lang_pair', lang_pair)
        if status:
            builder = builder.eq('status', status)
        result = builder.execute()
        if result.count is None:
            raise RuntimeError('Supabase не вернул число переводов корпуса')
        return result.count

    # Демо-ученики имеют отрицательные Telegram ID и не считаются в готовности.
    users = (
        db.table('users')
        .select('id', count='exact')
        .eq('role', 'student')
        .gt('telegram_id', 0)
        .limit(1)
        .execute()
    )
    real_answers = (
        db.table('answers')
        .select('id,users!inner(telegram_id)', count='exact')
        .gt('users.telegram_id', 0)
        .limit(1)
        .execute()
    )
    if users.count is None or real_answers.count is None:
        raise RuntimeError('Supabase не вернул реальные количества учеников и ответов')
    voters = set()
    votes_by_pair = {}
    if source_id:
        offset = 0
        while True:
            rows = (
                db.table('answers')
                .select('id,user_id,fragment_pair_id,users!inner(telegram_id,role),'
                        'fragment_pairs!inner(status,fragments!inner(source_id))')
                .gt('users.telegram_id', 0).eq('users.role', 'student')
                .eq('eligible', True)
                .eq('fragment_pairs.fragments.source_id', source_id)
                .order('id').range(offset, offset + 499).execute().data or []
            )
            for row in rows:
                voters.add(row['user_id'])
                if row['fragment_pairs']['status'] == 'confirmed':
                    votes_by_pair.setdefault(row['fragment_pair_id'], set()).add(row['user_id'])
            if len(rows) < 500:
                break
            offset += 500
    return {
        'corpus_sources': len(sources),
        'corpus_fragments': count_rows(db, 'fragments', source_id=source_id) if source_id else 0,
        'pairs_ru': source_pairs(lang_pair='ba-ru'),
        'pairs_kk': source_pairs(lang_pair='ba-kk'),
        'answers': real_answers.count,
        'confirmed': source_pairs(status='confirmed'),
        'expert_review': source_pairs(status='expert_review'),
        'students': users.count,
        'voters': len(voters),
        'demonstrable_consensus': sum(len(people) >= 3 for people in votes_by_pair.values()),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description='Проверка готовности проекта к показу')
    parser.add_argument(
        '--strict', action='store_true', help='Завершиться с ошибкой при предупреждениях'
    )
    args = parser.parse_args()
    try:
        if __package__:
            from .common import client
        else:
            from common import client
        metrics = collect_metrics(client())
    except Exception as error:
        print('FAIL: Supabase недоступен или структура не совпадает:', type(error).__name__)
        return 2
    labels = {
        'corpus_sources': 'Источников корпуса БГПУ',
        'corpus_fragments': 'Фрагментов корпуса',
        'pairs_ru': 'Переводов ba-ru',
        'pairs_kk': 'Переводов ba-kk',
        'answers': 'Ответов настоящих участников',
        'confirmed': 'Подтверждённых переводов корпуса БГПУ',
        'expert_review': 'На рассмотрении эксперта',
        'students': 'Зарегистрированных Telegram-учеников',
        'voters': 'Независимых учеников с допустимыми ответами на корпус',
        'demonstrable_consensus': 'Подтверждённых фраз с тремя независимыми учениками',
    }
    print('Состояние подключённой базы (данные не изменяются):')
    for key, label in labels.items():
        print(f'  {label}: {metrics[key]}')
    warnings = evaluate(metrics)
    for warning in warnings:
        print('ПРОВЕРЬ:', warning)
    if warnings:
        print('NOT READY: сначала закрой предупреждения перед защитой.')
        return 1 if args.strict else 0
    print('READY BY COUNTS: данные есть. Это не замена проверкам RLS, API и Telegram.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
