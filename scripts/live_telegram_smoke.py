"""Read-only observer of real Telegram polling, human actions and test DB state.

Never calls getUpdates, sends user messages, changes webhook or writes to the DB.
Requires a deliberately selected test-only environment; live execution is not CI.
"""

import argparse
import asyncio
import json
import logging
import queue
import re
import shutil
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from bot.live_probe import db_fingerprint  # noqa: E402
from scripts.settings import read_env  # noqa: E402


def settings(path):
    if not path.is_file():
        raise FileNotFoundError('Dedicated test environment is not prepared')
    values = read_env(path)  # Explicit file only; never inherit a stale cloud key.
    if values.get('LIVE_TELEGRAM_TEST_ONLY') != '1':
        raise ValueError('Set LIVE_TELEGRAM_TEST_ONLY=1 only for an isolated test database')
    if not values.get('SUPABASE_URL') and values.get('SERVICE_ROLE_KEY'):
        values.update(
            SUPABASE_URL='http://127.0.0.1:54321',
            SUPABASE_SECRET_KEY=values['SERVICE_ROLE_KEY'],
        )
    for name in ('TELEGRAM_BOT_TOKEN', 'SUPABASE_URL', 'SUPABASE_SECRET_KEY'):
        if not values.get(name):
            raise ValueError('Missing setting: ' + name)
    parsed = urlparse(values['SUPABASE_URL'])
    if parsed.scheme not in ('http', 'https') or not parsed.hostname or parsed.username:
        raise ValueError('Invalid test API URL')
    if not values.get('LIVE_TELEGRAM_TEST_USER_ID', '').isdigit():
        raise ValueError('A numeric dedicated test account ID is required')
    if int(values['LIVE_TELEGRAM_TEST_USER_ID']) <= 0:
        raise ValueError('Test account ID must be positive')
    return values


def read_probe(path, values, bot_id):
    data = json.loads(path.read_text(encoding='utf-8'))
    if (
        data.get('version') != 1
        or data.get('mode') != 'polling'
        or data.get('bot_id') != bot_id
        or data.get('user_id') != int(values['LIVE_TELEGRAM_TEST_USER_ID'])
        or data.get('db') != db_fingerprint(values['SUPABASE_URL'])
        or data.get('stopped')
        or not 0 <= time.time() - data.get('heartbeat', 0) < 15
    ):
        raise ValueError('Live probe is stale or belongs to a different bot/account/database')
    return data


def witnessed(probe, after, action, method=None, target=None):
    events = [event for event in probe.get('events', []) if event['at'] >= after]
    for event in events:
        if event['kind'] != 'incoming' or event['action'] != action:
            continue
        if target is not None and event.get('target') != target:
            continue
        related = [other for other in events if other['update'] == event['update']]
        if any(other['kind'] == 'handled' for other in related) and any(
            other['kind'] == 'delivered' and (method is None or other['method'] == method)
            for other in related
        ):
            return True
    return False


def timed_input(prompt, timeout):
    answers = queue.Queue()

    def read():
        try:
            answers.put(input(prompt))
        except EOFError:
            answers.put('skip')

    threading.Thread(target=read, daemon=True).start()
    try:
        return answers.get(timeout=timeout).strip().lower()
    except queue.Empty:
        return 'skip'


class Report:
    def __init__(self, path=None):
        self.rows = []
        self.path = path
        if path and path.is_file():
            archive = path.with_name(path.stem + '-previous-' + str(time.time_ns()) + '.json')
            shutil.copyfile(path, archive)
        if path:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.with_suffix('.summary.json').write_text(
                json.dumps({'status': 'SKIP', 'complete': False}), encoding='utf-8'
            )

    def progress(self, name, phase):
        if self.path:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.with_suffix('.progress.json').write_text(
                json.dumps({'scenario': name, 'phase': phase}), encoding='utf-8'
            )

    def add(self, name, status, detail):
        self.rows.append({'scenario': name, 'status': status, 'detail': detail})
        print(f'{status}: {name} — {detail}', flush=True)
        if self.path:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(
                json.dumps(self.rows, ensure_ascii=False, indent=2), encoding='utf-8'
            )

    def finish(self, path):
        statuses = {row['status'] for row in self.rows}
        code = 1 if 'FAIL' in statuses else 2 if 'SKIP' in statuses or not statuses else 0
        print(
            'LIVE E2E: '
            + ('PASS' if code == 0 else 'FAIL' if code == 1 else 'SKIP / MANUAL REQUIRED')
        )
        if path:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(self.rows, ensure_ascii=False, indent=2), encoding='utf-8')
            path.with_suffix('.summary.json').write_text(
                json.dumps(
                    {
                        'status': 'PASS' if code == 0 else 'FAIL' if code == 1 else 'SKIP',
                        'complete': True,
                    }
                ),
                encoding='utf-8',
            )
            self.progress('completed', 'PASS' if code == 0 else 'FAIL' if code == 1 else 'SKIP')
        return code


