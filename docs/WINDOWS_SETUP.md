# Windows 11: установка, обновление и резервная копия

Основной режим — Docker Desktop, Linux containers/WSL2, Git и Python 3.11+. Все команды из корня репозитория в PowerShell. Порт 54321 должен быть свободен; Supabase CLI параллельно не запускать. Первый запуск требует интернета для образов и корпуса. Не показывайте `.env.docker`, логи с секретами и коды преподавателей на трансляции.

## Новая установка

```powershell
git clone https://github.com/KerixSq/bashkir-language-school.git
Set-Location bashkir-language-school
git switch main
python scripts/create_docker_env.py
docker compose --env-file .env.docker config --quiet
docker compose --env-file .env.docker up -d --build --wait
python scripts/download_phrasebooks.py
docker compose --env-file .env.docker build bot
docker compose --env-file .env.docker run --rm --no-deps bot python scripts/import_phrasebooks.py --dir data/phrasebooks --dry-run
docker compose --env-file .env.docker run --rm --no-deps bot python scripts/import_phrasebooks.py --dir data/phrasebooks --bad-share 0.2 --seed 42
Start-Process http://127.0.0.1:54321/web/
```

`--no-deps` у импортёра использует уже работающий REST и не запускает polling/Tor. Колода браузера и серверный корпус — разные ресурсы. Импортированный корпус получает collecting, а не фиктивные подтверждения. Лицензия/хеши: CORPUS_PROVENANCE.json. SQL schema → seed → logic применяется автоматически только к пустому volume и уже содержит stage14. На чистой установке миграции вручную не нужны.

## Резервная копия перед обновлением

Остановите запись ответов на время копирования и миграций: закройте сайт, остановите единственный бот. БД оставьте запущенной. Backup содержит персональные данные и ключи — храните вне Git, с ограниченным доступом.

```powershell
docker compose --env-file .env.docker --profile bot stop bot
$backupRoot = Join-Path $env:USERPROFILE ('bashkir-backups\' + (Get-Date -Format yyyyMMdd-HHmmss))
New-Item -ItemType Directory -Path $backupRoot -Force | Out-Null
docker compose --env-file .env.docker exec -T db pg_dump -U postgres -d bashkir -Fc -f /tmp/bashkir-backup.dump
if ($LASTEXITCODE -ne 0) { throw 'pg_dump failed' }
docker compose --env-file .env.docker cp db:/tmp/bashkir-backup.dump "$backupRoot\bashkir-backup.dump"
if ($LASTEXITCODE -ne 0) { throw 'Backup copy failed' }
docker compose --env-file .env.docker exec -T db pg_restore --list /tmp/bashkir-backup.dump | Out-Null
if ($LASTEXITCODE -ne 0) { throw 'Backup archive unreadable' }
Copy-Item -LiteralPath .env.docker -Destination $backupRoot
if (Test-Path web/assets/original-audio) { Copy-Item web/assets/original-audio "$backupRoot\original-audio" -Recurse }
```

`pg_restore --list` проверяет читаемость архива, не полноценное восстановление. Восстановление проверяйте отдельно на изолированной БД, не поверх работающей. Сохраните также разрешения/исходную разметку аудио. Пароли/JWT из действующего `.env.docker` не пересоздавать.

## Обновление существующей установки

```powershell
git status --short
git fetch origin
git switch main
git pull --ff-only origin main
```

При незакоммиченных локальных изменениях сначала сохраните их отдельно; не используйте reset/force. В проекте нет единого журнала применённых миграций. Установите последнюю применённую версию по собственным записям и определению функций. Для базы до stage9 сначала изучите старые миграции stage1–8 и [WINDOWS_SETUP.md](WINDOWS_SETUP.md). Следующий блок предназначен для **подтверждённой базы stage9 или новее**, а не любой неизвестной схемы.

| Порядок | Точный файл | Назначение |
|---|---|---|
| 9 | 20261114_stage9_auth_owner.sql | Владелец auth.uid для GoTrue; если уже применена, пропустить |
| 10 | 20261114_stage10_period_points.sql | Серверные очки выбранного периода |
| 11a | 20261114_stage11_auth_search_path.sql | search_path роли GoTrue, **отдельная миграция** |
| 11b | 20261114_stage11_independent_students.sql | Ученик без класса, защищённая выдача заданий |
| 12 | 20261114_stage12_expert_similarity.sql | Подсказки эксперту |
| 13 | 20261114_stage13_original_audio.sql | Импорт исходного аудио/таймкодов |
| 14 | 20261114_stage14_daily_reminders.sql | Добровольные напоминания |

