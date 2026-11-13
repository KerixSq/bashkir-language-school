# Стабилизация перед демо — 14 ноября 2026

База изменений: KerixSq/bashkir-language-school, commit `0b1b58458e5b2eba18d1781d05adbfb88857fa0f`.
Изменения подготовлены локально. Контейнерный стек ещё требует проверки на машине с Docker Desktop.

## Что исправлено

| Файлы | Причина и результат |
|---|---|
| docker/init_roles.sh, sql/logic.sql, stage9 | Воспроизведён PostgreSQL 42501: роль GoTrue не владела auth.uid(). Исправлен владелец; повтор миграции безопасен. |
| docker-compose.yml | Healthcheck БД проверяет финальный TCP-сервер после init, а не временный Unix socket; включён admin-порт для PostgREST --ready. |
| docker/nginx.conf | Если Authorization отсутствует, anon JWT из apikey передаётся PostgREST как Bearer; токен вошедшего пользователя сохраняет приоритет. |
| Dockerfile, docker/public_config.sh, web/config.js, web/index.html | Публичный адрес текущего сайта и anon JWT конфигурируются при старте app. App получает только ANON_KEY; серверный ключ не передаётся. |
| scripts/settings.py, common.py, check_rls.py, smoke_test.py, doctor.py | Единый выбор .env.docker; старые облачные настройки не подмешиваются. CLI выбирается явно через BASHKIR_ENV_FILE=.env. Doctor больше не считает 404 подтверждением запрета. |
| scripts/*.ps1, .gitattributes | BOM для PowerShell 5.1, LF для shell/SQL. run_local по умолчанию запускает Compose; CLI требует -UseSupabaseCli. |
| docs/DOCKER_WINDOWS.md, README.md, LOCAL_WINDOWS.md | Основной путь Compose, обновление существующей БД, остановка с сохранением volume; бинарный backup через docker cp вместо UTF-16 перенаправления PowerShell. |
| tests/test_settings.py, tests/compose_sql_checks.py | Проверки изоляции окружения и настоящего SQL; остальные Python-изменения — Ruff import/format. |

Подозрение о несуществующем `postgrest --ready` не подтвердилось: команда есть в исходниках v14.18, но требует admin server. GoTrue v2.197.0 действительно содержит миграции замены auth.uid().
Первичные источники: [PostgREST CLI v14.18](https://github.com/PostgREST/postgrest/blob/v14.18/src/PostgREST/CLI.hs), [миграция GoTrue](https://github.com/supabase/auth/blob/v2.197.0/migrations/20211124214934_update_auth_functions.up.sql).

## Выполненные проверки

| Команда / сценарий | Результат |
|---|---|
| python -m unittest discover -s tests -q | PASS, 104 теста |
| python -m compileall -q bot scripts tests | PASS |
| python scripts/check_contract.py | PASS, статическая проверка |
| python -m ruff check . | PASS, Ruff 0.17.5 |
| python -m ruff format --check . | PASS, 86 файлов |
| Разбор всех scripts/*.ps1 настоящим Windows PowerShell 5.1 Parser | PASS, setup_local и run_local |
| tests/compose_sql_checks.py, PG_TEST_ADMIN_DSN на локальном PostgreSQL 17.12 | PASS: исходный отказ владельца воспроизведён; stage9 дважды; schema/seed/logic; три отдельные SQL auth-идентичности через web_register/web_next_fragment/web_submit_answer дают confirmed=3 на фразе колоды БГПУ |
| docker compose config/up/healthchecks | SKIP: Docker отсутствует |
| PostgreSQL 16 в контейнере и полный набор миграций GoTrue | SKIP |
| signInAnonymously(), Auth JWT → HTTP REST → браузер, 3 аккаунта | SKIP: нет запущенного GoTrue/Compose; SQL-идентичности эту проверку не заменяют |
| Публичные HTTP RLS, CSV/JSON, мобильный браузер, Telegram текущей версии | SKIP в этой итерации |

Интеграционный SQL-тест создаёт отдельную БД с уникальным именем и удаляет только её. Для него нужны psycopg, локальная admin DSN и роли anon/authenticated/service_role. Старые результаты предыдущей версии не выданы за проверки текущей версии.

## Windows 11: запуск

Из корня репозитория, Docker Desktop с Linux containers:

```powershell
python scripts/create_docker_env.py
docker compose --env-file .env.docker config --quiet
docker compose --env-file .env.docker up -d --build
docker compose --env-file .env.docker ps
python scripts/doctor.py
python scripts/check_rls.py
```

Открой http://127.0.0.1:54321/web/. Основной запуск также доступен через `powershell -NoProfile -ExecutionPolicy Bypass -File scripts/run_local.ps1`.
Для импорта, backup и существующей БД см. DOCKER_WINDOWS.md. Сначала резервная копия; после stage8 применяй stage9, не пересоздавай volume. Старые облачные данные автоматически не переносятся.

Остановить с сохранением данных:

```powershell
docker compose --env-file .env.docker --profile bot down
```

## Проверить перед жюри

1. На пустом отдельном volume дождаться healthy db/rest/auth/app; убедиться, что GoTrue не пишет migration errors.
2. Импортировать реальный JSONL; открыть три независимых профиля браузера, зарегистрировать разные никнеймы, подтвердить один подготовленный фрагмент. Проверить быстрый ответ, дубль, исправление и потерю сети.
3. Сопоставить серверный профиль, семь полей экспорта, confirmed=3 и прирост библиотеки. Локальная тренировочная XP не должна менять SQL.
4. Проверить запрет чтения users и отсутствие персональных колонок рейтинга через HTTP; проверить экспертный код, CSV/JSON, 360/390/430 px и клавиатуру.
5. Перезапустить контейнеры и сверить сохранность данных. Telegram проверяется отдельно, если он нужен для демо.

Критические открытые риски: контейнерные версии ещё не запускались; живая Auth/HTTP-интеграция не подтверждена; языковые соответствия корпуса требуют ручной проверки. Это подготовка к интеграционному прогону, а не заявление полной готовности к защите.