class Database:
    def __init__(self, values):
        from supabase import ClientOptions, create_client

        self.api = create_client(
            values['SUPABASE_URL'],
            values['SUPABASE_SECRET_KEY'],
            options=ClientOptions(postgrest_client_timeout=10),
        )
        self.telegram_id = int(values['LIVE_TELEGRAM_TEST_USER_ID'])
        self.user_id = None

    def snapshot(self):
        fields = (
            'id,nickname,role,class_id,lang_pair,state,points,current_fragment_pair_id,deleted_at'
        )
        rows = (
            self.api.table('users')
            .select(fields)
            .eq('telegram_id', self.telegram_id)
            .limit(1)
            .execute()
            .data
        )
        user = rows[0] if rows else None
        if user:
            self.user_id = user['id']
        answers = (
            self.api.table('answers')
            .select('id,fragment_pair_id,action,points_awarded')
            .eq('user_id', self.user_id)
            .execute()
            .data
            if self.user_id
            else []
        )
        if len({row['fragment_pair_id'] for row in answers}) != len(answers):
            raise ValueError('Duplicate database answers detected')
        deleted = False
        if user is None and self.user_id:
            rows = (
                self.api.table('users')
                .select('deleted_at,nickname,points')
                .eq('id', self.user_id)
                .execute()
                .data
            )
            deleted = bool(
                rows
                and rows[0]['deleted_at']
                and rows[0]['nickname'] is None
                and rows[0]['points'] == 0
            )
        return {
            'user': user,
            'answers': {row['fragment_pair_id']: row for row in answers},
            'deleted': deleted,
        }


def field(snapshot, key):
    return (snapshot['user'] or {}).get(key)


def unchanged(before, after):
    return before['answers'] == after['answers'] and field(before, 'points') == field(
        after, 'points'
    )


def confirmed_once(before, after):
    rows = [row for pair, row in after['answers'].items() if pair not in before['answers']]
    return (
        len(rows) == 1
        and rows[0]['action'] == 'confirm'
        and rows[0]['points_awarded'] > 0
        and (field(after, 'points') or 0) - (field(before, 'points') or 0)
        >= rows[0]['points_awarded']
    )


@dataclass
class Step:
    name: str
    instruction: str
    action: str
    check: object
    method: str | None = None


def registration_steps(role):
    return [
        Step(
            'registration/start',
            'Отправьте /start.',
            '/start',
            lambda b, a: field(a, 'state') == 'choosing_nickname',
        ),
        Step(
            'registration/cancel',
            'Отправьте /cancel во время регистрации.',
            '/cancel',
            lambda b, a: field(a, 'state') == 'idle' and not field(a, 'nickname'),
        ),
        Step(
            'registration/resume',
            'Снова отправьте /start.',
            '/start',
            lambda b, a: field(a, 'state') == 'choosing_nickname',
        ),
        Step(
            'registration/invalid',
            'Отправьте ___ — никнейм должен быть отклонён.',
            'text',
            lambda b, a: not field(a, 'nickname') and field(a, 'state') == 'choosing_nickname',
        ),
        Step(
            'registration/nickname',
            'Введите тестовый никнейм, например LiveSchoolQA.',
            'text',
            lambda b, a: bool(field(a, 'nickname')) and field(a, 'state') == 'choosing_role',
        ),
        Step(
            'registration/role',
            'Нажмите «Ученик».' if role == 'student' else 'Нажмите «Преподаватель».',
            'role:' + role,
            lambda b, a: field(a, 'role') == role and field(a, 'state') == 'joining_class',
        ),
        Step(
            'registration/class',
            'Введите код ТЕСТОВОГО класса (для teacher — код преподавателя).',
            'text',
            lambda b, a: bool(field(a, 'class_id')) and field(a, 'state') == 'choosing_pair',
        ),
        Step(
            'registration/pair',
            'Выберите доступную языковую пару.',
            'pair',
            lambda b, a: bool(field(a, 'lang_pair')) and field(a, 'state') == 'idle',
        ),
    ]


