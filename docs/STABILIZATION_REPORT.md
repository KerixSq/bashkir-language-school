# Точечная стабилизация — 14 ноября 2026

Стек и интерфейс сохранены. Основной запуск — Docker Compose; CLI остаётся явной альтернативой. Исходная точка: `77269ed`. Параллельные изменения main сохранены, включая настройку Auth DSN; история не откатывалась.

## Реальные результаты

| Проверка | Результат |
|---|---|
| `python -m unittest discover -s tests -q` | PASS, 106 тестов; Windows и Ubuntu в Actions |
| `python -m compileall -q bot scripts tests` | PASS |
| `python scripts/check_contract.py` | PASS, статическая проверка |
| Ruff 0.17.5 check и format --check | PASS |
| `python tests/postgres_integration.py` | PASS, 8 тестов на настоящем PostgreSQL; периодные очки, гонки, дубли, повтор миграции |
| `python tests/browser_checks.py` | PASS в Actions: 360/390/430/768/1280 px, полный урок, сохранение XP, повтор ошибки, повреждённое хранилище и недоступная колода |
| `python tests/docker_integration.py` | PASS на Ubuntu runner: настоящий PostgreSQL 16, GoTrue v2.197.0, PostgREST v14.18, Nginx |
| Перезапуск Docker | PASS: сохранены ответы, сумма очков, профиль и Auth-сеансы трёх браузеров |
| Работа при заблокированных CDN | PASS: локальный Supabase JS, три настоящих anonymous signup, браузерные ответы и SQL confirmed=3 |
| HTTP API и приватность | PASS: экспорт ровно из семи полей, публичный рейтинг без персональных полей, запрет users для anon/authenticated, быстрый ответ, дубль и ошибка сети |

Проверяемый полный прогон: [Actions 43518633925](https://github.com/KerixSq/bashkir-language-school/actions/runs/43518633925). Это исполнение контейнеров и HTTP, а не подменённые ответы. Финальные изменения дополнительно проверяются последующим workflow репозитория.

Docker-тест использует уникальный проект и свободный порт 54321, импортирует настоящие файлы БГПУ по зафиксированным хешам. Пользовательский Compose-проект не используется. В завершение вызывается только down, без удаления volumes. Тестовые Auth-профили явно называются Integration; их голоса не являются лингвистической экспертизой.

## Исправленные причины отказов

- GoTrue создавал таблицу schema_migrations в public: установлен search_path роли с auth первым, без выдачи CREATE на public.
- PostgREST --ready не принимал wildcard-адрес административного сервера: задан 127.0.0.1.
- Nginx возвращал 502 на пакетном UUID-фильтре импорта из-за большого Content-Location: увеличен proxy_buffer_size.
- Supabase JS-клиент пересоздавался из-за сравнения URL со слешем и не учитывал смену ключа: сравниваются канонический URL и ключ; таймер прежнего клиента останавливается, устаревшее задание сбрасывается.
- Главный и подробный рейтинги показывали общие очки при выборе периода: добавлены day/week/month/year_points, исправлены оба отображения.
- Серверные очки записывались в элементы с подписью XP: локальные показатели тренировки и серверный профиль разделены.
- Обязательная авторизация зависела от CDN: Supabase JS 2.119.0 поставляется локально с MIT LICENSE и SHA-256.

## Изменённые файлы

| Файлы | Назначение |
|---|---|
| README.md, START_HERE.md, AGENTS.md | Один основной путь Compose; честная загрузка data/ после git clone |
| scripts/run_local.ps1, scripts/setup_local.ps1 | Compose по умолчанию; CLI по флагу и с явным выбором .env |
| docs/DOCKER_WINDOWS.md, docs/LOCAL_WINDOWS.md, docs/BROWSER_FIRST.md, docs/DEMO_3_MINUTES.md, API.md | Согласованы запуск, миграции, CDN, периоды и браузерные голоса |
| docker-compose.yml, docker/init_roles.sh, docker/nginx.conf | Readiness, схема миграций Auth, импорт через прокси; выключены access logs Auth/REST |
| sql/logic.sql, sql/migrations/20261114_stage10_period_points.sql | Периодные очки; миграция не меняет существующие ответы |
| sql/migrations/20261114_stage11_auth_search_path.sql | Исправление Auth для существующей БД, идемпотентно |
| scripts/import_phrasebooks.py | Пропускается ненужный поиск подстановок при bad-share=0 |
| web/index.html | Исправление клиента, рейтингов, обновления после ответа и маркировки XP |
| web/assets/vendor/supabase.min.js, supabase-LICENSE, README.md | Локальная обязательная библиотека и происхождение |
| tests/docker_integration.py, .github/workflows/ci.yml | Полный автоматический прогон контейнеров, HTTP и браузера |
| tests/postgres_integration.py, tests/test_browser_client.py, tests/test_browser_first.py | Регрессии периодов, JS-клиента и локальной зависимости |
| bot/main.py | Только форматирование параллельно добавленной строки; поведение сохранено |

## Запуск и существующие данные

См. README.md и START_HERE.md. После чистого git clone сначала скачай JSONL через scripts/download_phrasebooks.py, затем импортируй их через контейнер bot. Никакие вымышленные языковые данные не добавлены.

Для существующей БД: backup, затем только недостающие stage10 и stage11 после stage9. Используй docker compose cp и psql -v ON_ERROR_STOP=1 по инструкции DOCKER_WINDOWS.md. Перезапусти auth после stage11. Не пересоздавай .env.docker и не удаляй volume.

Не проверялись в этой итерации: Docker Desktop непосредственно на Windows и живой Telegram polling. Windows unit-тесты и разбор PowerShell выполнялись отдельно. Шрифты и необязательные эффекты могут отсутствовать без CDN; вход и серверный цикл проверены без него. Корпус требует ручной языковой проверки, анонимные аккаунты не обеспечивают сильной защиты от мультиаккаунтов.
