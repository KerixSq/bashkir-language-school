from html import escape

WELCOME = 'Привет! Выбери роль.'
NICKNAME_PROMPT = (
    'Придумай никнейм для рейтинга. Не используй фамилию или контакты. '
    'Длина — 3–20 символов: буквы, цифры, пробел, дефис или подчёркивание.'
)
INVALID_NICKNAME = 'Никнейм не подходит. Введи 3–20 символов без ссылок и @.'
CHOOSE_PAIR = 'Выбери языковую пару.'
NO_AVAILABLE_PAIRS = 'Пока нет загруженных переводов. Попроси организатора добавить материалы.'
STUDENT_CODE = 'Введи код класса из 6–8 символов. Его даст преподаватель.'
TEACHER_CODE = 'Введи секретный код преподавателя, который даст организатор.'
UNKNOWN_CODE = 'Код не найден. Проверь символы и попробуй ещё раз.'
UNKNOWN_PAIR = 'Такой языковой пары нет.'
REGISTRATION_REQUIRED = 'Сначала закончи регистрацию через /start.'
START_FIRST = 'Сначала введи /start.'
CORRECTION_REQUIRED = 'Пришли исправленный перевод или введи /cancel.'
CORRECTION_PROMPT = 'Пришли свой вариант перевода (1–500 символов). Для отмены: /cancel.'
CORRECTION_EMPTY = 'Нужен текст исправления длиной 1–500 символов.'
ROLE_BUTTONS = 'Выбери роль кнопками после команды /start.'
NO_TASKS = 'Ты проверил все доступные переводы. Новые задания появятся после импорта.'
TASK_STALE = 'Это задание уже неактуально. Введи /task.'
TASK_SKIPPED = 'Пропущено. По /task сначала предложим другую фразу, если она есть.'
TASK_DUPLICATE = 'Этот ответ уже учтён. Следующее задание: /task.'
CANCELLED = 'Действие отменено. Введи /task или /start.'
NO_REPORT_ACCESS = 'Отчёт доступен преподавателю, подтвердившему доступ к классу.'
NO_CLASS = 'Класс не найден.'
NO_RATING = 'Пока нет участников. Первый ответ появится после /task.'
UNKNOWN_MESSAGE = 'Чтобы получить задание, введи /task. Все команды: /help.'
BAD_ACTION = 'Неизвестная кнопка. Введи /task.'
DATABASE_ERROR = 'Не получилось выполнить действие. Попробуй ещё раз позже.'
KNOWN_ERRORS = {
    'Задание устарело': TASK_STALE,
    'Исправление': CORRECTION_EMPTY,
    'Сначала': CORRECTION_REQUIRED,
    'Завершите регистрацию': REGISTRATION_REQUIRED,
}
HELP = (
    '<b>Башкирская языковая школа</b>\n'
    '/start — регистрация\n'
    '/task — проверить перевод\n'
    '/pair — выбрать другую языковую пару\n'
    '/join — вступить в класс, сохранив прогресс\n'
    '/remind on или /remind off — добровольные напоминания\n'
    '/cancel — отменить действие\n'
    '/top — рейтинг\n'
    '/me — мой профиль\n'
    '/report — отчёт класса (преподавателю)\n'
    '/newclass — создать класс по приглашению\n'
    '/privacy — кто видит данные\n'
    '/delete_me — убрать личные данные\n'
    '/help — справка\n\n'
    'Сравнивай перевод с текстом на башкирском, отмечай ошибки и набирай очки.'
)


def returned(nickname: str) -> str:
    return f'С возвращением, <b>{escape(nickname)}</b>! Готов продолжить? Нажми кнопку ниже. Сменить язык: /pair.'


def registered(nickname: str) -> str:
    return f'Готово, <b>{escape(nickname)}</b>! Нажми кнопку ниже, чтобы получить первое задание.'


def task(
    text_ba: str,
    translation: str,
    today: int,
    goal: int,
    source: str | None = None,
    time_start=None,
    time_end=None,
) -> str:
    extra = '\nЭто дополнительное задание.' if today >= goal else ''
    return (
        '<b>Текст на башкирском</b>\n'
        f'{escape(text_ba)}\n\n'
        '<b>Предложенный перевод</b>\n'
        f'{escape(translation)}\n\n'
        'Иногда в переводе есть ошибка.\n'
        'Буквы ә, ө, ү, ҙ, ҡ, ң, ғ, һ, ҫ можно скопировать из задания.\n'
        f'Сегодня: {today} из {goal}.{extra}'
        + (
            f'\nИсточник: {escape(source)} · время {time_start}–{time_end} с.'
            if source and time_start is not None and time_end is not None
            else ''
        )
    )


