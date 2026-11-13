"""Демо-школы и участники; тексты и ответы — только по отдельному флагу."""

import argparse
import random
import secrets
from datetime import datetime, timedelta, timezone

from common import client
from pure import new_join_code

# Собственные учебные примеры. Перед реальным использованием проверить носителем.
EXAMPLES = [
    (
        'Бөгөн беҙ мәктәптә яңы һүҙҙәр өйрәнәбеҙ.',
        'Сегодня мы учим новые слова в школе.',
        'Today we learn new words at school.',
        'Бүгін біз мектепте жаңа сөздер үйренеміз.',
    ),
    (
        'Мин башҡорт телендә һөйләшергә тырышам.',
        'Я стараюсь говорить на башкирском языке.',
        'I try to speak Bashkir.',
        'Мен башқұрт тілінде сөйлеуге тырысамын.',
    ),
    (
        'Уҡытыусы беҙгә ҡыҙыҡлы китап күрһәтте.',
        'Учитель показал нам интересную книгу.',
        'The teacher showed us an interesting book.',
        'Мұғалім бізге қызықты кітап көрсетті.',
    ),
    (
        'Беҙ дәрестән һуң китапханаға барабыҙ.',
        'После урока мы идём в библиотеку.',
        'We go to the library after class.',
        'Біз сабақтан кейін кітапханаға барамыз.',
    ),
    (
        'Минең дуҫым башҡортса яҡшы уҡый.',
        'Мой друг хорошо читает по-башкирски.',
        'My friend reads Bashkir well.',
        'Менің досым башқұртша жақсы оқиды.',
    ),
    (
        'Иртәгә беҙ бергәләп музейға барасаҡбыҙ.',
        'Завтра мы вместе пойдём в музей.',
        'Tomorrow we will go to the museum together.',
        'Ертең біз бірге мұражайға барамыз.',
    ),
    (
        'Был һүҙҙең мәғәнәһен аңлатып бирегеҙ.',
        'Объясните значение этого слова.',
        'Please explain the meaning of this word.',
        'Осы сөздің мағынасын түсіндіріңіз.',
    ),
    (
        'Өләсәйем миңә матур әкиәт һөйләне.',
        'Бабушка рассказала мне красивую сказку.',
        'My grandmother told me a lovely fairy tale.',
        'Әжем маған әдемі ертегі айтып берді.',
    ),
    (
        'Тыуған телде һаҡлау бик мөһим эш.',
        'Сохранять родной язык очень важно.',
        "Preserving one's native language is very important.",
        'Ана тілін сақтау өте маңызды.',
    ),
    (
        'Беҙ яңы йырҙың һүҙҙәрен өйрәндек.',
        'Мы выучили слова новой песни.',
        'We learned the words of a new song.',
        'Біз жаңа әннің сөздерін үйрендік.',
    ),
    (
        'Йәй көнө ауылда ҡоштар күп һайрай.',
        'Летом в деревне много поют птицы.',
        'In summer many birds sing in the village.',
        'Жазда ауылда құстар көп сайрайды.',
    ),
    (
        'Мин иртәнсәк таҙа һыу эсергә яратам.',
        'Я люблю пить чистую воду утром.',
        'I like drinking clean water in the morning.',
        'Мен таңертең таза су ішкенді ұнатамын.',
    ),
    (
        'Беҙҙең мәктәптә яңы спорт залы асылды.',
        'В нашей школе открылся новый спортзал.',
        'A new gym opened at our school.',
        'Біздің мектепте жаңа спорт залы ашылды.',
    ),
    (
        'Атайым ял көнө тәмле аш бешерә.',
        'Папа готовит вкусный суп в выходной.',
        'Dad makes tasty soup on his day off.',
        'Әкем демалыс күні дәмді сорпа пісіреді.',
    ),
    (
        'Балалар дәрестә һорауҙарға яуап бирә.',
        'Дети отвечают на вопросы на уроке.',
        'The children answer questions in class.',
        'Балалар сабақта сұрақтарға жауап береді.',
    ),
    (
        'Кисә мин бик ҡыҙыҡлы фильм ҡараным.',
        'Вчера я посмотрел очень интересный фильм.',
        'Yesterday I watched a very interesting film.',
        'Кеше мен өте қызықты фильм көрдім.',
    ),
    (
        'Ҡыш көнө беҙ йылы кейем кейәбеҙ.',
        'Зимой мы надеваем тёплую одежду.',
        'In winter we wear warm clothes.',
        'Қыста біз жылы киім киеміз.',
    ),
    (
        'Минең ҡустым мәктәпкә иртә бара.',
        'Мой младший брат рано идёт в школу.',
        'My younger brother goes to school early.',
        'Менің інім мектепке ерте барады.',
    ),
    (
        'Был дәрестә яңы ҡағиҙәне өйрәнәбеҙ.',
        'На этом уроке мы изучаем новое правило.',
        'In this lesson we study a new rule.',
        'Бұл сабақта біз жаңа ережені үйренеміз.',
    ),
    (
        'Китап уҡыу һүҙ байлығын арттыра.',
        'Чтение книг увеличивает словарный запас.',
        'Reading books expands vocabulary.',
        'Кітап оқу сөздік қорды арттырады.',
    ),
    (
        'Бөгөн һауа торошо бик матур һәм йылы.',
        'Сегодня погода очень хорошая и тёплая.',
        'The weather is very nice and warm today.',
        'Бүгін ауа райы өте жақсы әрі жылы.',
    ),
    (
        'Әсәйем менән баҙарҙан алма алдыҡ.',
        'Мы с мамой купили яблоки на рынке.',
        'My mother and I bought apples at the market.',
        'Анам екеуміз базардан алма сатып алдық.',
    ),
    (
        'Һәр уҡыусы үҙ фекерен әйтә ала.',
        'Каждый ученик может высказать своё мнение.',
        'Every student can express an opinion.',
        'Әр оқушы өз пікірін айта алады.',
    ),
    (
        'Тәржемәне иғтибар менән тикшерегеҙ.',
        'Внимательно проверьте перевод.',
        'Check the translation carefully.',
        'Аударманы мұқият тексеріңіз.',
    ),
    (
        'Берҙәм эшләгәндә һөҙөмтә яҡшыраҡ була.',
        'Когда работаем вместе, результат лучше.',
        'Working together gives better results.',
        'Бірге жұмыс істесек, нәтиже жақсырақ болады.',
    ),
]
SUFFIX = (
    'Беҙ бергәләп өйрәнәбеҙ.',
    'Мы учимся вместе.',
    'We learn together.',
    'Біз бірге үйренеміз.',
)
# Правдоподобные подставные ошибки: меняется один смысловой признак.
BASE_WRONG = {
    5: (
        'Мой друг плохо читает по-башкирски.',
        'My friend reads Bashkir poorly.',
        'Менің досым башқұртша нашар оқиды.',
    ),
    10: (
        'Мы забыли слова новой песни.',
        'We forgot the words of a new song.',
        'Біз жаңа әннің сөздерін ұмыттық.',
    ),
    15: (
        'Дети не отвечают на вопросы на уроке.',
        'The children do not answer questions in class.',
        'Балалар сабақта сұрақтарға жауап бермейді.',
    ),
    20: (
        'Сегодня погода очень холодная.',
        'The weather is very cold today.',
        'Бүгін ауа райы өте суық.',
    ),
    25: (
        'Когда работаем вместе, результат хуже.',
        'Working together gives worse results.',
        'Бірге жұмыс істесек, нәтиже нашар болады.',
    ),
}
PAIRS = ('ba-ru', 'ba-en', 'ba-kk')
DEMO_TITLE = 'Демо: учебные фразы (не проверены носителем)'
LEGACY_TITLE = 'Демо: учебные фразы (авторский набор)'


