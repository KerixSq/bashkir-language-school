# Башкирская языковая школа

Веб-платформа и Telegram-бот для практики башкирского языка и совместной проверки переводов. Короткие уроки с Акбузатом помогают заниматься регулярно, а независимые ответы участников пополняют общую базу согласованных переводов с источниками и REST-экспортом.

Сайт, aiogram-бот, PostgreSQL, PostgREST, Supabase Auth и Nginx работают на одном ноутбуке через Docker Compose. React, внешняя облачная база и Node.js для запуска не нужны. Текущая сборка собрана в `rc1-visual-polish`; стабильный релиз и тег не опубликованы. [Результаты проверок и ограничения](docs/QA.md).

## Возможности

- Тренировочная карта, уроки по пять заданий, локальные XP и достижения.
- Серверная проверка в браузере и Telegram: подтверждение, исправление, пропуск, три независимых голоса и экспертная очередь.
- Рейтинги по периодам, прогресс общей библиотеки, классы, отчёты преподавателя, JSON/CSV и REST API.
- Самостоятельная регистрация без класса, вступление позже через `/join`, добровольные `/remind on/off` (изначально выключены).
- Реальные тексты БГПУ; синтезированная башкирская TTS для 40 фраз; импорт исходного WAV/MP3 с готовыми таймкодами.

Тренировочные XP сохраняются только в браузере. Они не создают серверных голосов и не увеличивают рейтинг или библиотеку. Веб- и Telegram-профили независимы.

## Быстрый старт — Windows 11

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

## Документация

| Документ | Содержание |
|---|---|
| [SPEC](SPEC.md), [API](API.md) | Фактические функции, RPC, права и семь полей экспорта |
| [WINDOWS_SETUP](docs/WINDOWS_SETUP.md) | Установка, миграции, backup и диагностика |
| [ARCHITECTURE](docs/ARCHITECTURE.md) | Потоки данных, безопасность, модули и тестовые контуры |
| [GAMEPLAY](docs/GAMEPLAY.md) | Правила уроков, XP и серверного прогресса |
| [CONTENT_AND_AUDIO](docs/CONTENT_AND_AUDIO.md) | Корпус, лицензии, CSV, TTS, исходное аудио и 20 фраз для носителя |
| [TELEGRAM](docs/TELEGRAM.md) | Регистрация, меню, вклад и напоминания |
| [EXPERT_REVIEW](docs/EXPERT_REVIEW.md) | Сходство вариантов и защищённое решение эксперта |
| [DEMO](docs/DEMO.md) | Три минуты защиты, резервный сценарий и вопросы жюри |
| [QA](docs/QA.md), [RELEASE_NOTES](docs/RELEASE_NOTES.md) | Фактические результаты, ограничения и история |

[Исследование учеников](docs/STUDENT_RESEARCH.md) сохраняет гипотезы и протокол пилота. [Live Telegram](docs/TELEGRAM_LIVE_TEST.md) описывает изолированную ручную проверку; искусственные Updates не называются Live E2E.

## Проверки

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

## Происхождение и ограничения

Тексты: [Bashkorttele / БГПУ](https://huggingface.co/datasets/bashkorttele/trilingual-parallel-phrasebooks-bgpu), [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). Правообладатель — ФГБОУ ВО «БГПУ им. М. Акмуллы»; издатель — АНО «Фонд сохранения и развития башкирского языка». Сохранены LICENSE/NOTICE, [ревизия и хеши](docs/CORPUS_PROVENANCE.json). Изменения: отбор ba-ru/ba-kk, дедупликация, частотный русский вариант, учебные подстановки. Лицензия текста не распространяется на иллюстрации печатных изданий.

Переводы и произношение TTS не проверены носителем. Сходство написания не означает семантическую эквивалентность. Подлинный лицензированный исходный аудиокорпус не добавлен: тесты используют обозначенный технический тон. Напоминания резервируют одну попытку в день, не гарантируют доставку при сетевом сбое. Официальная интеграция с экспертной организацией и объединение аккаунтов не заявляются. Локальный API нельзя публиковать напрямую без отдельной защиты и HTTPS.
