# Старт на Windows 11

Основной способ — Docker Compose. Нужны Docker Desktop с Linux containers и Python 3.11+.

```powershell
python scripts/create_docker_env.py
docker compose --env-file .env.docker up -d --build --wait
python scripts/download_phrasebooks.py
docker compose --env-file .env.docker build bot
docker compose --env-file .env.docker run --rm --no-deps bot python scripts/import_phrasebooks.py --dir data/phrasebooks --bad-share 0.2 --seed 42
```

Открой http://127.0.0.1:54321/web/, введи никнейм, выбери языковую пару и получи задание. Вручную вводить ключ не нужно. После git clone JSONL отсутствуют до запуска загрузчика; локальная учебная колода уже включена.

Схема создаётся автоматически только в новом пустом volume. Для существующей БД сделай backup и применяй только недостающие миграции. Не удаляй volume и не меняй пароли существующей БД.

Остановить с сохранением данных:

```powershell
docker compose --env-file .env.docker --profile bot down
```

[README: проверки, лицензия, Telegram, ограничения](README.md) · [Backup и обновление](docs/DOCKER_WINDOWS.md).
Тренировочные XP локальны; серверные очки и общий прогресс считаются PostgreSQL. CLI Supabase — отдельная альтернатива с флагом -UseSupabaseCli; одновременно с Compose его не запускают.
