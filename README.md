# Башкирская языковая школа

Release candidate `v0.9.0-rc1`: [единая установка/обновление Windows](docs/FINAL_WINDOWS_SETUP.md), [сценарий на три минуты](docs/FINAL_DEMO.md), [резервный показ](docs/DEMO_BACKUP.md), [проверки и матрица ТЗ](docs/FINAL_RELEASE_QA.md). Ветка `release-candidate`; тег и стабильный релиз не опубликованы.

Добровольные Telegram-напоминания: `/remind on/off` и меню настроек. По умолчанию выключены; [stage14, запуск и ограничения доставки](docs/REMINDERS.md). Итоговый технический аудит — [FINAL_HACKATHON_QA.md](docs/FINAL_HACKATHON_QA.md).

Исходное WAV/MP3 с готовой разметкой: [импорт, stage13 и воспроизведение диапазона](docs/ORIGINAL_AUDIO.md). Это отдельный конвейер от TTS, без распознавания речи.

Экспертные подсказки сходства вариантов и безопасное обновление stage12: [инструкция](docs/EXPERT_SIMILARITY.md). Итог выбирает эксперт; сходство не объединяет голоса автоматически.

Telegram: самостоятельное обучение без класса, меню и личный вклад — [инструкция](docs/TELEGRAM_NAVIGATION.md). Для обновления существующей базы нужна миграция stage11 из этой инструкции. Сайт запускается без токена и без Tor; бот имеет явные proxy/direct режимы.

Браузерная проверка переводов БГПУ: анонимный вход, никнейм, задания, серверные очки, консенсус, рейтинги и REST-экспорт. Telegram — дополнительный канал. Отдельная тренировочная тропа хранит XP только в браузере: они не влияют на серверный рейтинг и Библиотеку Акбузата.

## Основной запуск: Docker Compose, Windows 11

Нужны Docker Desktop (Linux containers / WSL2), Python 3.11+ и Git. Node.js для запуска сайта не нужен. Выполняй из корня репозитория:

```powershell
python scripts/create_docker_env.py
docker compose --env-file .env.docker config --quiet
docker compose --env-file .env.docker up -d --build --wait
```

Открой http://127.0.0.1:54321/web/. Публичная конфигурация и анонимный вход включены автоматически; секретный ключ не попадает на сайт. SQL инициализируется автоматически только при первом запуске пустого volume. Не запускай schema/seed/logic повторно поверх существующих данных.

Оба Windows-скрипта по умолчанию запускают этот же Compose:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/run_local.ps1
```

## Реальный корпус после чистого git clone

`data/` исключена из Git. В репозитории есть учебная колода из 700 фраз, но серверные задания нужно импортировать отдельно. Загрузчик скачивает зафиксированную ревизию, проверяет SHA-256 всех пяти JSONL, LICENSE и NOTICE; изменённые локальные файлы не перезаписывает.

```powershell
python scripts/download_phrasebooks.py
docker compose --env-file .env.docker build bot
docker compose --env-file .env.docker run --rm --no-deps bot python scripts/import_phrasebooks.py --dir data/phrasebooks --dry-run
docker compose --env-file .env.docker run --rm --no-deps bot python scripts/import_phrasebooks.py --dir data/phrasebooks --bad-share 0.2 --seed 42
```

Импорт повторяемый; неподтверждённые переводы получают collecting. Пары: ba-ru и ba-kk. Подставной вариант — другой перевод того же файла, выбранный по длине; это эвристика, требующая проверки. Для ручной проверки используй --review-out (CSV внутри контейнера нужно скопировать на хост).

Источник: [Bashkorttele / БГПУ](https://huggingface.co/datasets/bashkorttele/trilingual-parallel-phrasebooks-bgpu). Лицензия текстов — [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). Правообладатель: ФГБОУ ВО «БГПУ им. М. Акмуллы»; издатель: АНО «Фонд сохранения и развития башкирского языка». Сохранённые LICENSE/NOTICE — web/assets/corpus/; ревизия и хеши — docs/CORPUS_PROVENANCE.json. Изменения: отбор ba-ru/ba-kk, дедупликация, частотный выбор русского варианта, учебные подстановки. Соответствия корпуса не проверены построчно; проверка сообщества не равна экспертизе. Лицензия текста не распространяется на иллюстрации печатных изданий.

Статическую колоду можно обновить командой `python scripts/export_learning_deck.py --dir data/phrasebooks --per-pair 350 --seed 42`. Правила тренировки — [docs/GAMEPLAY.md](docs/GAMEPLAY.md).

## Данные и остановка

```powershell
docker compose --env-file .env.docker --profile bot down
```

Обычный down сохраняет volume. Никогда не добавляй -v для обычной остановки. Не пересоздавай .env.docker для существующей БД: в нём сохранены её пароли и JWT secret. Backup и точный порядок обновления — [FINAL_WINDOWS_SETUP.md](docs/FINAL_WINDOWS_SETUP.md). После stage9 нужны stage10, **обе stage11** (auth_search_path и independent_students), затем stage12–14. Применяйте только необходимый суффикс после проверки состояния базы.

Telegram необязателен: добавь TELEGRAM_BOT_TOKEN в .env.docker и выполни `docker compose --env-file .env.docker --profile bot up -d --build`. Команды: /start, /task, /pair, /cancel, /me, /top, /report, /newclass, /privacy, /delete_me, /help. Токены, учительские и экспертные коды не публикуй.

## Проверки

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe scripts/check_contract.py
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m ruff format --check .
.\.venv\Scripts\python.exe scripts/doctor.py
.\.venv\Scripts\python.exe scripts/check_rls.py
.\.venv\Scripts\python.exe -m playwright install chromium
.\.venv\Scripts\python.exe tests/docker_integration.py
```