def registration_plan(user, role):
    """Resume without resetting an existing partial test registration."""
    steps = registration_steps((user or {}).get('role') or role)
    if not user or not user.get('nickname'):
        return steps
    for field_name, state, index in (
        ('role', 'choosing_role', 5),
        ('class_id', 'joining_class', 6),
        ('lang_pair', 'choosing_pair', 7),
    ):
        if not user.get(field_name):
            return [
                Step(
                    'registration/resume',
                    'Отправьте /start для продолжения регистрации.',
                    '/start',
                    lambda b, a, state=state: field(a, 'state') == state,
                )
            ] + steps[index:]
    return []


def task_steps():
    return [
        Step(
            'returning/start',
            'Отправьте /start: профиль должен восстановиться.',
            '/start',
            lambda b, a: field(a, 'state') == 'idle' and unchanged(b, a),
        ),
        Step(
            'task/receive',
            'Отправьте /task, убедитесь, что видны фраза из БД и кнопки.',
            '/task',
            lambda b, a: bool(field(a, 'current_fragment_pair_id')),
        ),
        Step(
            'task/skip',
            'Нажмите «Пропустить».',
            'task:skip',
            lambda b, a: not field(a, 'current_fragment_pair_id') and unchanged(b, a),
        ),
        Step(
            'task/next',
            'Отправьте /task для следующей фразы.',
            '/task',
            lambda b, a: bool(field(a, 'current_fragment_pair_id')),
        ),
        Step(
            'correction/begin',
            'Нажмите «Исправить». Пока не отправляйте перевод.',
            'task:correct',
            lambda b, a: field(a, 'state') == 'awaiting_correction',
        ),
        Step(
            'correction/cancel',
            'Отправьте /cancel во время исправления.',
            '/cancel',
            lambda b, a: (
                field(a, 'state') == 'idle'
                and not field(a, 'current_fragment_pair_id')
                and unchanged(b, a)
            ),
        ),
        Step(
            'task/confirm',
            'Получите /task, подождите несколько секунд и нажмите «Верно».',
            'task:confirm',
            confirmed_once,
        ),
        Step(
            'task/duplicate',
            'Если старая кнопка доступна во втором клиенте, нажмите её повторно. Иначе пропустите этот шаг.',
            'task:confirm',
            lambda b, a: unchanged(b, a),
        ),
        Step(
            'correction/new',
            'Получите /task и нажмите «Исправить» для новой фразы.',
            'task:correct',
            lambda b, a: field(a, 'state') == 'awaiting_correction',
        ),
        Step(
            'restart/persistence',
            'Остановите ЕДИНСТВЕННЫЙ бот Ctrl+C, запустите его заново с тем же env и отправьте /start. Состояние исправления должно сохраниться.',
            '/start',
            lambda b, a: (
                field(a, 'state') == field(b, 'state') == 'awaiting_correction'
                and field(a, 'current_fragment_pair_id') == field(b, 'current_fragment_pair_id')
                and unchanged(b, a)
            ),
        ),
        Step(
            'correction/submit',
            'Отправьте корректный отличный перевод, который вы можете обосновать источником. Не выдумывайте языковые данные; если не можете проверить перевод, пропустите шаг.',
            'text',
            lambda b, a: (
                len(a['answers']) == len(b['answers']) + 1
                and any(
                    row['action'] == 'correct'
                    for pair, row in a['answers'].items()
                    if pair not in b['answers']
                )
            ),
        ),
        Step(
            'input/invalid',
            'В обычном состоянии отправьте ??? — бот должен объяснить допустимые действия.',
            'text',
            lambda b, a: field(a, 'state') == 'idle' and unchanged(b, a),
        ),
        Step(
            'profile/me',
            'Отправьте /me, сравните очки и статистику с ответами.',
            '/me',
            lambda b, a: unchanged(b, a),
        ),
        Step('rating/top', 'Отправьте /top.', '/top', lambda b, a: unchanged(b, a)),
        *[
            Step(
                'rating/' + period,
                'Нажмите период рейтинга: ' + period,
                'top:' + period,
                lambda b, a: unchanged(b, a),
            )
            for period in ('week', 'month', 'year', 'day')
        ],
        Step('privacy', 'Отправьте /privacy.', '/privacy', lambda b, a: unchanged(b, a)),
        Step('help', 'Отправьте /help.', '/help', lambda b, a: unchanged(b, a)),
    ]


