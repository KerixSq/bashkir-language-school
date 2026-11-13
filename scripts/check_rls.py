"""Проверка публичных прав Supabase реальными запросами."""

import os

CLOSED = (
    'users',
    'answers',
    'classes',
    'api_keys',
    'external_answers',
    'expert_decisions',
    'status_history',
    'synonym_map',
    'user_stats',
    'expert_review_queue',
    'phrasebook_rows',
    'config',
    'fragments',
    'fragment_pairs',
    'sources',
    'schools',
    'lang_pairs',
    'badges',
    'user_badges',
    'import_batches',
)
PUBLIC = (
    'translations_export',
    'leaderboard_users',
    'leaderboard_classes',
    'leaderboard_schools',
    'adventure_progress',
)
PERSONAL_COLUMNS = ('user_id', 'telegram_id', 'username', 'display_name')


def error_code(error: Exception) -> str:
    """Ошибку транспорта нельзя принимать за отказ в доступе."""
    return str(getattr(error, 'code', '') or '')


def permission_denied(error: Exception) -> bool:
    return error_code(error) == '42501'


def unknown_column(error: Exception) -> bool:
    return error_code(error) in ('42703', 'PGRST204')


def check_closed(client, table: str) -> None:
    try:
        client.table(table).select('*').limit(1).execute()
    except Exception as error:
        if not permission_denied(error):
            raise AssertionError(
                f'{table}: не подтверждён запрет доступа; ошибка {type(error).__name__} '
                f'(код {error_code(error) or "отсутствует"})'
            ) from error
    else:
        raise AssertionError(f'{table}: публичный SELECT выполнился')
    print('PASS — доступ закрыт:', table)


def check_public(client, view: str) -> None:
    response = client.table(view).select('*').limit(1).execute()
    rows = response.data or []
    if view in PUBLIC:
        if rows and set(PERSONAL_COLUMNS).intersection(rows[0]):
            raise AssertionError('В рейтинге найдены персональные поля')
        # Даже пустой view не должен иметь запрещённые колонки.
        for column in PERSONAL_COLUMNS:
            try:
                client.table(view).select(column).limit(1).execute()
            except Exception as error:
                if not unknown_column(error):
                    raise AssertionError(
                        f'{view}.{column}: не подтверждено отсутствие поля '
                        f'({type(error).__name__}, {error_code(error)})'
                    ) from error
            else:
                raise AssertionError(f'В публичном рейтинге есть поле {column}')
    print('PASS — публичное представление:', view)


def main() -> None:
    from supabase import create_client

    if __package__:
        from .settings import load_settings
    else:
        from settings import load_settings
    os.environ.update(load_settings())
    url = os.getenv('SUPABASE_URL', '').strip()
    key = os.getenv('SUPABASE_PUBLIC_KEY', '').strip()
    if not url or not key:
        raise SystemExit('Заполни SUPABASE_URL и SUPABASE_PUBLIC_KEY в .env')
    client = create_client(url, key)
    for table in CLOSED:
        check_closed(client, table)
    for view in PUBLIC:
        check_public(client, view)
    print('PASS — публичные права проверены реальными запросами')


if __name__ == '__main__':
    main()