Номер stage11 не уникален: оба файла нужны. Лексикографическая сортировка всех имён неверна (stage10 окажется раньше stage9). Если база уже stage14, SQL повторять не требуется. Для подтверждённой stage9 выполнить оставшийся суффикс **в указанном порядке**:

```powershell
# Удалите из списка только точно применённый начальный префикс.
$pendingMigrations = @(
 '20261114_stage10_period_points.sql',
 '20261114_stage11_auth_search_path.sql',
 '20261114_stage11_independent_students.sql',
 '20261114_stage12_expert_similarity.sql',
 '20261114_stage13_original_audio.sql',
 '20261114_stage14_daily_reminders.sql'
)
foreach ($migrationFile in $pendingMigrations) {
 docker compose --env-file .env.docker cp "sql/migrations/$migrationFile" db:/tmp/upgrade.sql
 if ($LASTEXITCODE -ne 0) { throw "Cannot copy $migrationFile" }
 docker compose --env-file .env.docker exec -T db psql -U postgres -d bashkir -v ON_ERROR_STOP=1 -f /tmp/upgrade.sql
 if ($LASTEXITCODE -ne 0) { throw "Migration failed: $migrationFile; stop and inspect" }
}
docker compose --env-file .env.docker restart auth rest
docker compose --env-file .env.docker up -d --build --wait
```

Не передавайте SQL через `Get-Content | docker ... psql`: кодировка PowerShell может повредить кириллицу. Эти миграции транзакционные; ошибка останавливает последовательность. Не выполняйте schema/seed/logic повторно на существующем volume. Исторические миграции могут заменять более новые функции — нельзя накатывать старый этап поверх нового отдельно от полного нужного суффикса.

## Telegram: один polling на токен

Введите токен локально в существующий `.env.docker`, не публикуйте его. Установите BOT_USERNAME для ссылки на бота (без @). Остановите другие экземпляры на Windows/серверах. Tor-режим:

```powershell
docker compose --env-file .env.docker --profile bot up -d --build tor bot
docker compose --env-file .env.docker --profile bot ps
```

Direct-режим — явный выбор при доступном Telegram, без автоматического fallback:

```powershell
$env:BOT_PROXY_URL = 'direct'
docker compose --env-file .env.docker --profile bot up -d --build --no-deps bot
Remove-Item Env:BOT_PROXY_URL
```

Direct работает при уже здоровом основном стеке. Для возврата Tor удалите локальное переопределение BOT_PROXY_URL в `.env.docker`, если сами его добавляли, и пересоздайте только bot указанной Tor-командой. Никакие секреты заменять не нужно. Состояние Tor проверяется healthcheck, доступность Telegram — отдельно; здоровье сайта не доказывает живой polling.

Ручная проверка на специальном тестовом профиле: `/start` → никнейм → ученик → самостоятельно → пара → `/task` → ответ → `/me` → `/join` с настоящим кодом тестового класса → `/remind on` → меню настроек → `/remind off`. Уведомление только в настроенный час Уфы (по умолчанию 18), если дневная цель не выполнена. Реальные аккаунты без участия человека не проверяются. Проверка одного контейнера ниже не исключает чужой процесс на другом компьютере:

```powershell
docker compose --env-file .env.docker --profile bot ps bot
Get-CimInstance Win32_Process | Where-Object { $_.Name -match '^python' -and $_.CommandLine -match 'bot\.main' } | Select-Object ProcessId, Name
```

## Состояние, API и диагностика

```powershell
docker compose --env-file .env.docker ps
Invoke-WebRequest http://127.0.0.1:54321/health
Get-NetTCPConnection -LocalPort 54321 -ErrorAction SilentlyContinue
docker compose --env-file .env.docker logs --tail 60 db rest auth app
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
$env:BASHKIR_ENV_FILE = '.env.docker'
.\.venv\Scripts\python.exe scripts/doctor.py
.\.venv\Scripts\python.exe scripts/check_rls.py
.\.venv\Scripts\python.exe scripts/check_readiness.py --strict
```

Doctor/RLS читают API; readiness проверяет счётчики и не заменяет E2E. Smoke-тест создаёт собственные временные записи: запускайте его на отдельной QA-базе. Браузер/экспорт: сайт → серверная проверка → вкладка «База переводов» → confirmed → JSON/CSV. Локальный тренажёр не создаёт серверных голосов.

Остановка без удаления данных:

```powershell
docker compose --env-file .env.docker --profile bot stop
```

`stop` сохраняет контейнеры и volumes; обычный `down` тоже сохраняет named volume. Не используйте `down -v`, reset или повторную инициализацию. Локально в технической проверке Docker daemon недоступен: чистая установка/рестарт стека проверяются изолированным Actions, а выполнение команд обновления на конкретной Windows-машине остаётся ручной проверкой.