class Observer:
    def __init__(self, db, values, bot_id, probe_path, report, timeout):
        self.db, self.values, self.bot_id, self.path = db, values, bot_id, probe_path
        self.report, self.timeout = report, timeout

    async def step(self, step):
        before = await asyncio.to_thread(self.db.snapshot)
        probe = read_probe(self.path, self.values, self.bot_id)
        session = probe['session']
        self.report.progress(step.name, 'ready')
        print('\n' + step.instruction, flush=True)
        answer = await asyncio.to_thread(
            timed_input, 'Enter = начать ожидание; skip = пропустить: ', self.timeout
        )
        if answer == 'skip':
            self.report.add(step.name, 'SKIP', 'MANUAL REQUIRED; действие не подтверждено')
            return step.name in ('task/duplicate', 'restart/persistence')
        started = time.time()
        self.report.progress(step.name, 'waiting')
        print('Выполните действие в Telegram сейчас; проверяем БД и доставку ответа…', flush=True)
        deadline = time.monotonic() + self.timeout
        target = next(reversed(before['answers']), None) if step.name == 'task/duplicate' else None
        while time.monotonic() < deadline:
            try:
                probe = read_probe(self.path, self.values, self.bot_id)
            except (OSError, ValueError):
                await asyncio.sleep(1)
                continue  # A manual restart may temporarily remove the heartbeat.
            after = await asyncio.to_thread(self.db.snapshot)
            if (
                step.name != 'delete/profile'
                and before['user']
                and (not after['user'] or before['user']['id'] != after['user']['id'])
            ):
                self.report.add(
                    step.name,
                    'FAIL',
                    'Профиль удалён или заменён вне текущего шага; последовательность остановлена',
                )
                return False
            restart_ok = step.name != 'restart/persistence' or probe['session'] != session
            if (
                restart_ok
                and witnessed(probe, started, step.action, step.method, target)
                and step.check(before, after)
            ):
                print(
                    f'БД: state {field(before, "state")} → {field(after, "state")}; очки {field(before, "points")} → {field(after, "points")}; ответов {len(before["answers"])} → {len(after["answers"])}',
                    flush=True,
                )
                self.report.progress(step.name, 'confirm')
                confirmation = await asyncio.to_thread(
                    timed_input,
                    'Видите ожидаемый ответ в Telegram? yes / no / skip: ',
                    self.timeout,
                )
                status = (
                    'PASS' if confirmation == 'yes' else 'FAIL' if confirmation == 'no' else 'SKIP'
                )
                self.report.add(
                    step.name,
                    status,
                    'БД + входящий update + успешный Bot API ответ + проверка человеком'
                    if status == 'PASS'
                    else 'Ответ в клиенте не подтверждён',
                )
                return status == 'PASS'
            await asyncio.sleep(1)
        self.report.add(
            step.name, 'SKIP', 'MANUAL REQUIRED / timeout: полного свидетельства сценария нет'
        )
        return False


