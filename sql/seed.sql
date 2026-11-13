-- 02. Справочники. Запускать после schema.sql.
insert into public.lang_pairs(code,name) values
 ('ba-ru','Башкирский — русский'),
 ('ba-en','Башкирский — английский'),
 ('ba-kk','Башкирский — казахский')
on conflict(code) do nothing;

insert into public.config(key,value) values
 ('min_votes','3'),
 ('consensus_share','0.6'),
 ('expert_after_votes','5'),
 ('points_per_answer','10'),
 ('bonus_catch_error','15'),
 ('bonus_match_consensus','5'),
 ('level_step','100'),
 ('bad_variant_probability','0.2'),
 ('daily_goal','5')
on conflict(key) do nothing;

insert into public.badges(code,title,description) values
 ('first_answer','Первый шаг','Отправить первый ответ'),
 ('ten_answers','Десять ответов','Ответить на 10 заданий'),
 ('error_hunter','Охотник за ошибками','Поймать 5 подставных ошибок'),
 ('streak_3','Три дня подряд','Отвечать 3 дня подряд (по времени Уфы)'),
 ('corrector','Редактор','Исправить 10 переводов')
on conflict(code) do nothing;

select (select count(*) from public.lang_pairs) as lang_pairs,
       (select count(*) from public.config) as config,
       (select count(*) from public.badges) as badges;

insert into public.config(key,value) values
 ('daily_points_cap','150'),('min_answer_seconds','2'),('answer_interval_seconds','2'),
 ('vote_weight_step','0.1'),('vote_weight_min','0.5'),('vote_weight_max','1.5'),
 ('reminder_hour','18'),('teacher_invite_code',''),('expert_access_hash','')
on conflict(key) do nothing;
