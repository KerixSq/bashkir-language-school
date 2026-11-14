# REST API

Stage14: claim_daily_reminders(p_now timestamptz,p_limit integer) — только service_role, резервирует дату одной ежедневной попытки по Уфе через SKIP LOCKED. Публичный вызов/список Telegram-получателей запрещён. Согласие меняет только бот по from_user через /remind on/off; публичного reminder API нет. Подробности: [Telegram и напоминания](docs/TELEGRAM.md).

Stage13: задания дополнительно возвращают source_kind/source_url/source_license и прежние time_start/time_end для исходного аудио. Новый import_audio_fragments(jsonb,jsonb) — только service_role, для CLI; публичное исполнение запрещено. В translations_export по-прежнему семь полей, таймкоды находятся в source. [Импорт и контракт](docs/CONTENT_AND_AUDIO.md).

Stage12: защищённый `expert_list_queue(p_code)` дополнительно возвращает `similarity_candidates` с двумя вариантами, числом голосов и score pg_trgm (0–1). Это подсказка эксперту, не семантическое объединение; запись выполняется прежним `expert_resolve`. Права и семь полей `translations_export` сохранены. Подробности: [Экспертное согласование](docs/EXPERT_REVIEW.md).

Telegram и веб используют общий submit_answer/консенсус и агрегированные представления. Самостоятельный Telegram-ученик может иметь class_id=NULL (stage11); публичные RLS не расширялись. Новый личный вклад запрашивается только доверенным ботом по from_user; браузеру API чужой истории не добавлен. Контракт translations_export остаётся из семи полей.

Все запросы идут в PostgREST. При основном запуске через Compose базовый адрес — `http://127.0.0.1:54321/rest/v1/`; для отдельно настроенного облачного Supabase — `https://PROJECT.supabase.co/rest/v1/`. Обязателен HTTP-заголовок `apikey` с публичным ключом проекта для публичных вызовов. Для новых ключей вида `sb_publishable_...` не требуется указывать их в `Authorization: Bearer`: это не JWT.

Укажи адрес проекта в переменной PowerShell:

```powershell
$base = "$env:SUPABASE_URL/rest/v1"
$headers = @{ apikey = $env:SUPABASE_PUBLIC_KEY }
```

## Публичное чтение

```powershell
Invoke-RestMethod -Uri "$base/translations_export?status=eq.confirmed&limit=10" -Headers $headers
Invoke-RestMethod -Uri "$base/leaderboard_users?select=name,points,day_answers,corrections,vocabulary" -Headers $headers
Invoke-RestMethod -Uri "$base/leaderboard_schools?select=name,points,users_count" -Headers $headers
Invoke-RestMethod -Uri "$base/leaderboard_classes?select=name,school,points,users_count" -Headers $headers
```

`translations_export` содержит **ровно семь** полей:

| Колонка | Тип | Значение |
|---|---|---|
| `fragment_id` | uuid | Фрагмент |
| `text_ba` | text | Исходный текст |
| `lang_pair` | text | `ba-ru`, `ba-en`, `ba-kk` |
| `translation` | text | Читаемый вариант |
| `source` | text | Название/глава/позиция/секунды |
| `confirmed` | integer | Число голосов за подтверждённый вариант; 0 пока нет подтверждения |
| `status` | text | `collecting`, `confirmed`, `expert_review` |

Пример ответа (поля условные, текст технический, **не** башкирский перевод):

```json
[{"fragment_id":"00000000-0000-0000-0000-000000000001","text_ba":"[текст из источника]","lang_pair":"ba-ru","translation":"[проверенный перевод]","source":"[название] · глава 1 · позиция 1","confirmed":3,"status":"confirmed"}]
```

Публичные рейтинги содержат никнеймы (поле `name`) и показатели, **не** `user_id` или `telegram_id`. `user_stats`, `expert_review_queue` и исходные таблицы публичному ключу недоступны.

## Отчёт класса — по секрету преподавателя

RPC: `POST /rpc/get_class_report`

```powershell
$body = @{ p_teacher_code = 'ДЛИННЫЙ_СЕКРЕТНЫЙ_КОД' } | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri "$base/rpc/get_class_report" -Headers $headers -ContentType 'application/json' -Body $body
```

Ответ включает `school`, `class`, `students_count`, `answers_count`, `error_rate`, `top_students` (`name`, `points`, `level`, `answers`), `activity` (`day`, `answers`), `students_progress` (`name`, `today_answers`, `completed`), `frequent_mistakes` (`text_ba`, `lang_pair`, `errors`). **Короткий `join_code` не даёт доступ.** На сайте и в боте доступна выгрузка CSV с разделами «Сводка», «Топ», «Активность», «Прогресс», «Частые ошибки». Код передаётся только в теле POST и не сохраняется сайтом в localStorage.