async def run(args, report):
    try:
        values = settings(args.env_file)
    except FileNotFoundError:
        report.add('environment', 'SKIP', 'MANUAL REQUIRED: подготовьте отдельный env-файл')
        return
    except ValueError as error:
        report.add('environment', 'FAIL', str(error))  # Only controlled, secret-free messages.
        return
    report.add('environment', 'PASS', 'Выбран явный тестовый env; значения секретов не выводятся')
    from aiogram import Bot

    bot = None
    try:
        bot = Bot(values['TELEGRAM_BOT_TOKEN'])
        me = await bot.get_me(request_timeout=15)
        report.add('getMe', 'PASS', '@' + str(me.username))
        webhook = await bot.get_webhook_info(request_timeout=15)
        if webhook.url:
            report.add(
                'webhook',
                'FAIL',
                'Webhook активен; polling не запускается. Изменяйте его только вручную.',
            )
            return
        report.add(
            'webhook',
            'PASS',
            f'Webhook отсутствует; pending updates: {webhook.pending_update_count}; ничего не удалено',
        )
        db = Database(values)
        snapshot = await asyncio.to_thread(db.snapshot)
        report.add(
            'database',
            'PASS',
            'Реальный REST/SQL доступен; наблюдение ограничено тестовым аккаунтом',
        )
        probe_path = args.probe_file or Path(
            values.get('LIVE_TELEGRAM_PROBE_FILE', ROOT / '.live-telegram/probe.json')
        )
        try:
            read_probe(probe_path, values, me.id)
        except (OSError, ValueError):
            report.add(
                'polling',
                'SKIP',
                'MANUAL REQUIRED: нет свежего probe единственного тестового polling-процесса',
            )
            return
        report.add(
            'polling/process',
            'PASS',
            'Свежий процесс совпадает по боту, тестовому аккаунту и API; доставка проверяется отдельными шагами',
        )
        if not args.interactive:
            report.add(
                'user scenarios',
                'SKIP',
                'MANUAL REQUIRED: запустите --interactive; getMe не является live E2E',
            )
            return
        observer = Observer(db, values, me.id, probe_path, report, args.timeout)
        plan = registration_plan(snapshot['user'], args.role)
        if plan:
            if snapshot['user'] and field(snapshot, 'nickname'):
                report.add(
                    'earlier registration phases',
                    'SKIP',
                    'Продолжается существующая регистрация; прежние действия не засчитываются заново',
                )
            for step in plan:
                code = values.get('LIVE_TELEGRAM_JOIN_CODE', '')
                if (
                    step.name == 'registration/class'
                    and (field(snapshot, 'role') or args.role) == 'student'
                    and re.fullmatch(r'[A-HJ-NP-Z2-9]{6,8}', code)
                ):
                    step.instruction += ' Код только тестового класса: ' + code
                if not await observer.step(step):
                    report.add(
                        'remaining scenarios',
                        'SKIP',
                        'MANUAL REQUIRED: продолжение остановлено после неполного шага',
                    )
                    return
        else:
            report.add(
                'fresh registration',
                'SKIP',
                'Профиль уже существует; автоматического удаления/сброса нет',
            )
        if args.suite == 'registration':
            report.add('other suites', 'SKIP', 'Остальные сценарии требуют отдельного запуска')
            return
        steps = task_steps()
        if args.suite == 'profile':
            steps = [
                step
                for step in steps
                if step.name.startswith(('profile/', 'rating/')) or step.name in ('privacy', 'help')
            ]
        for step in steps:
            if not await observer.step(step):
                report.add(
                    'remaining scenarios',
                    'SKIP',
                    'MANUAL REQUIRED: продолжение остановлено после неполного шага; при необходимости отправьте /cancel',
                )
                return
        role = field(await asyncio.to_thread(db.snapshot), 'role')
        await observer.step(
            Step(
                'report/' + str(role),
                'Отправьте /report и проверьте доступ по своей роли.',
                '/report',
                lambda b, a: unchanged(b, a),
                'sendDocument' if role == 'teacher' else 'sendMessage',
            )
        )
        report.add(
            'report/other role',
            'SKIP',
            'Нужен второй специальный аккаунт с другой ролью; отдельный запуск',
        )
        if args.allow_delete:
            confirm = await asyncio.to_thread(
                timed_input,
                'Только тестовый профиль: введите DELETE TEST PROFILE для проверки удаления: ',
                args.timeout,
            )
            if confirm == 'delete test profile':
                await observer.step(
                    Step(
                        'delete/profile',
                        'Отправьте /delete_me и явно подтвердите «Да, удалить» в Telegram.',
                        'delete:yes',
                        lambda b, a: a['user'] is None and a['deleted'],
                    )
                )
            else:
                report.add('delete/profile', 'SKIP', 'Удаление не подтверждено')
        else:
            report.add(
                'delete/profile',
                'SKIP',
                'Удаление выключено; нужны --allow-delete и отдельное явное подтверждение',
            )
    except Exception as error:
        report.add(
            'runtime',
            'FAIL',
            type(error).__name__ + ': проверьте доступ, сеть и тестовое окружение; секреты скрыты',
        )
    finally:
        if bot:
            await bot.session.close()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--env-file', type=Path, required=True)
    parser.add_argument('--probe-file', type=Path)
    parser.add_argument('--interactive', action='store_true')
    parser.add_argument('--allow-delete', action='store_true')
    parser.add_argument('--role', choices=('student', 'teacher'), default='student')
    parser.add_argument(
        '--suite', choices=('all', 'registration', 'tasks', 'profile'), default='all'
    )
    parser.add_argument('--timeout', type=int, default=120)
    parser.add_argument('--report', type=Path, default=ROOT / '.live-telegram/report.json')
    args = parser.parse_args(argv)
    if not 5 <= args.timeout <= 600:
        parser.error('--timeout must be between 5 and 600 seconds')
    for logger in ('httpx', 'httpcore', 'aiogram', 'postgrest'):
        logging.getLogger(logger).setLevel(logging.CRITICAL)
    report = Report(args.report)
    try:
        asyncio.run(run(args, report))
    except KeyboardInterrupt:
        report.add(
            'interrupted', 'SKIP', 'MANUAL REQUIRED: безопасно прервано; polling и БД не изменены'
        )
    return report.finish(args.report)


if __name__ == '__main__':
    raise SystemExit(main())
