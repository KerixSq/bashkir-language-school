# Docker Compose на Windows 11

Здесь основной продукт — сайт, `app` (Nginx), и необязательный `bot` (aiogram).
PostgreSQL (`db`) работает в Docker, вместе с двумя минимальными сервисами,
которые уже нужны проекту: `rest` (PostgREST) и `auth` (Supabase Auth).
Это не полный облачный Supabase: нет Studio, Realtime и Storage. Все данные
и локальные JWT-ключи находятся на ноутбуке. Соединение работает только через
`127.0.0.1`, не публикуй порты в интернет.

## Запуск с нуля

1. Установи Docker Desktop с Linux containers и включи WSL2.
2. Открой PowerShell в корне проекта. Не запускай рядом `npx supabase start`
   на тех же портах: он будет конфликтовать с Compose.
3. Создай отдельные локальные секреты:

```powershell
python .\scripts\create_docker_env.py
```

4. Запусти сервисы сайта и базы:

```powershell
docker compose --env-file .env.docker up -d --build
docker compose --env-file .env.docker ps
docker compose --env-file .env.docker logs --tail 50 db rest auth app
```

5. Открой `http://127.0.0.1:54321/web/`. В настройках сайта используй:
   - адрес API: `http://127.0.0.1:54321`;
   - публичный ключ: `ANON_KEY` из `.env.docker`.
   - **Никогда** не вводи туда `SERVICE_ROLE_KEY`.

6. Если в базе ещё нет фрагментов, импортируй реальный корпус. JSONL лежат
   в `data/phrasebooks/` и монтируются read-only в контейнер бота:

```powershell
docker compose --env-file .env.docker --profile bot run --rm bot python scripts/import_phrasebooks.py --dir data/phrasebooks --bad-share 0.2 --seed 42
```

7. Для Telegram-бота впиши токен в `TELEGRAM_BOT_TOKEN` в `.env.docker` и запусти:

```powershell
docker compose --env-file .env.docker --profile bot up -d --build
docker compose --env-file .env.docker --profile bot logs -f bot
```

`docker compose ... up -d` не запускает бот без `--profile bot`, поэтому
сайт доступен и без Telegram-токена.

## Проверки и обслуживание

```powershell
# Доступность HTML и REST
Invoke-WebRequest http://127.0.0.1:54321/web/
Invoke-WebRequest http://127.0.0.1:54321/health

# Проверка состояния таблиц и сохранённых данных
docker compose --env-file .env.docker exec db psql -U postgres -d bashkir -c 'select count(*) from public.fragment_pairs;'

# Проверка публичного API (анонимный ключ вводится на сайте)
# Для SQL-ошибок на первом запуске смотри логи db:
docker compose --env-file .env.docker logs --tail 100 db

# Остановить без удаления данных
docker compose --env-file .env.docker --profile bot down

# Резервная копия в файл на ноутбуке
docker compose --env-file .env.docker exec -T db pg_dump -U postgres -d bashkir > bashkir-backup.sql
```

**Не используй `docker compose down -v`**, если хочешь сохранить БД:
это удалит volume `postgres_data`. Данные также не синхронизируются с облачным
Supabase и не импортируются автоматически из старого локального CLI Supabase.

### На что обратить внимание

- Схема создаётся **один раз** в новом пустом volume:
  `sql/schema.sql` → `sql/seed.sql` → `sql/logic.sql`.
- Чтобы обновить SQL в существующем volume, используй миграции вручную через
  `docker compose exec -T db psql ... -f ...`, а не очистку данных.
- Если бот уже запущен на Windows вне Docker, сначала останови его: Telegram
  long polling не должен работать в двух экземплярах.
- При отсутствии интернета CDN-шрифты и анимации могут не загрузиться, но
  локальные изображения и игровая колода в контейнере остаются.
- Сайт на другом телефоне не получит доступ по `127.0.0.1`; отдельный HTTPS
  шлюз для внешнего доступа не входит в эту локальную демо-сборку.
- Проверяй в браузере анонимный вход и API после запуска: проверка Compose
  не доказывает корректность PostgreSQL RPC.
