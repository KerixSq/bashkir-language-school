import argparse
import os
import secrets
import sys
from datetime import datetime, timedelta, timezone

from common import client
from pure import new_api_key, new_join_code, secret_hash

from supabase import create_client


def check(condition: bool, label: str) -> None:
    if not condition:
        raise AssertionError(label)
    print('PASS', label)


def rejected(action, label: str) -> None:
    try:
        action()
    except Exception as error:
        # Ошибки SQL-триггера имеют код P0001. Потеря сети — не PASS.
        if str(getattr(error, 'code', '')) != 'P0001':
            raise AssertionError(
                f'{label}: вместо ожидаемого отказа получено {type(error).__name__}'
            ) from error
        print('PASS', label)
    else:
        raise AssertionError(label)


def main() -> None:
    parser = argparse.ArgumentParser(description='Сквозная проверка на реальном Supabase')
    parser.add_argument(
        '--expert-code',
        default=os.getenv('EXPERT_ACCESS_CODE'),
        help='Код эксперта (предпочтительно EXPERT_ACCESS_CODE в окружении)',
    )
    args = parser.parse_args()
    if not args.expert_code:
        parser.error('Задай EXPERT_ACCESS_CODE или --expert-code')
    db = client()
    public_key = os.getenv('SUPABASE_PUBLIC_KEY')
    url = os.getenv('SUPABASE_URL')
    if not public_key or not url:
        raise SystemExit('Для проверки anon RPC заполни SUPABASE_URL и SUPABASE_PUBLIC_KEY')
    public_db = create_client(url, public_key)
    stamp = secrets.token_hex(5)
    pair_code = 'ba-smoke-' + stamp
    saved = {'users': [], 'pairs': [], 'fragments': [], 'keys': []}

    def add_pair(name, wrong=None):
        f = (
            db.table('fragments')
            .insert(
                {
                    'source_id': saved['source'],
                    'chapter': 'Техническая проверка',
                    'position': len(saved['fragments']) + 1,
                    'text_ba': f'SMOKE {name}: техническая строка, не башкирский текст.',
                }
            )
            .execute()
            .data[0]
        )
        saved['fragments'].append(f['id'])
        row = (
            db.table('fragment_pairs')
            .insert(
                {
                    'fragment_id': f['id'],
                    'lang_pair': pair_code,
                    'auto_translation': 'Сегодня мы проверяем запись.',
                    'bad_translation': wrong,
                }
            )
            .execute()
            .data[0]
        )
        saved['pairs'].append(row['id'])
        return row['id']

    def user(index):
        data = (
            db.table('users')
            .insert(
                {
                    'telegram_id': -(2_000_000_000_000 + secrets.randbelow(900_000_000)),
                    'nickname': f'Smoke {stamp}{index}',
                    'role': 'student',
                    'class_id': saved['class'],
                    'lang_pair': pair_code,
                }
            )
            .execute()
            .data[0]
        )
        saved['users'].append(data['id'])
        return data['id']

    def assign(who, pair, variant='auto', action='confirm', correction=None):
        ago = (datetime.now(timezone.utc) - timedelta(seconds=12)).isoformat()
        db.table('users').update(
            {
                'current_fragment_pair_id': pair,
                'current_shown_variant': variant,
                'current_shown_at': ago,
                'last_answer_at': ago,
                'state': 'awaiting_correction' if action == 'correct' else 'idle',
            }
        ).eq('id', who).execute()
        return (
            db.rpc(
                'submit_answer',
                {
                    'p_user_id': who,
                    'p_fragment_pair_id': pair,
                    'p_action': action,
                    'p_text': correction,
                },
            )
            .execute()
            .data
        )

    def progress():
        return (
            public_db.table('adventure_progress')
            .select('confirmed')
            .eq('lang_pair', pair_code)
            .single()
            .execute()
            .data['confirmed']
        )

    try:
        db.table('lang_pairs').insert({'code': pair_code, 'name': 'Smoke тест'}).execute()
        saved['lang_pair'] = pair_code
        school = db.table('schools').insert({'name': f'SMOKE {stamp}'}).execute().data[0]
        saved['school'] = school['id']
        room = (
            db.table('classes')
            .insert(
                {
                    'school_id': saved['school'],
                    'name': 'Проверка',
                    'join_code': new_join_code(),
                    'teacher_code': secrets.token_urlsafe(32),
                }
            )
            .execute()
            .data[0]
        )
        saved['class'] = room['id']
        source = (
            db.table('sources')
            .insert(
                {
                    'title': f'SMOKE {stamp} · тестовый источник',
                    'kind': 'text',
                    'license': 'test',
                }
            )
            .execute()
            .data[0]
        )
        saved['source'] = source['id']
        pair1 = add_pair('consensus')
        check(progress() == 0, 'библиотека начинает с нуля')
        users = [user(i) for i in range(8)]
        task = db.rpc('get_next_fragment', {'p_user_id': users[0]}).execute().data
        check(task and task['fragment_pair_id'] == pair1, 'получено задание')
        early = (
            db.rpc(
                'submit_answer',
                {
                    'p_user_id': users[0],
                    'p_fragment_pair_id': pair1,
                    'p_action': 'confirm',
                    'p_text': None,
                },
            )
            .execute()
            .data
        )
        check(early.get('too_fast') is True, 'слишком быстрый ответ отклонён')
        for i in range(3):
            result = assign(users[i], pair1)
            check(result.get('points_awarded', 0) >= 10, f'голос {i + 1} начислен')
        check(progress() == 1, 'три независимых голоса увеличили библиотеку на один')
        check(
            db.table('fragment_pairs')
            .select('status,final_translation')
            .eq('id', pair1)
            .single()
            .execute()
            .data['final_translation']
            == 'Сегодня мы проверяем запись.',
            'консенсус сохраняет исходный регистр и пунктуацию',
        )
        exported = (
            db.table('translations_export')
            .select('translation')
            .eq('fragment_id', saved['fragments'][0])
            .single()
            .execute()
            .data
        )
        check(exported['translation'].endswith('.'), 'экспорт возвращает читаемый текст')
        repeated = (
            db.rpc(
                'submit_answer',
                {
                    'p_user_id': users[0],
                    'p_fragment_pair_id': pair1,
                    'p_action': 'confirm',
                    'p_text': None,
                },
            )
            .execute()
            .data
        )
        check(repeated.get('duplicate') is True, 'дубль не даёт очков')
        check(progress() == 1, 'повторный ответ не увеличивает библиотеку')
        check(
            public_db.table('translations_export')
            .select('status,confirmed')
            .eq('fragment_id', saved['fragments'][0])
            .single()
            .execute()
            .data
            == {'status': 'confirmed', 'confirmed': 3},
            'перевод доступен через публичный API',
        )
        check(
            db.rpc('begin_correction', {'p_user_id': users[0], 'p_fragment_pair_id': pair1})
            .execute()
            .data
            is False,
            'устаревшее исправление не меняет FSM',
        )
        pair2 = add_pair('planted', 'Завтра мы проверяли запись.')
        missed = assign(users[0], pair2, variant='bad')
        check(
            missed['points_awarded'] == 0 and missed['correct_translation'],
            'подтверждение ошибки даёт 0 и пояснение',
        )
        caught = assign(
            users[1],
            pair2,
            variant='bad',
            action='correct',
            correction='Сегодня мы проверяем запись.',
        )
        check(caught.get('caught_planted_error') is True, 'ошибка поймана')
        eligible = (
            db.table('answers')
            .select('eligible')
            .eq('user_id', users[0])
            .eq('fragment_pair_id', pair2)
            .single()
            .execute()
            .data
        )
        check(eligible['eligible'] is False, 'ошибочный ответ исключён из голосования')
        pair3 = add_pair('expert')
        for i in range(5):
            assign(
                users[i],
                pair3,
                action='correct',
                correction=f'Предложение со смысловым вариантом номер {i + 1}.',
            )
        status = db.table('fragment_pairs').select('status').eq('id', pair3).single().execute().data
        check(status['status'] == 'expert_review', 'спорный фрагмент отправлен эксперту')
        queue = public_db.rpc('expert_list_queue', {'p_code': args.expert_code}).execute().data
        check(any(r['fragment_pair_id'] == pair3 for r in queue), 'очередь доступна эксперту')
        resolved = (
            public_db.rpc(
                'expert_resolve',
                {
                    'p_code': args.expert_code,
                    'p_fragment_pair_id': pair3,
                    'p_translation': 'Итоговая редакция эксперта.',
                },
            )
            .execute()
            .data
        )
        check(resolved['status'] == 'confirmed', 'эксперт сохранил решение')
        check(progress() == 2, 'экспертное решение увеличило библиотеку')
        db.table('sources').update({'license': 'demo'}).eq('id', saved['source']).execute()
        check(progress() == 0, 'демо-источник исключён из библиотеки')
        db.table('sources').update({'license': 'test'}).eq('id', saved['source']).execute()
        rejected(
            lambda: public_db.rpc('expert_list_queue', {'p_code': 'wrong'}).execute(),
            'неверный экспертный код отклонён',
        )
        rejected(
            lambda: public_db.rpc(
                'get_class_report', {'p_teacher_code': room['join_code']}
            ).execute(),
            'ученический код не открывает отчёт',
        )
        rejected(
            lambda: public_db.rpc('get_class_report', {'p_teacher_code': 'not-a-secret'}).execute(),
            'неверный код не открывает отчёт',
        )
        report = (
            public_db.rpc('get_class_report', {'p_teacher_code': room['teacher_code']})
            .execute()
            .data
        )
        check(report['students_count'] == len(users), 'учитель видит только свой класс')
        token = new_api_key()
        api_key = (
            db.table('api_keys')
            .insert(
                {
                    'partner_name': 'smoke',
                    'key_hash': secret_hash(token),
                    'permission': 'write',
                    'expires_at': (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
                }
            )
            .execute()
            .data[0]
        )
        saved['keys'].append(api_key['id'])
        catalog = (
            public_db.rpc(
                'api_get_fragments', {'p_key': token, 'p_lang_pair': pair_code, 'p_limit': 10}
            )
            .execute()
            .data
        )
        check(bool(catalog['items']), 'внешний API читает фрагменты по ключу')
        external = {
            'p_key': token,
            'p_external_user': 'test-user',
            'p_fragment_pair_id': pair1,
            'p_translation': 'Внешний пример.',
        }
        result = public_db.rpc('api_submit_answer', external).execute().data
        check(result['accepted'] is True, 'API принимает внешнее предложение')
        check(
            public_db.rpc('api_submit_answer', external).execute().data['duplicate'] is True,
            'API не дублирует внешнее предложение',
        )
        check(progress() == 2, 'внешнее предложение не является ученическим голосом')
        db.table('api_keys').update({'revoked_at': datetime.now(timezone.utc).isoformat()}).eq(
            'id', api_key['id']
        ).execute()
        rejected(
            lambda: public_db.rpc(
                'api_get_fragments', {'p_key': token, 'p_lang_pair': pair_code}
            ).execute(),
            'отозванный API-ключ отклонён',
        )
        rejected(
            lambda: public_db.rpc(
                'api_get_fragments', {'p_key': 'wrong', 'p_lang_pair': pair_code}
            ).execute(),
            'неверный API-ключ отклонён',
        )
        pair4 = add_pair('cap1', 'Неправильный пример.')
        for i in range(7):
            more = pair4 if i == 0 else add_pair(f'cap{i}', 'Неправильный пример.')
            assign(users[7], more, 'bad', 'correct', 'Сегодня мы проверяем запись.')
        earned = (
            db.table('answers').select('points_awarded').eq('user_id', users[7]).execute().data
            or []
        )
        check(
            sum(row['points_awarded'] for row in earned) <= 150, 'дневной потолок очков не превышен'
        )
        check(
            bool(
                db.table('leaderboard_users')
                .select('name')
                .eq('name', f'Smoke {stamp}0')
                .execute()
                .data
            ),
            'публичный рейтинг обновлён',
        )
        print('ИТОГ: PASS — все пункты успешно выполнены')
    except Exception as exc:
        print(f'ИТОГ: FAIL — {type(exc).__name__}: {exc}', file=sys.stderr)
        raise
    finally:
        targets = [
            ('external_answers', 'api_key_id', saved['keys']),
            ('api_keys', 'id', saved['keys']),
            ('user_badges', 'user_id', saved['users']),
            ('answers', 'user_id', saved['users']),
            ('users', 'id', saved['users']),
            ('expert_decisions', 'fragment_pair_id', saved['pairs']),
            ('status_history', 'fragment_pair_id', saved['pairs']),
            ('fragment_pairs', 'id', saved['pairs']),
            ('fragments', 'id', saved['fragments']),
            ('sources', 'id', [saved['source']] if 'source' in saved else []),
            ('classes', 'id', [saved['class']] if 'class' in saved else []),
            ('schools', 'id', [saved['school']] if 'school' in saved else []),
            ('lang_pairs', 'code', [saved['lang_pair']] if 'lang_pair' in saved else []),
        ]
        failure = False
        for table, key, ids in targets:
            if not ids:
                continue
            try:
                db.table(table).delete().in_(key, ids).execute()
            except Exception as exc:
                failure = True
                print(f'ОШИБКА очистки {table}: {type(exc).__name__}: {exc}', file=sys.stderr)
        print('Очистка:', 'ОШИБКИ (проверь SQL Editor)' if failure else 'выполнена')
        if failure:
            raise RuntimeError('Сквозной тест оставил временные данные в Supabase')


if __name__ == '__main__':
    main()