## Эксперт — по отдельному секрету

Получить спорные случаи:

```powershell
$body = @{ p_code = 'КОД_ЭКСПЕРТА' } | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri "$base/rpc/expert_list_queue" -Headers $headers -ContentType 'application/json' -Body $body
```

Ответ: массив `fragment_pair_id`, `text_ba`, `lang_pair`, `auto_translation`, `source`, `status`, `options` (исходный текст варианта, число голосов и суммарный вес), `similar_variants` (похожесть написания через pg_trgm, не смысл).

Утвердить вариант:

```powershell
$body = @{ p_code = 'КОД_ЭКСПЕРТА'; p_fragment_pair_id = 'UUID_ПАРЫ'; p_translation = 'Итоговый текст.' } | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri "$base/rpc/expert_resolve" -Headers $headers -ContentType 'application/json' -Body $body
```

Ответ: `{"status":"confirmed","confirmed_count":2}`. Решение попадает в `expert_decisions`, изменение — в `status_history`. Для реального запуска сначала выпусти секрет `scripts/setup_access.py --kind expert`.

## Партнёрский API — отдельный `bsk_...` ключ

Получить ключ через `scripts/create_api_key.py --partner "Пилот" --permission write --days 30` (должен быть у администратора с серверным ключом). В `api_keys` хранятся только SHA-256, права, срок действия и дата отзыва. При отзыве заполни `revoked_at`.

```powershell
$body = @{ p_key = 'bsk_СЕКРЕТНЫЙ_КЛЮЧ'; p_lang_pair = 'ba-ru'; p_limit = 20; p_cursor = $null } | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri "$base/rpc/api_get_fragments" -Headers $headers -ContentType 'application/json' -Body $body
```

Ответ:

```json
{"items":[{"fragment_pair_id":"00000000-0000-0000-0000-000000000001","text_ba":"[исходный текст]","lang_pair":"ba-ru","auto_translation":"[черновик]","final_translation":null,"status":"collecting","source":"[название]"}],"next_cursor":"00000000-0000-0000-0000-000000000001"}
```

`p_limit` от 1 до 100, `p_cursor` — `fragment_pair_id` последней записи предыдущей страницы (или `null`).

```powershell
$body = @{ p_key = 'bsk_СЕКРЕТНЫЙ_КЛЮЧ'; p_external_user = 'student-42'; p_fragment_pair_id = 'UUID_ПАРЫ'; p_translation = 'Мой вариант.' } | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri "$base/rpc/api_submit_answer" -Headers $headers -ContentType 'application/json' -Body $body
```

Возвращается `{"accepted":true,"duplicate":false}` либо `{"accepted":false,"duplicate":true}`. **Внешние ответы не влияют на консенсус, рейтинг и очки учеников Telegram.** `p_external_user` в базе хранится только как SHA-256 с привязкой к партнёру. Если нужен импорт внешних голосов в основную систему, нужен отдельный процесс проверки, в прототипе его нет.

## Только серверу

`get_next_fragment(p_user_id uuid)` — объект задания с `fragment_pair_id`, `text_ba`, `translation`, `lang_pair`, `source`, `time_start`, `time_end`. Задание закреплено за пользователем в `users.current_fragment_pair_id` и `users.current_shown_at`.

`submit_answer(p_user_id uuid,p_fragment_pair_id uuid,p_action text,p_text text)` — запись голоса, пересчёт консенсуса и очков. Для слишком быстрого ответа возвращает `{"too_fast":true,"retry_seconds":2}`, ничего не начисляя; дубль — `{"duplicate":true,...}`. Успех включает `points_awarded`, `points`, `level`, `status`, `daily_goal`, `today_answers`, `goal_streak`, `caught_planted_error` и `correct_translation` при подтверждённой подставной ошибке.

`create_teacher_class(p_user_id,p_invite,p_name)` — создание класса подтверждённым преподавателем по отдельному коду приглашения. Лимит: три класса на преподавателя. Результат: `join_code` и `teacher_code`.

Эти три RPC доступны только `service_role`; **никогда не помещай `sb_secret_...` в браузер**.

## Ошибки и права

