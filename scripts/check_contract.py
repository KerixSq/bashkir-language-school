"""Статическая сверка связей SQL, бота и документации без обращения к БД."""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TABLES = (
    'users',
    'answers',
    'fragment_pairs',
    'synonym_map',
    'expert_decisions',
    'status_history',
    'api_keys',
    'external_answers',
    'import_batches',
    'phrasebook_rows',
)
RPC = (
    'get_next_fragment',
    'submit_answer',
    'get_class_report',
    'create_teacher_class',
    'expert_list_queue',
    'expert_resolve',
    'api_get_fragments',
    'api_submit_answer',
    'web_register',
    'web_profile',
    'web_next_fragment',
    'web_submit_answer',
    'web_skip_fragment',
    'import_audio_fragments',
    'claim_daily_reminders',
)
COMMANDS = (
    'start',
    'task',
    'pair',
    'join',
    'remind',
    'cancel',
    'top',
    'me',
    'report',
    'newclass',
    'privacy',
    'delete_me',
    'help',
)


def assert_contains(pattern: str, text: str, label: str) -> None:
    if not re.search(pattern, text, flags=re.I | re.S):
        raise AssertionError(label)


def verify() -> None:
    def read(file: str) -> str:
        return (ROOT / file).read_text(encoding='utf-8')

    schema, logic, seed = read('sql/schema.sql'), read('sql/logic.sql'), read('sql/seed.sql')
    stage3 = read('sql/migrations/20261113_stage3_hardening.sql')
    stage4 = read('sql/migrations/20261113_stage4_phrasebooks.sql')
    sources = schema + '\n' + logic

    for table in TABLES:
        assert_contains(
            r'create\s+table\s+if\s+not\s+exists\s+public\.' + table + r'\b',
            sources,
            f'Нет таблицы: {table}',
        )
        assert_contains(
            r'alter\s+table\s+public\.' + table + r'\s+enable\s+row\s+level\s+security',
            sources,
            f'RLS не включён: {table}',
        )

    defined = set(
        re.findall(r'create\s+or\s+replace\s+function\s+public\.(\w+)\s*\(', logic, flags=re.I)
    )
    for function in RPC:
        if function not in defined:
            raise AssertionError(f'Отсутствует RPC в logic.sql: {function}')

    python_code = '\n'.join(
        path.read_text(encoding='utf-8')
        for folder in ('bot', 'scripts')
        for path in (ROOT / folder).rglob('*.py')
    )
    python_calls = set(re.findall(r'\.rpc\(\s*[\'\"](\w+)[\'\"]', python_code))
    for function in python_calls:
        if function not in defined:
            raise AssertionError(f'В Python вызывается неизвестная RPC: {function}')

    bot_code = '\n'.join(path.read_text(encoding='utf-8') for path in (ROOT / 'bot').rglob('*.py'))
    for command in COMMANDS:
        if command == 'start':
            assert_contains(r'CommandStart\(\)', bot_code, 'Нет /start')
        else:
            assert_contains(
                r'Command\([\'\"]' + command + r'[\'\"]\)', bot_code, f'Нет команды /{command}'
            )
    assert_contains(
        r'revoke all on function public.claim_daily_reminders\(timestamptz,integer\) from public,anon,authenticated',
        logic,
        'Reminder claims must remain private',
    )

    for param in (
        'daily_goal',
        'daily_points_cap',
        'min_answer_seconds',
        'vote_weight_step',
        'vote_weight_min',
        'vote_weight_max',
        'teacher_invite_code',
        'expert_access_hash',
    ):
        if f"'{param}'" not in seed:
            raise AssertionError(f'Нет настройки: {param}')

    for path, migration in (('stage3', stage3), ('stage4', stage4)):
        assert_contains(r'\bbegin\s*;', migration, f'{path}: нет BEGIN')
        assert_contains(r'\bcommit\s*;\s*$', migration, f'{path}: нет COMMIT')
        if migration.count('$$') % 2:
            raise AssertionError(f'{path}: непарные $$')
    if 'pg_advisory_xact_lock(75241309)' in stage3:
        raise AssertionError('Глобальная блокировка осталась в stage3')
    if 'primary key (source_hash, row_id)' not in stage4:
        raise AssertionError('Неправильный ключ дедупликации корпуса')

    views = (
        'leaderboard_users',
        'leaderboard_classes',
        'leaderboard_schools',
        'translations_export',
        'expert_review_queue',
        'user_stats',
    )
    for view in views:
        assert_contains(
            r'create\s+(?:or\s+replace\s+)?view\s+public\.' + view + r'\b',
            logic,
            f'Нет view: {view}',
        )
    user_view = re.search(
        r'create\s+or\s+replace\s+view\s+public\.leaderboard_users\b(.*?);',
        logic,
        flags=re.I | re.S,
    )
    if user_view is None:
        raise AssertionError('Не найден leaderboard_users')
    for field in ('telegram_id', 'user_id', 'display_name', 'username'):
        if re.search(r'\b' + field + r'\b', user_view.group(1), flags=re.I):
            raise AssertionError(f'Персональное поле публичного рейтинга: {field}')

    site = read('web/index.html')
    if '.innerHTML' in site:
        raise AssertionError('Веб-страница использует innerHTML')
    for name in (
        'translations_export',
        'leaderboard_users',
        'leaderboard_classes',
        'leaderboard_schools',
    ):
        if name not in site:
            raise AssertionError(f'Веб не использует представление: {name}')

    importer = read('scripts/import_phrasebooks.py')
    for item in ('--dir', '--bad-share', '--seed', 'source_hash', 'row_id', 'ba-ru', 'ba-kk'):
        if item not in importer:
            raise AssertionError(f'Контракт импортёра: {item}')
    stage5 = read('sql/migrations/20261113_stage5_quality.sql')
    for item in (
        'last_skipped_fragment_pair_id',
        'file_name',
        'get_next_fragment',
        'skip_fragment',
        'begin;',
        'commit;',
    ):
        if item not in stage5.lower():
            raise AssertionError(f'Контракт миграции stage5: {item}')
    if (
        'last_skipped_fragment_pair_id' not in schema
        or 'last_skipped_fragment_pair_id' not in logic
    ):
        raise AssertionError('Выбор задания не совпадает с обновлённой схемой')
    for item in ('--dry-run', '--review-out', 'storage_id'):
        if item not in importer:
            raise AssertionError(f'Контракт проверки корпуса: {item}')
    if '--with-demo-texts' not in read('scripts/seed_demo.py'):
        raise AssertionError('Отсутствует флаг старых демо-текстов')
    for name in ('expert_resolve', 'api_get_fragments', 'api_submit_answer', 'translations_export'):
        if name not in read('API.md'):
            raise AssertionError(f'Нет API-документации: {name}')
    if 'CC BY 4.0' not in read('README.md'):
        raise AssertionError('Нет атрибуции корпуса')
    if "'flow:next'" not in read('bot/keyboards.py') or "F.data == 'flow:next'" not in read(
        'bot/handlers/tasks.py'
    ):
        raise AssertionError('Кнопка следующего задания не связана с обработчиком')
    if 'PUBLISHED_BOT_USERNAME' not in site or 'id="start-guide"' not in site:
        raise AssertionError('Нет маршрута для ученика на сайте')
    if '## Гипотезы для проверки' not in read('docs/STUDENT_RESEARCH.md'):
        raise AssertionError('Нет плана проверки спроса')
    game_script = read('scripts/export_learning_deck.py')
    for token in ('--dir', '--per-pair', '--seed', 'read_phrasebooks', 'select_translations'):
        if token not in game_script:
            raise AssertionError(f'Нет части экспорта веб-колоды: {token}')
    for marker in (
        'id="game-zone"',
        'id="game-start"',
        'id="game-check"',
        'id="game-badges"',
        'learning-deck.json',
        'game-question-type',
    ):
        if marker not in site:
            raise AssertionError(f'Отсутствует игровой интерфейс: {marker}')
    for token in (
        'create or replace view public.adventure_progress',
        'grant select on public.adventure_progress to anon, service_role',
    ):
        if token not in read('sql/logic.sql') or token not in read(
            'sql/migrations/20261113_stage6_expedition.sql'
        ):
            raise AssertionError(f'Отсутствует безопасный SQL-контракт экспедиции: {token}')
    stage7 = read('sql/migrations/20261113_stage7_runtime_fixes.sql')
    for token in ('begin_correction', 'for update', 'commit;'):
        if token not in stage7.lower():
            raise AssertionError(f'Missing stage7 correction race protection: {token}')
    if 'public.begin_correction' not in logic:
        raise AssertionError('Fresh installation is missing stage7 correction protection')
    for script in ('scripts/configure_local_env.py', 'scripts/doctor.py', 'scripts/run_local.ps1'):
        if not (ROOT / script).is_file():
            raise AssertionError(f'Missing local setup utility: {script}')
    if 'adventure_progress' not in site or 'community-confirmed' not in site:
        raise AssertionError('Нет подключения общей библиотеки к публичному представлению')
    if 'Игровой режим на сайте' not in read('docs/GAMEPLAY.md'):
        raise AssertionError('Нет правил веб-игры')
    print('PASS — связи SQL/Python, RLS-декларации, команды, view, миграции и документы')
    print('INFO — работоспособность SQL и RLS требует запуска на живой базе')


if __name__ == '__main__':
    verify()