def unique_join_code(db):
    while True:
        code = new_join_code()
        if not one(db, 'classes', join_code=code):
            return code


def remove_demo(db):
    demo_users = (
        db.table('users')
        .select('id')
        .lt('telegram_id', 0)
        .gte('telegram_id', -900000014)
        .execute()
        .data
        or []
    )
    schools = (
        db.table('schools')
        .select('id')
        .in_('name', ['Демо-школа №1', 'Демо-школа №2', 'Демо-школа №3'])
        .execute()
        .data
        or []
    )
    school_ids = [row['id'] for row in schools]
    rooms = (
        (db.table('classes').select('id').in_('school_id', school_ids).execute().data or [])
        if school_ids
        else []
    )
    room_ids = [row['id'] for row in rooms]
    demo_sources = (
        db.table('sources').select('id').in_('title', [DEMO_TITLE, LEGACY_TITLE]).execute().data
        or []
    )
    source_ids = [row['id'] for row in demo_sources]
    fragments = (
        (db.table('fragments').select('id').in_('source_id', source_ids).execute().data or [])
        if source_ids
        else []
    )
    fragment_ids = [row['id'] for row in fragments]
    pairs = (
        (
            db.table('fragment_pairs').select('id').in_('fragment_id', fragment_ids).execute().data
            or []
        )
        if fragment_ids
        else []
    )
    pair_ids = [row['id'] for row in pairs]
    user_ids = [row['id'] for row in demo_users]

    if room_ids:
        linked = db.table('users').select('id').in_('class_id', room_ids).execute().data or []
        if any(row['id'] not in user_ids for row in linked):
            raise SystemExit('Сброс остановлен: в демо-классах есть реальные участники.')
    if pair_ids:
        linked = (
            db.table('answers').select('user_id').in_('fragment_pair_id', pair_ids).execute().data
            or []
        )
        if any(row['user_id'] not in user_ids for row in linked):
            raise SystemExit('Сброс остановлен: реальные участники отвечали на демо-тексты.')
        pending = (
            db.table('users').select('id').in_('current_fragment_pair_id', pair_ids).execute().data
            or []
        )
        if any(row['id'] not in user_ids for row in pending):
            raise SystemExit('Сброс остановлен: у реального участника открыто демо-задание.')

    if pair_ids:
        external = (
            db.table('external_answers')
            .select('id')
            .in_('fragment_pair_id', pair_ids)
            .limit(1)
            .execute()
            .data
            or []
        )
        if external:
            raise SystemExit('Сброс отменён: внешние ответы ссылаются на демо-данные.')
    if user_ids:
        db.table('user_badges').delete().in_('user_id', user_ids).execute()
        db.table('answers').delete().in_('user_id', user_ids).execute()
        db.table('users').delete().in_('id', user_ids).execute()
    if pair_ids:
        for table in ('expert_decisions', 'status_history'):
            db.table(table).delete().in_('fragment_pair_id', pair_ids).execute()
        db.table('fragment_pairs').delete().in_('id', pair_ids).execute()
    if fragment_ids:
        db.table('fragments').delete().in_('id', fragment_ids).execute()
    if source_ids:
        db.table('import_batches').delete().in_('source_id', source_ids).execute()
        db.table('sources').delete().in_('id', source_ids).execute()
    if room_ids:
        db.table('classes').delete().in_('id', room_ids).execute()
    if school_ids:
        db.table('schools').delete().in_('id', school_ids).execute()
    print('Старые демонстрационные данные очищены.')