| Ситуация | Ответ |
|---|---|
| Нет/неверный публичный ключ Supabase | HTTP 401 или 403 |
| Запрос закрытой таблицы публичным ключом | HTTP 401/403, `permission denied` |
| Неизвестная RPC после миграции | HTTP 404 или `PGRST202`; обнови кэш схемы: `NOTIFY pgrst, 'reload schema';` |
| Неверный код/истёкший партнёрский ключ | HTTP 400/403, описание ошибки PostgreSQL |
| Повторный ответ на ту же пару | HTTP 200 + `duplicate:true` |
| Ответ быстрее разрешённого | HTTP 200 + `too_fast:true` |

Код SQL/HTTP-ошибки зависит от PostgREST; не стоит делать клиентскую логику на точном тексте сообщения.

## Схема данных

```text
schools ── classes ── users ── answers ── fragment_pairs ── fragments ── sources
                        │                 │
                   user_badges          synonym_map (по lang_pair)
                        │                 ├─ expert_decisions
                      badges             └─ status_history
api_keys ── external_answers ──────────────────────────────┘
import_batches ── sources
config (параметры игры и хеши секретов)
```

Сутки, недели, серии и отчёты считаются по `Asia/Yekaterinburg` (UTC+5). Индексы и полные ограничения находятся в `sql/schema.sql` и `sql/logic.sql`.

## Происхождение разговорников

Текстовый корпус [Bashkorttele / БГПУ](https://huggingface.co/datasets/bashkorttele/trilingual-parallel-phrasebooks-bgpu) распространяется по [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). При повторном использовании экспортированных записей сохраняй атрибуцию источника, лицензию и сведения об изменениях (отбор языков, удаление дублей, добавление подставных ошибок). По `NOTICE`: правообладатель — ФГБОУ ВО «БГПУ им. М. Акмуллы», издатель — АНО «Фонд сохранения и развития башкирского языка».

`phrasebook_rows` — только служебная таблица, доступная `service_role`, не публичный REST-ресурс. `row_id` хранится как `file_name::исходный-id`, потому что одинаковый ID может встречаться в разных файлах разговорников. Для API координаты основной записи остаются в поле `source` представления `translations_export`.

## Общий прогресс библиотеки (публично)

`GET /rest/v1/adventure_progress?select=lang_pair,confirmed,collecting,expert_review`

Возвращает агрегированное количество пар переводов без идентификаторов пользователей и без личных ответов. Источники с `license='demo'` исключены. Пример одной строки (числа условные, формат реальный):

```json
{"lang_pair":"ba-ru","confirmed":7,"collecting":15,"expert_review":2}
```

При локальной разработке замени URL проекта на `http://127.0.0.1:54321`; необходим только публичный ключ. Представление появляется после `sql/logic.sql` на чистой базе или после миграции `20261113_stage6_expedition.sql` на существующей. Новые главы библиотеки открываются при 1, 5, 15 подтверждённых переводах; XP браузера и голоса Telegram не смешиваются.


## Браузерный ученик — authenticated RPC

Для этих вызовов необходим JWT пользователя Supabase Auth (включённый Anonymous Sign-In). API-ключ — только публичный publishable/anon, сервисный ключ в HTML не используется.

```http
POST /rest/v1/rpc/web_register
Authorization: Bearer <AUTH_JWT>
apikey: <PUBLIC_KEY>
Content-Type: application/json

{"p_nickname":"ЗвездаУрала","p_lang_pair":"ba-ru","p_join_code":null}
```

Также доступны: `web_profile()`; `web_next_fragment()`; `web_submit_answer(p_fragment_pair_id, p_action, p_text)`; `web_skip_fragment(p_fragment_pair_id)`. Во всех случаях внутренний `user_id` находится по `auth.uid()` в SQL, а не приходит из клиента.

Фронтенд вызывает эти RPC через `supabase-js` (`client.rpc()`), который автоматически добавляет JWT текущего сеанса. Публичные рейтинги `leaderboard_*` и `translations_export` читаются по публичному ключу, без авторизации.

## Периодные очки учеников

`leaderboard_users` дополнительно возвращает `day_points`, `week_points`, `month_points`, `year_points` по `Asia/Yekaterinburg`; `points` остаётся общим итогом за всё время. Миграция stage10 добавляет колонки без изменения ответов; stage11 настраивает search_path роли Auth для самостоятельного Compose.
# Проверка RC1

API-контракты сохранены. [Матрица и результаты](docs/QA.md), [PowerShell и обновление](docs/WINDOWS_SETUP.md). REST-экспорт содержит прежние семь полей; независимые Telegram/Web-профили используют общий механизм голосования, не объединённую учётную запись.
