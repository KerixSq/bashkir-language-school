# Альтернативный режим Supabase CLI

Основной запуск описан в [WINDOWS_SETUP.md](WINDOWS_SETUP.md). Эта инструкция относится к CLI: добавляй `-UseSupabaseCli` к setup_local.ps1/run_local.ps1. Перед запуском останови Compose. Для проверок CLI явно установи `$env:BASHKIR_ENV_FILE=".env"`.

# Все данные на своём ноутбуке · Windows 11

Это альтернативный режим Supabase CLI. Основной запуск — Docker Compose по README.md. Локальная PostgreSQL и Supabase REST API работают через Docker Desktop; Telegram-бот и веб-игра запускаются на Windows. Регистрация в облачном Supabase не требуется.

**Важно:** ключи из `supabase status` теперь автоматически записываются в действующий `.env`. Если там уже были настройки облака, они сохраняются в файле `.env.backup-*`. Скрипт не переписывает `TELEGRAM_BOT_TOKEN`.

**Важно:** локальный `supabase start` — **не публичный сервер**. Он не защищён для публикации в интернет. Не пробрасывай порты 54321/54322/54323 на роутере, не используй его для настоящего публичного сайта или хранения чувствительных данных школьников без отдельной защиты. Сайт и бот станут недоступны, если выключить ноутбук или остановить контейнеры. При нормальном `supabase stop` данные сохраняются; не используй `--no-backup`.

## 1. Один раз установить инструменты

- [Docker Desktop](https://www.docker.com/products/docker-desktop/) (включи движок Linux / WSL2).
- [Node.js 20+](https://nodejs.org/) и npm.
- Python 3.11+ и VS Code.

Supabase CLI требует запущенный Docker. Для полного локального стека ориентируйся минимум на 7 ГБ доступной RAM. Первый запуск требует интернета, чтобы скачать Docker-образы и CLI; далее работать с уже скачанными образами можно без облака. Telegram требует интернет даже при локальной базе.

## 2. Запустить Supabase одной командой

В PowerShell из корня `bashkir-language-school`:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\setup_local.ps1 -UseSupabaseCli
```

Скрипт установит официальную Supabase CLI через npm (если её нет), создаст локальный проект, ограничит привязку портов `127.0.0.1` и запустит Docker. Обрати внимание на ключи, которые выводит `supabase status`: **не показывай их в трансляции экрана**. Если PowerShell запускается из VS Code, просто используй новый терминал.

Адреса по умолчанию:

| Сервис | Адрес |
|---|---|
| Supabase Studio / SQL Editor | `http://127.0.0.1:54323` |
| Supabase REST API | `http://127.0.0.1:54321` |
| PostgreSQL | `127.0.0.1:54322` |

## 3. Один раз создать схему

В локальном SQL Editor выполни **по очереди** полное содержимое файлов:

1. `sql/schema.sql`
2. `sql/seed.sql`
3. `sql/logic.sql`

Эти три файла содержат актуальную схему до stage14. **Не применяй к новой чистой базе заново файлы из `sql/migrations/`**. Для существующей CLI-базы сначала backup и подтверждение её версии, затем только недостающий суффикс миграций. После stage5 нужны stage6, stage7, stage8 и последующие этапы; две stage11 имеют разные назначения. Имена/порядок stage9–14 — [WINDOWS_SETUP](WINDOWS_SETUP.md). В CLI выполняйте выбранные SQL-файлы в локальном SQL Editor; команды Compose для контейнера db к CLI не относятся. Не останавливайтесь на stage7 и не запускайте старые файлы отдельно поверх новых.

## 4. Подключить бота

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r bot\requirements.txt
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
notepad .env
```

Укажи **локальные** значения из `npx supabase status` (скрипт `setup_local.ps1` уже записывает три первых значения в `.env` и сохраняет твой старый токен бота):

```text
SUPABASE_URL=http://127.0.0.1:54321
SUPABASE_SECRET_KEY=<локальный Secret key / Service role key>
SUPABASE_PUBLIC_KEY=<локальный Publishable key / Anon key>
TELEGRAM_BOT_TOKEN=<токен из BotFather>
```

Никогда не добавляй `.env` в Git. Не публикуй секретный ключ даже в HTML на localhost.

Проверки (после создания таблиц):

```powershell
.\.venv\Scripts\python.exe scripts\check_contract.py
.\.venv\Scripts\python.exe scripts\check_rls.py
.\.venv\Scripts\python.exe scripts\setup_access.py --kind expert
.\.venv\Scripts\python.exe scripts\smoke_test.py --expert-code "ТВОЙ_КОД_ЭКСПЕРТА"
```

Для базы с настоящими фразами импортируй пять JSONL БГПУ как описано в README. На этом шаге нельзя автоматически считать импортированные переводы проверенными: они получают статус `collecting`.

Запусти бота в терминале:

```powershell
.\.venv\Scripts\python.exe -m bot.main
```

## 5. Запустить сайт на том же компьютере

Во втором терминале:

```powershell
python -m http.server 8000 --bind 127.0.0.1
```

Открой `http://127.0.0.1:8000/web/`. Для уроков достаточно локального `learning-deck.json`. Чтобы видеть рейтинги и библиотеку, нажми «Показать настройки» и подключи:

- адрес: `http://127.0.0.1:54321`;
- только **публичный** ключ из `supabase status`.

После подключения кнопка «Обновить прогресс» в разделе библиотеки показывает **реальные** подтверждённые переводы `ba-ru` или `ba-kk`. Демо-источники `license='demo'` в общий счёт не включены. Личный опыт веб-игры остаётся в `localStorage` и не является голосованием.

**Другие устройства:** Telegram работает на телефонах участников, пока бот на твоём ноутбуке подключён к Telegram. Но веб-страница, открытая на чужом телефоне, **не сможет** использовать его `localhost` для доступа к базе твоего ноутбука. Локальный сайт и REST API открывайте на компьютере, где запущена платформа. Для доступа с других устройств понадобится отдельно защищённое размещение API с HTTPS — не выставляй локальный Supabase наружу.

## 6. После перезапуска ноутбука

Запусти Docker Desktop, затем в PowerShell в папке проекта:

```powershell
npx --no-install supabase start --network-id local-network
.\.venv\Scripts\python.exe -m bot.main
```

Для запуска сайта и бота **одной командой** (после настройки токена и SQL) используй:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\run_local.ps1 -UseSupabaseCli
```

Перед запуском эта команда выполняет `scripts/doctor.py`: проверяет наличие файлов, публичное представление API и запрет прямого чтения `users`. Если проверка не прошла, бот не запускается. Запускай только с локальными ключами. `Ctrl+C` останавливает бот и локальный веб-сервер.

Для остановки локальной базы используй `npx --no-install supabase stop`, **без** `--no-backup`. Перед защитой сделай отдельную резервную копию через инструменты PostgreSQL/Supabase; не полагайся на один Docker volume. При выключенном ноутбуке Telegram-бот также перестанет отвечать.

## Проверка без внешней БД

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -m compileall bot scripts tests
.\.venv\Scripts\python.exe scripts\check_contract.py
```

Если установлен Ruff: `ruff check .` и `ruff format --check .`. SQL и права RLS обязательно проверяются на **работающем** локальном Supabase, одних юнит-тестов недостаточно.
