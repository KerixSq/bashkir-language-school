# Final release candidate 1 — 2026-11-14

Статус локального аудита: **READY WITH LIMITATIONS**. RC становится проверенной сборкой только при завершённом успешном workflow указанного SHA. База main: `0838c1a2ea8b372177b5e2c9aabe8cf26cb503b8`, [успешный baseline CI](https://github.com/KerixSq/bashkir-language-school/actions/runs/43610295143). Проверенный код RC: `5cd5c75d64bf1bc73e821cf9c5a1d5b05b8a8b2c`; последующий коммит меняет только документацию. SHA всей сборки и её CI: [Actions release-candidate](https://github.com/KerixSq/bashkir-language-school/actions?query=branch%3Arelease-candidate); открывайте run и проверяйте head_sha и conclusion=success. Main не изменяется, тег не создаётся.

## Подтверждённые исправления

1. На реальных обработчиках Dispatcher.feed_update и отдельной QA PostgreSQL воспроизведено сохранение `/unknown_command` как перевода при awaiting_correction. Регрессия до исправления: FAIL `Unknown command submitted as answer`; после: PASS, состояние/очки/назначенный фрагмент сохранены, запись ответа отсутствует. Изменён только fallback неизвестных команд, SQL и начисления не затронуты.
2. По реальному скриншоту expert-1440 обнаружен устаревший onboarding «Получи код класса» как обязательный первый шаг. Теперь самостоятельный путь явно доступен, код необязателен, /join объяснён. Дизайн не заменялся.
3. Исправлены инструкции обновления, пропускавшие вторую stage11 и stage12–14. Команды импорта используют --no-deps, чтобы импорт не запускал polling/Tor. Восстановлена единая актуальная точка входа документации.

## Реально выполненные проверки

| Проверка | Результат |
|---|---|
| compileall bot/scripts/tests | PASS |
| unittest discover | PASS, 151 тест |
| check_contract | PASS, семь полей экспорта и контракты сохранены |
| Ruff check/format | PASS после форматирования регрессионного теста |
| PostgreSQL integration | PASS, 12 тестов в disposable БД: голоса, повторное начисление, период, эксперт, аудио, напоминания |
| Aiogram integration | PASS, QA PostgreSQL/PostgREST + реальные обработчики + подменённый transport; оба вида регистрации, /join, меню, вклад, преподавательский CSV, три голоса, FSM/restart, remind on/off |
| REST smoke, check_rls, doctor | PASS на QA, временные записи smoke очищены, закрытые таблицы недоступны anon |
| Экспертное согласование через браузер/API | PASS на QA: варианты → решение → export |
| Visual Chromium | PASS на 360, 390, 768, 1024, 1440, 1920: CDN отключён, длинный текст, фокус, overflow, урок |
| Mobile Chromium Pixel 7 / WebKit iPhone 13 | PASS: пять упражнений, ошибочный ответ, WAV, завершение, карта, профиль, localStorage после reload, клавиатура/ошибка сети |
| TTS Chromium | PASS: настоящие WAV, pause/stop/next/close, 404/retry, отсутствующая запись/manifest, без русского browser voice |
| Original audio Chromium/WebKit | PASS локально: PCM WAV и MP3, Range, клавиатура, остановка, отмена, unsafe URL; используются имеющиеся FFmpeg/ffprobe |
| Docker локально | SKIP: dockerDesktopLinuxEngine pipe отсутствует; никаких volumes не меняли |
| Docker CI | Проверяется workflow RC: свежий PostgreSQL/Auth/PostgREST/Nginx, настоящий корпус, три независимых голоса двух каналов, экспорт, restart, expert, audio, aiogram/reminders. Baseline main PASS; это не подмена результата RC |
| Live Telegram, Tor/direct через интернет | SKIP: реальных сообщений/аккаунтов не использовали. Ручной чек-лист в FINAL_WINDOWS_SETUP |
| Физические телефоны, оценка носителем, восстановление backup на Windows | SKIP: требуется отдельная ручная проверка |

Снимки: `test-results/visual/` (home/lesson/finish/expert/zoom по ширинам). Просмотрены мобильная home-390 и desktop expert-1440; после изменения повторены visual/mobile. Видео настоящего локального урока: `test-results/checkpoint/chromium-mobile.webm`, `webkit-mobile.webm`. Это не видео live Telegram/серверного консенсуса. В CI — interface-screenshots и original-audio-evidence. Локальные журналы в work: rc1-integration.log, rc1-reproduce.log (ожидаемый FAIL до исправления), rc1-fixed-integration.log (PASS). Артефакты/логи не содержат публикуемых реальных токенов.

## Матрица требований

Основа — требования пользователя и действующие SPEC/API; формальная лингвистическая экспертиза не выполнялась.

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

## Изменённые файлы RC1

- Код: bot/handlers/messages.py, web/index.html.
- Регрессия: tests/bot_integration.py.
- Обновлены README.md, SPEC.md, API.md, docs/DOCKER_WINDOWS.md, docs/TELEGRAM_NAVIGATION.md, docs/DEMO_3_MINUTES.md.
- Добавлены docs/FINAL_WINDOWS_SETUP.md, docs/FINAL_DEMO.md, docs/DEMO_BACKUP.md, docs/FINAL_RELEASE_QA.md, docs/RELEASE_NOTES_v0.9.0-rc1.md.

Новых SQL-миграций/сервисов/зависимостей нет. Формулы очков и SQL-консенсус, .env.docker, рабочие данные/volumes не изменялись. Обе stage11 имеют разное назначение; нельзя ограничиться auth_search_path или сортировать миграции лексикографически. Обновление конкретной старой базы не запускалось вслепую; её фактическую версию надо подтвердить перед выбором суффикса миграций.

## Запуск и ограничения

Точные PowerShell-команды установки, резервной копии, миграций и диагностики: [FINAL_WINDOWS_SETUP.md](FINAL_WINDOWS_SETUP.md). [Трёхминутный сценарий](FINAL_DEMO.md), [резервный](DEMO_BACKUP.md), [release notes](RELEASE_NOTES_v0.9.0-rc1.md).

Напоминания резервируют одну попытку/день, не обещают exactly-once доставку. Текстовое сходство не доказывает семантическую эквивалентность. 40 TTS-записей не покрывают всю колоду; носитель не оценивал произношение. В CI MP3 имеет SKIP без ffprobe, локально проверен. P2-связки аккаунтов нет. Безопасность подтверждена проверками RLS/контрактов, не внешним пентестом. Для окончательной живой защиты необходим ручной Telegram-чек-лист и проверка запуска на ноутбуке выступающего.
