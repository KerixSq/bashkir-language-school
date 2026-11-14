from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def build_keyboard(rows: list[list[tuple[str, str]]]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=text, callback_data=data) for text, data in row]
            for row in rows
        ]
    )


def role_keyboard() -> InlineKeyboardMarkup:
    return build_keyboard([[('Ученик', 'role:student'), ('Преподаватель', 'role:teacher')]])


def pair_keyboard(rows: list[dict]) -> InlineKeyboardMarkup:
    return build_keyboard([[(row['name'], 'pair:' + row['code'])] for row in rows])


def task_keyboard(fragment_id: str) -> InlineKeyboardMarkup:
    return build_keyboard(
        [
            [
                ('Верно', f'task:confirm:{fragment_id}'),
                ('Исправить', f'task:correct:{fragment_id}'),
            ],
            [('Пропустить', f'task:skip:{fragment_id}')],
        ]
    )


def period_keyboard() -> InlineKeyboardMarkup:
    return build_keyboard(
        [[('День', 'top:day'), ('Неделя', 'top:week'), ('Месяц', 'top:month'), ('Год', 'top:year')]]
    )


def delete_keyboard() -> InlineKeyboardMarkup:
    return build_keyboard([[('Да, удалить', 'delete:yes'), ('Отмена', 'delete:no')]])


def next_task_keyboard() -> InlineKeyboardMarkup:
    return build_keyboard([[('Следующее задание', 'flow:next'), ('Меню', 'menu:home')]])


def main_menu(role: str | None) -> InlineKeyboardMarkup:
    rows = [
        [('Задание дня', 'menu:task'), ('Мой прогресс', 'menu:progress')],
        [('Вклад в библиотеку', 'menu:contribution'), ('Рейтинг', 'menu:ratings')],
        [('Настройки', 'menu:settings'), ('Сайт и игра', 'menu:web')],
    ]
    if role == 'teacher':
        rows.append([('Мой класс', 'menu:report'), ('Отчёт', 'menu:report')])
    return build_keyboard(rows)


def study_mode() -> InlineKeyboardMarkup:
    return build_keyboard(
        [[('Учиться самостоятельно', 'study:solo')], [('Вступить в класс', 'study:class')]]
    )
