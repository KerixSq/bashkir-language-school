# Экспертные подсказки сходства (ТЗ 4.4)

Вкладка «Эксперт», после ввода отдельного секретного кода, показывает спорные переводы. Раскройте «Сравнить похожие варианты»: каждая пара содержит сами ответы, количество голосов и текстовое сходство pg_trgm. Выберите вариант радиокнопкой или отредактируйте поле итогового перевода и нажмите «Утвердить перевод».

RPC `expert_list_queue(p_code)` сохранил прежние поля и добавил `similarity_candidates`: `left_translation`, `left_votes`, `right_translation`, `right_votes`, `similarity` (0–1). Сравниваются различные нормализованные ответы одного fragment_pair_id, только eligible. Кандидаты имеют score >= 0.65; показаны до 10 пар среди 20 наиболее частых нормализованных вариантов. Равные нормализованные строки не сравниваются друг с другом. Это ограничение объёма подсказок, не правило консенсуса.

Сходство написания не доказывает эквивалентность смысла. Голоса не объединяются автоматически, synonym_map не меняется. Решение принимает эксперт через прежний защищённый `expert_resolve`; сохраняются история, статус, итоговый перевод и семиполевой translations_export. Повторное решение вне очереди отклоняется. Пересчёт не перезаписывает решение эксперта и не начисляет бонус повторно. Официальная экспертиза носителем/организацией не заявляется.

## Обновление существующей базы в PowerShell

Сначала обычная резервная копия. Миграция не удаляет данные и не меняет права или формулы очков. Копирование файла исключает перекодировку SQL при передаче через старый Windows PowerShell:

```powershell
docker compose --env-file .env.docker cp sql/migrations/20261114_stage12_expert_similarity.sql db:/tmp/stage12.sql
docker compose --env-file .env.docker exec -T db psql -U postgres -d bashkir -v ON_ERROR_STOP=1 -f /tmp/stage12.sql
docker compose --env-file .env.docker up -d --build app
```

Stage12 транзакционная и повторяемая, заменяет только expert_list_queue. На чистой базе функция включена в logic.sql. Для установки поверх старой версии P0 сначала примените необходимые прежние миграции, включая stage11. Не запускайте заново schema/seed/logic поверх существующего volume.

## Проверки

```powershell
python -m unittest discover -s tests -v
python tests/postgres_integration.py
# Только выделенная QA-база с SUPABASE_URL/PUBLIC_KEY/SECRET_KEY:
$env:BASHKIR_QA_ISOLATED = '1'
python tests/browser_expert_checks.py
```

PostgreSQL integration требует локальный PG_TEST_ADMIN_DSN, создаёт свою disposable БД. Browser-тест использует технические строки, временно меняет экспертный хеш только в QA и восстанавливает его в finally; не запускайте его с рабочими ключами. В Docker integration он запускается автоматически внутри уникального тестового проекта. Реальный REST/браузерный цикл: 6 независимых тестовых пользователей → 3 варианта по 2 голоса → подсказка → ручное решение (клик Playwright) → подтверждённый REST-экспорт. Никакие успешные серверные ответы не подменяются.

Локально прошли 135 unit-тестов, compileall, контракт, Ruff, 10 PostgreSQL integration-тестов, aiogram-регрессии P0 и настоящий browser/REST экспертный цикл на 390 px. Stage12 применена дважды в QA и disposable БД. Скриншот: `test-results/visual/expert-similarity-mobile.png`. Docker локально SKIP: daemon недоступен; отдельный прогон выполняется в GitHub Actions.
