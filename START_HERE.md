# Запуск после продолжения работы Codex — Windows 11

В этой сборке уже есть пять JSONL разговорников БГПУ, игровая колода `web/assets/learning-deck.json` (350 фраз `ba-ru` + 350 `ba-kk`), мультяшная карта, бот, SQL и API. Самое важное — не начинать разработку заново, а запустить и проверить проект.

## 1. Подними локальную базу

Установи Docker Desktop, Node.js 20+ и Python 3.11+. Открой PowerShell в **корне** папки `bashkir-language-school`:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\setup_local.ps1
```

Скрипт запускает локальный Supabase и вписывает его ключи в **активный `.env`**. Если файл уже существовал, его прежняя версия сохраняется в `.env.backup-*`; **токен Telegram не меняется**. Не показывай эти файлы на экране во время питча.

## 2. Создай схему только один раз

В `http://127.0.0.1:54323` → SQL Editor последовательно выполни `sql/schema.sql`, `sql/seed.sql`, `sql/logic.sql` — **только для новой пустой базы**.

На базе, которую ты уже использовал, **не запускай схему повторно**. При необходимости применяй недостающие миграции по порядку, начиная после последней реально применённой. Миграция `20261113_stage7_runtime_fixes.sql` защищает от гонки при исправлении ответа; на чистой базе уже входит в `logic.sql`.

## 3. Заполни Telegram-токен

```powershell
notepad .env
```

Укажи `TELEGRAM_BOT_TOKEN` из BotFather. Не отправляй этот токен в чат, GitHub или скриншоты.

## 4. Проверь API и ограничения доступа

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r bot\requirements.txt
.\.venv\Scripts\python.exe scripts\doctor.py --require-bot
.\.venv\Scripts\python.exe scripts\check_rls.py
.\.venv\Scripts\python.exe scripts\setup_access.py --kind expert
```

Последняя команда выдаст отдельный код эксперта; сохрани его приватно. После этого выполни:

```powershell
.\.venv\Scripts\python.exe scripts\smoke_test.py --expert-code "ТВОЙ_СЕКРЕТНЫЙ_КОД"
```

**Если есть FAIL — не показывай SQL/API как проверенный до исправления ошибки.**

## 5. Импортируй настоящие фразы

```powershell
.\.venv\Scripts\python.exe scripts\import_phrasebooks.py --dir .\data\phrasebooks --dry-run
.\.venv\Scripts\python.exe scripts\import_phrasebooks.py --dir .\data\phrasebooks --bad-share 0.2 --seed 42
```

Корпус поставляется с лицензией CC BY 4.0 и файлом `NOTICE` с полными именами правообладателя и издателя. Переводы не проверены носителем построчно: используй `--review-out` для ручной экспертизы.

## 6. Запусти сайт и Telegram-бот одной командой

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\run_local.ps1
```

Сайт: `http://127.0.0.1:8000/web/`. В настройках сайта укажи `http://127.0.0.1:54321` и **только публичный** ключ Supabase. `Ctrl+C` останавливает бот и веб-сервер; база останавливается отдельно командой `npx supabase stop` без `--no-backup`.

Другие участники могут пользоваться Telegram-ботом, пока ноутбук включён и подключён к интернету. Но сайт, открытый на чужом телефоне, не сможет использовать `localhost` твоего ноутбука. Не публикуй локальный Supabase напрямую в интернет.

## 7. Демо для жюри

Покажи реальный фрагмент БГПУ → задание в Telegram → три независимых ответа → `confirmed` в PostgreSQL → экспорт через REST → увеличение счётчика Библиотеки Акбузата. Подробности в `docs/DEMO_3_MINUTES.md`.

**Если что-то не запускается:** прочитай сообщение `scripts/doctor.py`, затем `docs/LOCAL_WINDOWS.md`. Не запускай команды `db reset`, `stop --no-backup` и не удаляй тома Docker, если в базе уже есть нужные ответы.

hello from cb