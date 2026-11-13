import asyncio
import os
from pathlib import Path

from dotenv import load_dotenv

from supabase import create_client

load_dotenv(Path(__file__).resolve().parents[1] / '.env')
URL = os.getenv('SUPABASE_URL', '').strip()
SECRET = (os.getenv('SUPABASE_SECRET_KEY') or os.getenv('SUPABASE_SERVICE_ROLE_KEY') or '').strip()
if not URL or not SECRET:
    raise SystemExit('Заполни SUPABASE_URL и SUPABASE_SECRET_KEY в .env')

_db = create_client(URL, SECRET)


async def query(operation):
    return await asyncio.to_thread(operation)


async def select(table: str, columns: str = '*', **filters) -> list[dict]:
    def operation():
        builder = _db.table(table).select(columns)
        for key, value in filters.items():
            builder = builder.eq(key, value)
        return builder.execute().data or []

    return await query(operation)


async def user_by_telegram(telegram_id: int) -> dict | None:
    found = await select('users', telegram_id=telegram_id)
    return found[0] if found else None


async def update_user(user_id: str, changes: dict) -> None:
    await query(lambda: _db.table('users').update(changes).eq('id', user_id).execute())


async def register_user(telegram_id: int) -> dict:
    await query(
        lambda: (
            _db.table('users')
            .upsert(
                {'telegram_id': telegram_id, 'state': 'choosing_nickname'},
                on_conflict='telegram_id',
                ignore_duplicates=True,
            )
            .execute()
        )
    )
    found = await user_by_telegram(telegram_id)
    if found is None:
        raise RuntimeError('Не получилось создать пользователя')
    return found


async def rpc(function: str, arguments: dict):
    result = await query(lambda: _db.rpc(function, arguments).execute().data)
    if isinstance(result, list) and len(result) == 1:
        return result[0]
    return result


async def lang_pairs() -> list[dict]:
    # Нельзя предлагать пару, для которой пока нет ни одного задания.
    pairs = await query(
        lambda: _db.table('lang_pairs').select('code,name').order('code').execute().data or []
    )
    available = []
    for pair in pairs:
        found = await query(
            lambda code=pair['code']: (
                _db.table('fragment_pairs')
                .select('id')
                .eq('lang_pair', code)
                .in_('status', ['collecting', 'confirmed'])
                .limit(1)
                .execute()
                .data
                or []
            )
        )
        if found:
            available.append(pair)
    return available


async def top_users(period: str = 'day') -> list[dict]:
    field = {
        'day': 'day_answers',
        'week': 'week_answers',
        'month': 'month_answers',
        'year': 'year_answers',
    }[period]
    return await query(
        lambda: (
            _db.table('leaderboard_users')
            .select(f'name,points,level,{field}')
            .order(field, desc=True)
            .limit(10)
            .execute()
            .data
            or []
        )
    )


async def rank_summary(user: dict) -> tuple[int, int, int, int] | None:
    if user.get('role') != 'student' or not user.get('class_id'):
        return None
    all_classes = await query(
        lambda: (
            _db.table('leaderboard_classes')
            .select('class_id,points')
            .order('points', desc=True)
            .execute()
            .data
            or []
        )
    )
    all_students = await query(
        lambda: (
            _db.table('users')
            .select('id,points')
            .eq('class_id', user['class_id'])
            .eq('role', 'student')
            .order('points', desc=True)
            .execute()
            .data
            or []
        )
    )
    class_rank = next(
        (i for i, row in enumerate(all_classes, 1) if row['class_id'] == user['class_id']), 0
    )
    student_rank = next((i for i, row in enumerate(all_students, 1) if row['id'] == user['id']), 0)
    return (class_rank, len(all_classes), student_rank, len(all_students))


async def user_stats(user_id: str) -> dict:
    found = await select('user_stats', user_id=user_id)
    return found[0] if found else {}


async def user_badges(user_id: str) -> list[str]:
    rows = await query(
        lambda: (
            _db.table('user_badges')
            .select('badge_code,badges(title)')
            .eq('user_id', user_id)
            .execute()
            .data
            or []
        )
    )
    return [row['badges']['title'] for row in rows if row.get('badges')]


async def daily_goal() -> int:
    rows = await select('config', 'value', key='daily_goal')
    return int(rows[0]['value']) if rows else 5


async def class_for_code(column: str, code: str) -> dict | None:
    if column not in ('join_code', 'teacher_code'):
        raise ValueError('Неизвестный тип кода класса')
    rows = await select('classes', 'id', **{column: code})
    return rows[0] if rows else None


async def class_secret(class_id: str) -> str | None:
    rooms = await select('classes', 'teacher_code', id=class_id)
    return rooms[0]['teacher_code'] if rooms else None