def one(db, table, **filters):
    q = db.table(table).select('*')
    for key, value in filters.items():
        q = q.eq(key, value)
    rows = q.limit(1).execute().data
    return rows[0] if rows else None


def main():
    parser = argparse.ArgumentParser(description='Создание демо-данных')
    parser.add_argument(
        '--reset-demo',
        action='store_true',
        help='Удалить только демо-данные, затем создать их заново',
    )
    parser.add_argument(
        '--with-demo-texts', action='store_true', help='Добавить непроверенные демо-фразы и ответы'
    )
    args = parser.parse_args()
    print('ВНИМАНИЕ: тексты демо не проверены носителем языка.')
    random.seed(42)
    db = client()
    if args.reset_demo:
        remove_demo(db)
    classes = []
    for school_number in range(1, 4):
        title = f'Демо-школа №{school_number}'
        school = one(db, 'schools', name=title)
        if not school:
            school = db.table('schools').insert({'name': title}).execute().data[0]
        for class_number in (1, 2):
            name = f'{school_number}{"А" if class_number == 1 else "Б"}'
            room = one(db, 'classes', school_id=school['id'], name=name)
            if not room:
                room = (
                    db.table('classes')
                    .insert(
                        {
                            'school_id': school['id'],
                            'name': name,
                            'join_code': unique_join_code(db),
                            'teacher_code': secrets.token_urlsafe(24),
                        }
                    )
                    .execute()
                    .data[0]
                )
            classes.append(room)

    if args.with_demo_texts:
        title = DEMO_TITLE
        src = one(db, 'sources', title=DEMO_TITLE) or one(db, 'sources', title=LEGACY_TITLE)
        if not src:
            src = (
                db.table('sources')
                .insert({'title': title, 'kind': 'text', 'license': 'demo', 'url': None})
                .execute()
                .data[0]
            )
        else:
            db.table('sources').update({'title': title, 'license': 'demo'}).eq(
                'id', src['id']
            ).execute()
        generated = EXAMPLES + [tuple(a + ' ' + b for a, b in zip(row, SUFFIX)) for row in EXAMPLES]
        for index, text_tuple in enumerate(generated, 1):
            phrase = one(db, 'fragments', source_id=src['id'], position=index)
            if not phrase:
                phrase = (
                    db.table('fragments')
                    .insert(
                        {
                            'source_id': src['id'],
                            'text_ba': text_tuple[0],
                            'chapter': 'Демо',
                            'position': index,
                        }
                    )
                    .execute()
                    .data[0]
                )
            for pair_index, pair_code in enumerate(PAIRS, 1):
                existing = one(db, 'fragment_pairs', fragment_id=phrase['id'], lang_pair=pair_code)
                if existing:
                    continue
                # Для каждого пятого фрагмента показываем содержательно неверный перевод.
                wrong = None
                if index % 5 == 0:
                    base_index = (index - 1) % len(EXAMPLES) + 1
                    wrong = BASE_WRONG[base_index][pair_index - 1]
                    if index > len(EXAMPLES):
                        wrong += ' ' + SUFFIX[pair_index]
                db.table('fragment_pairs').insert(
                    {
                        'fragment_id': phrase['id'],
                        'lang_pair': pair_code,
                        'auto_translation': text_tuple[pair_index],
                        'bad_translation': wrong,
                    }
                ).execute()

    users = []
    for index in range(15):
        identifier = -900000000 - index  # Не пересекается с реальными Telegram ID.
        user = one(db, 'users', telegram_id=identifier)
        payload = {
            'username': f'demo_{index + 1}',
            'display_name': None,
            'nickname': f'Демо {index + 1}',
            'role': 'teacher' if index in (0, 5, 10) else 'student',
            'class_id': classes[index % len(classes)]['id'],
            'lang_pair': PAIRS[index % 3],
            'state': 'idle',
        }
        if not user:
            user = (
                db.table('users').insert({'telegram_id': identifier, **payload}).execute().data[0]
            )
        else:
            db.table('users').update(payload).eq('id', user['id']).execute()
            user = one(db, 'users', id=user['id'])
        users.append(user)

    if args.with_demo_texts:
        # Можно возобновить генерацию, если предыдущий запуск оборвался.
        total = 0
        for index, user in enumerate(users):
            db.table('users').update(
                {'state': 'idle', 'current_fragment_pair_id': None, 'current_shown_variant': None}
            ).eq('id', user['id']).execute()
            current = db.table('answers').select('id').eq('user_id', user['id']).execute().data
            # При повторном запуске добавляем только недостающие ответы.
            for j in range(max(0, 24 - len(current))):
                # Never send synthetic participants through the production queue:
                # it also contains real corpus fragments awaiting consensus.
                answered = (
                    db.table('answers')
                    .select('fragment_pair_id')
                    .eq('user_id', user['id'])
                    .execute()
                    .data
                    or []
                )
                done = {row['fragment_pair_id'] for row in answered}
                candidates = (
                    db.table('fragment_pairs')
                    .select('id,auto_translation,bad_translation,fragments!inner(source_id)')
                    .eq('fragments.source_id', src['id'])
                    .eq('lang_pair', user['lang_pair'])
                    .execute()
                    .data
                    or []
                )
                task = next((row for row in candidates if row['id'] not in done), None)
                if task is None:
                    break
                pair = task['id']
                variant = 'bad' if task['bad_translation'] and random.random() < 0.2 else 'auto'
                db.table('users').update(
                    {
                        'current_fragment_pair_id': pair,
                        'current_shown_variant': variant,
                        'state': 'idle',
                    }
                ).eq('id', user['id']).execute()
                correct = (variant == 'bad' and random.random() < 0.8) or (
                    variant == 'auto' and random.random() < 0.12
                )
                if correct:
                    db.table('users').update({'state': 'awaiting_correction'}).eq(
                        'id', user['id']
                    ).execute()
                    if variant == 'bad':
                        # Для плохого варианта исправлением служит правильный перевод.
                        good = one(db, 'fragment_pairs', id=pair)['auto_translation']
                    else:
                        good = task['auto_translation'] + ' (другой вариант)'
                    action, text = 'correct', good
                else:
                    action, text = 'confirm', None
                try:
                    past = (datetime.now(timezone.utc) - timedelta(seconds=15)).isoformat()
                    db.table('users').update({'current_shown_at': past, 'last_answer_at': past}).eq(
                        'id', user['id']
                    ).execute()
                    db.rpc(
                        'submit_answer',
                        {
                            'p_user_id': user['id'],
                            'p_fragment_pair_id': pair,
                            'p_action': action,
                            'p_text': text,
                        },
                    ).execute()
                    total += 1
                except Exception as exc:
                    print(f'Не удалось создать демо-ответ: {exc}')
                    db.table('users').update(
                        {
                            'state': 'idle',
                            'current_fragment_pair_id': None,
                            'current_shown_variant': None,
                        }
                    ).eq('id', user['id']).execute()
            print(f'Участник {index + 1}/15 — готов')

        # Гарантированно создаём один спорный фрагмент для expert_review.
        phrase = one(db, 'fragments', source_id=src['id'], position=51)
        if not phrase:
            phrase = (
                db.table('fragments')
                .insert(
                    {
                        'source_id': src['id'],
                        'chapter': 'Демо',
                        'position': 51,
                        'text_ba': 'Бөгөн беҙ төрлө яуаптарҙы сағыштырабыҙ.',
                    }
                )
                .execute()
                .data[0]
            )
        conflict = one(db, 'fragment_pairs', fragment_id=phrase['id'], lang_pair='ba-ru')
        if not conflict:
            conflict = (
                db.table('fragment_pairs')
                .insert(
                    {
                        'fragment_id': phrase['id'],
                        'lang_pair': 'ba-ru',
                        'auto_translation': 'Сегодня мы сравниваем разные ответы.',
                    }
                )
                .execute()
                .data[0]
            )
        alternatives = [
            'Сегодня мы изучаем ответы.',
            'Сейчас мы проверяем варианты.',
            'Мы собираем новые предложения.',
            'Сегодня класс обсуждает тексты.',
            'Мы работаем над правильными словами.',
        ]
        for user, correction in zip(users[::3], alternatives):
            if one(db, 'answers', user_id=user['id'], fragment_pair_id=conflict['id']):
                continue
            db.table('users').update(
                {
                    'state': 'awaiting_correction',
                    'current_fragment_pair_id': conflict['id'],
                    'current_shown_variant': 'auto',
                    'current_shown_at': (
                        datetime.now(timezone.utc) - timedelta(seconds=15)
                    ).isoformat(),
                    'last_answer_at': (
                        datetime.now(timezone.utc) - timedelta(seconds=15)
                    ).isoformat(),
                }
            ).eq('id', user['id']).execute()
            db.rpc(
                'submit_answer',
                {
                    'p_user_id': user['id'],
                    'p_fragment_pair_id': conflict['id'],
                    'p_action': 'correct',
                    'p_text': correction,
                },
            ).execute()
            total += 1
        print(f'Создано {total} демонстрационных ответов')

    else:
        print('Демо-тексты отключены. Для них нужен флаг --with-demo-texts.')

    print('\nКоды классов. join_code — ученикам, teacher_code — только преподавателям:')
    for cls in classes:
        print(f'  {cls["name"]}: join_code={cls["join_code"]}  teacher_code={cls["teacher_code"]}')
    print('ВНИМАНИЕ: тексты демо не проверены носителем языка.')


if __name__ == '__main__':
    main()
