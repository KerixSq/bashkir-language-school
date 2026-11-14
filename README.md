# Башкирская языковая школа

Образовательная платформа для практики башкирского языка и совместной проверки переводов. Короткие уроки с Акбузатом помогают изучать фразы, а независимые ответы участников пополняют базу согласованных переводов с источниками и REST-экспортом.

## Для учеников

Начинайте без класса, выбирайте языковую пару и проходите задания в браузере или Telegram. Просматривайте обратную связь, личный вклад и дневную цель. Вступить в класс позже можно через `/join`, сохранив серверный прогресс.

## Для преподавателей

Организуйте класс, отслеживайте активность и получайте отчёт с экспортом CSV. Преподавательский доступ защищён отдельным кодом; ученический код не открывает отчёт.

## Коллективная проверка переводов

Участники подтверждают перевод, предлагают исправление или пропускают фразу. Сервер проверяет повторы и согласует независимые ответы. Эксперт сравнивает спорные варианты, голоса и показатель текстового сходства, затем принимает решение. Подтверждённые результаты доступны в общей библиотеке и API. Голосование не заменяет лингвистическую экспертизу.

## Игровой режим и достижения

Тренировочная карта включает уроки по пять заданий, этапы, серии и награды. Колода содержит 700 записей БГПУ на парах ba-ru/ba-kk. Тренировочные XP хранятся только в браузере и не создают серверных голосов. Экспортёр колоды: `scripts/export_learning_deck.py`. [Правила игры](docs/GAMEPLAY.md).

## Telegram-бот

Регистрация, задания, профиль, вклад, рейтинг и настройки доступны через меню. Добровольные `/remind on/off` изначально выключены. Веб- и Telegram-профили независимы; переход по ссылке их не объединяет. [Команды и настройки](docs/TELEGRAM.md).

## Архитектура

Сайт на HTML/CSS/JavaScript, aiogram-бот, PostgreSQL, PostgREST, Supabase Auth и Nginx работают через Docker Compose. Основной запуск не требует React, Node.js или внешней облачной базы. Синтезированная башкирская TTS доступна для 40 фраз; исходное WAV/MP3 импортируется отдельно с готовой разметкой. [Потоки данных и права](docs/ARCHITECTURE.md).

## Установка и запуск

Нужны Git, Python 3.11+ и Docker Desktop в режиме Linux containers/WSL2. Выполняйте из корня клонированного репозитория:

```powershell
python scripts/create_docker_env.py
docker compose --env-file .env.docker config --quiet
docker compose --env-file .env.docker up -d --build --wait
```

Откройте http://127.0.0.1:54321/web/. Публичная конфигурация создаётся автоматически; секретный ключ не попадает на сайт. На новом volume SQL инициализируется один раз. Сайт работает без токена Telegram и Tor.

Серверные задания после чистого clone нужно импортировать отдельно; `data/` не входит в Git:

```powershell
python scripts/download_phrasebooks.py
docker compose --env-file .env.docker build bot
docker compose --env-file .env.docker run --rm --no-deps bot python scripts/import_phrasebooks.py --dir data/phrasebooks --dry-run
docker compose --env-file .env.docker run --rm --no-deps bot python scripts/import_phrasebooks.py --dir data/phrasebooks --bad-share 0.2 --seed 42
```

Загрузчик проверяет закреплённую ревизию и SHA-256. Импорт повторяемый, новые пары получают collecting. Готовая браузерная колода содержит 700 записей и работает отдельно от серверной базы. Её экспортёр: `python scripts/export_learning_deck.py --dir data/phrasebooks --per-pair 350 --seed 42`.

**Существующая база:** сначала backup и подтверждение её версии, затем только недостающие миграции по [WINDOWS_SETUP](docs/WINDOWS_SETUP.md). Важны обе stage11 и последовательность до stage14. Не повторяйте schema/seed/logic поверх volume, не пересоздавайте пароли/JWT из `.env.docker`, не используйте down -v или reset.

Для Telegram введите токен только локально в `.env.docker`, остановите другие polling-процессы и выполните:

```powershell
docker compose --env-file .env.docker --profile bot up -d --build tor bot
```

Direct-режим выбирается явно, без скрытого fallback. Полные команды установки, обновления, backup, Tor/direct, healthchecks и остановки — [WINDOWS_SETUP](docs/WINDOWS_SETUP.md). Supabase CLI — [отдельный альтернативный режим](docs/LOCAL_WINDOWS.md); одновременно с Compose на 54321 его не запускают.

## API и интеграция

Публичные представления возвращают результаты без ID школьников. REST-экспорт содержит семь полей; JSON/CSV доступны на сайте. Закрытые таблицы не доступны публичному ключу. Учительские, экспертные и партнёрские операции имеют отдельные права. [Контракты и примеры](API.md).

## Тестирование

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m compileall -q bot scripts tests
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe scripts/check_contract.py
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m ruff format --check .
.\.venv\Scripts\python.exe -m playwright install chromium webkit
.\.venv\Scripts\python.exe tests/browser_navigation_checks.py
.\.venv\Scripts\python.exe tests/browser_visual_checks.py
.\.venv\Scripts\python.exe tests/browser_tts_checks.py
.\.venv\Scripts\python.exe tests/docker_integration.py
```

Docker integration требует свободного 54321 и создаёт отдельный Compose-проект, не рабочую базу. PostgreSQL integration использует локальный PG_TEST_ADMIN_DSN и удаляет только свою disposable БД. Скриншоты/видео — в test-results, новые CI-артефакты хранятся 14 дней. Повторный аудит и документация не подтверждают запуск на конкретном ноутбуке — смотрите фактический SHA/CI в QA.

## Документация

| Документ | Содержание |
|---|---|
| [Руководство пользователя](docs/PRODUCT_GUIDE.md) | Начало обучения, урок, проверка, прогресс и экспорт |
| [Установка Windows](docs/WINDOWS_SETUP.md) | Запуск, миграции, резервная копия и диагностика |
| [Архитектура](docs/ARCHITECTURE.md), [спецификация](SPEC.md), [API](API.md) | Устройство и функциональные контракты |
| [Игровые правила](docs/GAMEPLAY.md) | Уроки, XP и серверный прогресс |
| [Контент и аудио](docs/CONTENT_AND_AUDIO.md) | Происхождение, лицензии, CSV, TTS и исходное аудио |
| [Telegram](docs/TELEGRAM.md), [эксперт](docs/EXPERT_REVIEW.md) | Команды, напоминания и спорные случаи |
| [Качество](docs/QA.md), [изменения](docs/RELEASE_NOTES.md) | Проверки, ограничения и состояние версии |

[Исследование учеников](docs/STUDENT_RESEARCH.md) описывает гипотезы и протокол пилота; [live Telegram](docs/TELEGRAM_LIVE_TEST.md) — изолированную ручную проверку. Искусственные Updates не называются Live E2E.

## Лицензии и источники

Тексты: [Bashkorttele / БГПУ](https://huggingface.co/datasets/bashkorttele/trilingual-parallel-phrasebooks-bgpu), [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). Правообладатель — ФГБОУ ВО «БГПУ им. М. Акмуллы»; издатель — АНО «Фонд сохранения и развития башкирского языка». Сохранены LICENSE/NOTICE, [ревизия и хеши](docs/CORPUS_PROVENANCE.json). Изменения: отбор ba-ru/ba-kk, дедупликация, частотный русский вариант, учебные подстановки. Лицензия текста не распространяется на иллюстрации печатных изданий.

## Известные ограничения

Переводы и произношение TTS не проверены носителем. Сходство написания не означает семантическую эквивалентность. Подлинный лицензированный исходный аудиокорпус не добавлен: тесты используют обозначенный технический тон. Напоминания резервируют одну попытку в день, не гарантируют доставку при сетевом сбое. Официальная интеграция с экспертной организацией и объединение аккаунтов не заявляются. Локальный API нельзя публиковать напрямую без отдельной защиты и HTTPS.