def result(data: dict) -> str:
    if data.get('too_fast'):
        return TOO_FAST_RETRY.format(seconds=data.get('retry_seconds', 2))
    if data.get('duplicate'):
        return TASK_DUPLICATE
    status = {
        'confirmed': 'Перевод подтверждён.',
        'expert_review': 'Нужно мнение эксперта.',
        'collecting': 'Продолжаем собирать ответы.',
    }.get(data.get('status'), '')
    detail = ''
    if data.get('correct_translation'):
        detail = (
            'В этом переводе была ошибка. Верный вариант: '
            f'<b>{escape(data["correct_translation"])}</b>\n'
        )
    elif data.get('caught_planted_error'):
        detail = 'Ты нашёл ошибку. Отличная работа!\n'
    goal = int(data.get('daily_goal') or 5)
    today = int(data.get('today_answers') or 0)
    if data.get('goal_just_reached'):
        progress = f'Цель дня выполнена: {today} из {goal}! Серия: {data.get("goal_streak", 1)} дн.'
    else:
        progress = f'Сегодня: {today} из {goal}.'
    return (
        f'{detail}{status}\n'
        f'Очки за ответ: +{data["points_awarded"]}. '
        f'Всего: {data["points"]} · уровень {data["level"]}.\n'
        f'{progress}\nНажми «Следующее задание» или введи /task.'
    )


def profile(user: dict, stats: dict, badges: list[str], daily_goal: int) -> str:
    return (
        f'<b>{escape(user["nickname"])}</b>\n'
        f'Очки: {user["points"]} · уровень: {user["level"]}\n'
        f'Сегодня: {stats.get("day_answers", 0)} из {daily_goal}\n'
        f'Серия: {stats.get("goal_streak", 0)} дн.\n'
        f'Ответов: {stats.get("total_answers", 0)}\n'
        f'Исправлений: {stats.get("corrections", 0)}\n'
        f'Ошибочных подтверждений: {stats.get("errors", 0)}\n'
        f'Словарный запас: {stats.get("vocabulary", 0)} слов\n'
        f'Бейджи: {escape(", ".join(badges) if badges else "пока нет")}'
    )


def leaderboard(
    rows: list[dict], period: str = 'day', position: tuple[int, int, int, int] | None = None
) -> str:
    labels = {'day': 'день', 'week': 'неделю', 'month': 'месяц', 'year': 'год'}
    field = period + '_answers'
    lines = [f'<b>Самые активные за {labels[period]}</b>']
    for index, row in enumerate(rows, 1):
        lines.append(f'{index}. {escape(row["name"])} — {row.get(field, 0)} ответов')
    if position:
        lines.append(f'\nТвой класс: {position[0]} из {position[1]}.')
        lines.append(f'Ты в классе: {position[2]} из {position[3]}.')
    return '\n'.join(lines)


def report(data: dict) -> str:
    top = (
        '\n'.join(
            f'{escape(row["name"])} — {row["points"]} очков'
            for row in data.get('top_students', [])[:5]
        )
        or 'Пока нет ответов.'
    )
    return (
        f'<b>{escape(data["school"])} · {escape(data["class"])}</b>\n'
        f'Учеников: {data["students_count"]}\n'
        f'Ответов: {data["answers_count"]}\n'
        f'Ошибочных подтверждений: {data["error_rate"]}%\n\n'
        f'<b>Топ учеников</b>\n{top}'
    )


TOO_FAST_RETRY = (
    'Ответ пока слишком быстрый. Вернись к заданию через {seconds} с. Кнопка останется активной.'
)
PRIVACY = (
    'В рейтингах виден только твой никнейм. Мы храним Telegram ID для связи с ботом, '
    'ответы и статистику на сервере. Код класса не открывает отчёт. '
    'Команда /delete_me убирает связь ответов с твоим Telegram. '
    'Сами обезличенные ответы остаются для качества переводов.'
)
DELETE_CONFIRM = (
    'Убрать твои личные данные? Никнейм и связь с Telegram исчезнут, '
    'но анонимные ответы останутся. Отменить это действие нельзя.'
)
DELETE_CANCELLED = 'Удаление отменено.'
DELETED = 'Данные профиля обезличены. Если захочешь вернуться, введи /start.'
NEWCLASS_USAGE = 'Формат: /newclass КОД_ПРИГЛАШЕНИЯ | Название класса'
CSV_COLUMNS = ['Школа', 'Класс', 'Учеников', 'Ответов', 'Ошибок (%)']
CSV_STUDENTS = ['Ученик', 'Очки', 'Уровень', 'Ответы']
CSV_DAYS = ['Дата (Уфа, UTC+5)', 'Ответов']


def new_class(data: dict) -> str:
    return (
        f'Класс создан. Код ученика: <code>{escape(data["join_code"])}</code>\n'
        f'Код преподавателя: <code>{escape(data["teacher_code"])}</code>\n'
        'Не отправляй секретный код в общий чат.'
    )


CSV_PROGRESS = ['Никнейм', 'Ответов сегодня', 'Цель выполнена']
CSV_MISTAKES = ['Башкирский текст', 'Языковая пара', 'Ошибочных подтверждений']
YES = 'да'
NO = 'нет'
