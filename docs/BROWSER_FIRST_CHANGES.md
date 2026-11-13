# Что изменилось в браузерной версии

- Веб теперь основной канал: реальная серверная проверка переводов, профиль, очки, серии и рейтинг доступны в `web/index.html`.
- Telegram продолжает использовать прежнюю схему и остаётся альтернативным клиентом.
- Отдельные тренировочные упражнения по колоде JSONL сохранились, но их XP не участвуют в согласовании и рейтингах.
- Добавлена `sql/migrations/20261113_stage8_browser_first.sql` для ранее созданной PostgreSQL.
- `sql/schema.sql` и `sql/logic.sql` синхронизированы с миграцией для чистого развёртывания.
- Браузерная идентичность создаётся через Supabase Auth Anonymous Sign-In; `SECURITY DEFINER` RPC получают `user_id` только из `auth.uid()`.
- RLS и прямые запреты чтения персональных таблиц не ослаблены.
- Подключены запрошенные CDN: Tailwind Play, Google Fonts Nunito/Manrope, Font Awesome solid, GSAP/ScrollTrigger, Lenis.
- Анимация отключается при `prefers-reduced-motion`; кнопки магнитятся только при мыши и доступном GSAP.
- Обновлены README, API.md, Windows setup, статический контракт и unit-тесты.