Docker integration требует свободного порта 54321: сначала останови обычный Compose. Тест создаёт уникальный проект, скачивает настоящий корпус, проверяет Auth → браузер → REST → SQL, права и сохранность после restart. В конце останавливает только свой проект, сохраняя его volume. Отдельные PostgreSQL-тесты: PG_TEST_ADMIN_DSN на локальный тестовый сервер и tests/postgres_integration.py. SQL-тест создаёт и удаляет только собственную временную БД. Полный Docker-тест автоматически выполняется GitHub Actions.

Проверки выбирают .env.docker; для явного выбора используется BASHKIR_ENV_FILE. Сетевой отказ не является успешной проверкой прав. Схема и RPC документированы в [API.md](API.md). Сценарий защиты — [docs/DEMO_3_MINUTES.md](docs/DEMO_3_MINUTES.md). Единая учётная запись сайта/Telegram и семантическое распознавание синонимов не реализованы. Башкирская TTS доступна для 40 фраз корпуса: статические WAV Silero `bak_aigul`, без облачного API; произношение требует оценки носителем. Инструкции и ограничения — [docs/TTS.md](docs/TTS.md).

## Альтернативный режим Supabase CLI

Только при осознанном выборе: scripts/setup_local.ps1 -UseSupabaseCli. Не запускай CLI и Compose одновременно: они используют порт 54321. [Архивная инструкция CLI](docs/LOCAL_WINDOWS.md) описывает этот отдельный режим; он не является основным путём запуска. Локальный API привязан к 127.0.0.1; на другом телефоне это сам телефон. Публичное размещение требует отдельной настройки HTTPS и защиты.

Обязательная библиотека Supabase JS поставляется локально с MIT-лицензией. При недоступном CDN вход и упражнения работают без внешней JS-загрузки; внешние шрифты и декоративные анимации могут отсутствовать.

Визуальные регрессии интерфейса: `python tests/browser_visual_checks.py` (Chromium, шесть размеров экрана, CDN отключён, системная тёмная тема, длинный текст и клавиатура). Тест сам запускает временный статический сервер; снимки — `test-results/visual/`. Для просмотра без API: `python -m http.server 8000`, адрес `http://127.0.0.1:8000/web/`. Отчёт о визуальной полировке — [docs/UI_FINAL_PASS.md](docs/UI_FINAL_PASS.md).

Финальная проверка хакатонной сборки: [docs/HACKATHON_POLISH.md](docs/HACKATHON_POLISH.md). Docker integration дополнительно запускает smoke/RLS, браузерный CSV и отчёт преподавателя, а также FSM aiogram на своей изолированной базе; живое соединение с Telegram этим не подтверждается.

Живой Telegram smoke с действиями человека и сверкой БД: [docs/TELEGRAM_LIVE_TEST.md](docs/TELEGRAM_LIVE_TEST.md). Observer не вызывает getUpdates и не меняет webhook. Диагностика включается только для выбранного тестового аккаунта; live-проверки не запускаются в публичном CI.
