# Проверки и готовность

База консолидации: e90dd405e8e80f57cba1347107951c5e40d0df61. Проверенный код навигации: `165df8e31d8dcb923085b3afbfb1e1ec36b80291`. Полная история main → release-candidate → rc1-visual-polish присутствует; дополнительных merge/cherry-pick не требуется. Единственная рабочая ветка — rc1-visual-polish. Main не обновляется.

Предыдущий подтверждённый workflow: [43616817531](https://github.com/KerixSq/bashkir-language-school/actions/runs/43616817531). Это baseline, не доказательство новых изменений. Итоговые SHA и завершённый CI консолидации будут записаны после публикации. Статус до завершения нового workflow: IN PROGRESS.

## Исправления навигации

До правки воспроизведена последовательность learn → lessons → learn → lessons при колебаниях ±3 px. Упорядоченные границы теперь образуют непересекающиеся вертикальные диапазоны; одинаково расположенные колонки не конкурируют. Один passive scroll-listener и один requestAnimationFrame, гистерезис 12 px. При клике выбранный пункт удерживается до завершения программного скролла; wheel/touch/клавиатура/ручная прокрутка снимают удержание. Скрытые tabpanel не наблюдаются, выбранная вкладка определяется через openTab. Контекст меняется только при смене раздела/реальных данных. Дизайн, SQL, API и очки не менялись.

Новый тест проверяет последовательности при медленной прокрутке вниз/вверх, колебания, быстрые переходы, плавный переход и прерывание колесом, рейтинг → словарь → главная, mobile и рост контента. Повторное lessons → library → lessons при движении вниз допустимо: это три реальные последовательные области (тренировочная карта, библиотека, урок), а не возврат к прежней границе.

## Текущие проверки

| Проверка | Фактический результат |
|---|---|
| Новые навигационные сценарии Chromium/WebKit | PASS локально, desktop/mobile |
| compileall, unittest, контракт, Ruff | PASS локально, 154 unit-теста |
| Визуальные шесть ширин, TTS, original audio, mobile checkpoint | PASS локально: шесть ширин, Chromium/WebKit, реальные WAV/MP3 |
| PostgreSQL/aiogram/REST/RLS/эксперт | PASS: 12 PostgreSQL-сценариев, aiogram, эксперт, REST/RLS/doctor; отдельная QA-база |
| Docker локально | SKIP: daemon недоступен; полный изолированный стек проверяется CI |
| Live Telegram/Tor/direct через интернет | SKIP: реальных аккаунтов и доставки в этой задаче нет |
| Физические устройства, произношение/переводы носителем | SKIP: требуется человек |

## Матрица требований

| Требование | Реализация | Доказательство | Статус |
|---|---|---|---|
| Реальный текстовый корпус | Зафиксированные JSONL БГПУ, проверка хешей | Docker import, unit importer; CORPUS_PROVENANCE | PASS |
| Источники/координаты/происхождение | sources, phrasebook_rows, source в export | importer/PG integration, REST smoke | PASS |
| Аудио с таймкодами | WAV/MP3 + CSV/JSON, атомарный импорт | unit/PG, original audio browsers | PASS для конвейера |
| Подлинный аудиокорпус | Лицензированного речевого материала не добавлено | Явно технический тестовый тон | PARTIAL |
| Задания веб/Telegram | Auth/Web RPC, aiogram feed_update | browser/aiogram + Docker CI | PASS автоматически, Live SKIP |
| Подтверждение/исправление/пропуск | SQL submit_answer и обработчики | PG/aiogram: повторы/неверные/устаревшие действия | PASS |
| Подставные ошибки | Подстановка другого корпусного перевода | importer/unit, browser/aiogram | PARTIAL: эвристика, не гарантия языковой ошибки |
| Добровольные напоминания | on/off, Ufa, claim, default false | unit/PG concurrency/aiogram restart | PASS автоматически, доставка Live SKIP |
| Три независимых участника | SQL консенсус по пользователям | PG/aiogram, mixed-channel Docker CI | PASS |
| Нормализация/словарь | Правила и существующий synonym_map | unit/PG consensus | PASS в пределах правил, без семантической модели |
| Подсказки/экспертное решение | pg_trgm варианты/голоса/score, expert_resolve | browser_expert/PG, экспорт | PASS |
| Итог в БД/экспорт | confirmed, семь полей translations_export | PG/REST/browser CSV | PASS |
| Очки/уровни/достижения | Серверные и тренировочные механики раздельны | PG/aiogram/browser lesson | PASS |
| Периодные рейтинги | Серверные period points | PG integration | PASS |
| Карта/прогресс | Тренировочная карта + серверная библиотека | visual/mobile + adventure_progress | PASS |
| PostgreSQL/REST/Auth | Compose db/rest/auth/app | QA REST/RLS и CI Docker | PASS автоматически |
| Преподавательские отчёты | Защищённый отчёт и CSV | aiogram + Docker browser | PASS |
| Общая база Web/Telegram | Общие ответы/консенсус, разные профили | mixed-channel Docker CI | PASS; аккаунты не объединены |
| Работа offline CDN | Локальный Supabase JS/колода/WAV | visual/TTS при route.abort HTTPS | PASS для сайта; Telegram требует сеть |


## Документация и очистка

Было 51 отслеживаемый Markdown, осталось 19: четыре основных документа в корне, двенадцать в docs, руководство импорта и два документа происхождения ассетов/зависимости. Сохранены STUDENT_RESEARCH и GAMEPLAY, которые проверяет check_contract; LOCAL_WINDOWS для альтернативного CLI; TELEGRAM_LIVE_TEST для безопасной ручной проверки; IMPORT_GUIDE с условиями сторонних текстов; ART_NOTES и vendor/README. Сохранены все лицензии, CORPUS_PROVENANCE.json, SQL-миграции, фикстуры, исходники и графические ресурсы. Двадцать исходных фраз для носителя перенесены в CONTENT_AND_AUDIO без изменения текстов/переводов.

Установка и backup объединены в WINDOWS_SETUP; контент/TTS/оригинальное аудио/CSV — CONTENT_AND_AUDIO; Telegram/напоминания — TELEGRAM; эксперт — EXPERT_REVIEW; основной/резервный показ и вопросы жюри — DEMO; фактическая архитектура — ARCHITECTURE; текущие результаты — этот QA; история — RELEASE_NOTES. Промпты разработки и дублирующиеся промежуточные отчёты удалены из текущего дерева, но доступны в Git до e90dd40.

Удалённые Markdown (содержимое перенесено по назначению, устаревшие числа тестов не дублируются):

- `CODEX_ALL_IN_ONE.md`
- `PITCH_NOTES.md`
- `PROMPT_TRANSLATION.md`
- `README-BRAND-UPDATE.md`
- `START_HERE.md`
- `docs/ACADEMY_QA_REPORT.md`
- `docs/APP_DESIGN.md`
- `docs/BOT_FINAL_QA.md`
- `docs/BROWSER_FIRST.md`
- `docs/BROWSER_FIRST_CHANGES.md`
- `docs/BROWSER_FIRST_QA.md`
- `docs/CHANGES.md`
- `docs/CODEX_CONTINUATION_REPORT.md`
- `docs/CONTENT_FINAL_QA.md`
- `docs/CORPUS_AUDIT.md`
- `docs/DEMO_3_MINUTES.md`
- `docs/DEMO_BACKUP.md`
- `docs/DOCKER_WINDOWS.md`
- `docs/EXPERT_SIMILARITY.md`
- `docs/FINAL_CHECKPOINT_QA.md`
- `docs/FINAL_DEMO.md`
- `docs/FINAL_HACKATHON_QA.md`
- `docs/FINAL_RELEASE_QA.md`
- `docs/FINAL_WINDOWS_SETUP.md`
- `docs/HACKATHON_POLISH.md`
- `docs/JURY_POLISH.md`
- `docs/JURY_QA_REPORT.md`
- `docs/ORIGINAL_AUDIO.md`
- `docs/PRE_DEMO_REPORT.md`
- `docs/QA_REPORT.md`
- `docs/RELEASE_CHECKLIST.md`
- `docs/RELEASE_NOTES_v0.9.0-rc1.md`
- `docs/REMINDERS.md`
- `docs/STABILIZATION_REPORT.md`
- `docs/TELEGRAM_NAVIGATION.md`
- `docs/TTS.md`
- `docs/UI_FINAL_PASS.md`
- `docs/UX_REFERENCE.md`
- `docs/VISUAL_DESIGN.md`
- `docs/VISUAL_POLISH_QA.md`

Ссылки обновлены в README, AGENTS, API/SPEC, тематических документах и контрактном тесте наличия документов. Проверка контракта не ослаблена: CSV из четырёх полей и 20 реальных примеров проверяются регрессиями. Ссылка веб-интерфейса на API направлена в репозиторий, поскольку API.md не поставляется внутри Nginx web-root.

Отслеживаемых логов, видео, дампов БД и test-results не обнаружено; удалять их из Git не требовалось. PNG-оригинал Акбузата и SVG сохранены как полезные исходные иллюстрации/проверяемые ассеты. .gitignore дополнен локальными dump/backup/video/cache-артефактами, исходники и фикстуры не игнорируются. Срок хранения новых CI-свидетельств — 14 дней; история workflow и уже существующие артефакты не удаляются.

## Ограничения и защита

Семантической модели синонимов и P2-объединения аккаунтов нет. Текстовое сходство не доказывает смысл. 40 TTS WAV не покрывают всю колоду; носитель не оценивал произношение. Подлинный лицензированный исходный аудиокорпус не добавлен — тестовый тон маркирован технической фикстурой. MP3 локально проверяется с имеющимися FFmpeg/ffprobe; в CI без них явно SKIP. Анонимный Auth-профиль может потеряться после очистки хранилища; сговор аккаунтов полностью не исключён. Напоминание резервирует одну попытку в день, не exactly-once доставку. Проверки RLS не являются внешним пентестом.

Скриншоты/видео — test-results/visual, visual-polish/after и checkpoint; в CI interface-screenshots и original-audio-evidence. Автоматические Telegram Updates с подменённым transport — не Live E2E. Для защиты на конкретном ноутбуке нужен ручной проход из [WINDOWS_SETUP](WINDOWS_SETUP.md), [DEMO](DEMO.md) и при необходимости [TELEGRAM_LIVE_TEST](TELEGRAM_LIVE_TEST.md). Работающие данные и volumes не изменялись; SQL, формулы, API, .env.docker и секреты не трогали.
