-- Миграция для базы, где уже выполнены schema.sql, seed.sql и logic.sql.
-- Повторный запуск не перевыпускает коды классов и не стирает ответы.
begin;

-- Старые преподаватели подтверждали роль без секретного кода.
-- При первом запуске миграции им нужно повторно ввести teacher_code.
do $$
begin
  if not exists (
    select 1 from information_schema.columns
    where table_schema='public' and table_name='classes'
      and column_name='teacher_code'
  ) then
    update public.users set class_id=null, state='joining_class',
      current_fragment_pair_id=null, current_shown_variant=null
    where role='teacher' and class_id is not null;
  end if;
end;
$$;

alter table public.users add column if not exists nickname text;
alter table public.users drop constraint if exists users_state_check;
alter table public.users add constraint users_state_check check
  (state in ('idle','choosing_nickname','choosing_role','joining_class',
    'choosing_pair','awaiting_correction'));
alter table public.users drop constraint if exists users_nickname_check;
alter table public.users add constraint users_nickname_check check
  (nickname is null or (char_length(nickname) between 3 and 20
    and nickname ~ '^[[:alnum:] _-]+$'));

-- Прежние Telegram-имена не переносятся в публичный никнейм.
update public.users
set nickname='Участник ' || upper(substr(replace(gen_random_uuid()::text,'-',''),1,6))
where nickname is null;

alter table public.classes add column if not exists teacher_code text;
update public.classes
set teacher_code=case
  when length(join_code) between 20 and 128
    and join_code ~ '^[A-Za-z0-9_-]+$' then join_code
  else replace(gen_random_uuid()::text,'-','') || replace(gen_random_uuid()::text,'-','')
end
where teacher_code is null;

-- Алфавит без O, 0, I, 1. Случайные коды не меняются при повторной миграции.
do $$
declare
  v_class record;
  v_code text;
  v_uuid uuid;
  v_alphabet constant text := 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789';
  i integer;
begin
  for v_class in select id from public.classes
    where join_code !~ '^[A-HJ-NP-Z2-9]{6,8}$'
  loop
    loop
      v_uuid := gen_random_uuid();
      v_code := '';
      for i in 0..7 loop
        v_code := v_code || substr(v_alphabet,
          1 + get_byte(decode(replace(v_uuid::text,'-',''),'hex'),i)
            % length(v_alphabet),1);
      end loop;
      exit when not exists (select 1 from public.classes where join_code=v_code);
    end loop;
    update public.classes set join_code=v_code where id=v_class.id;
  end loop;
end;
$$;

alter table public.classes alter column teacher_code set not null;
alter table public.classes drop constraint if exists classes_short_join_code_check;
alter table public.classes add constraint classes_short_join_code_check
  check (join_code ~ '^[A-HJ-NP-Z2-9]{6,8}$');
alter table public.classes drop constraint if exists classes_teacher_code_format_check;
alter table public.classes add constraint classes_teacher_code_format_check
  check (teacher_code ~ '^[A-Za-z0-9_-]{20,128}$');
create unique index if not exists ux_classes_teacher_code
  on public.classes(teacher_code);

update public.users u
set last_active_date=(select max((a.created_at at time zone 'Asia/Yekaterinburg')::date)
                      from public.answers a where a.user_id=u.id)
where exists (select 1 from public.answers a where a.user_id=u.id);

-- Старое представление содержит user_id: заменить определение без него
-- через CREATE OR REPLACE VIEW в PostgreSQL нельзя.
drop view if exists public.leaderboard_users;
drop function if exists public.get_class_report(text);

-- Логика базы. Для новой установки: schema.sql, seed.sql, logic.sql.

create or replace function private.normalize_translation(p_text text)
returns text language sql immutable set search_path = '' as $$
  select pg_catalog.lower(pg_catalog.btrim(
    pg_catalog.regexp_replace(
      pg_catalog.regexp_replace(coalesce(p_text,''), '[[:space:]]+', ' ', 'g'),
      '^[[:punct:]«»„“” ]+|[[:punct:]«»„“” ]+$', '', 'g'
    )
  ));
$$;

create or replace function private.award_badges(p_user_id uuid)
returns void language plpgsql security invoker set search_path = '' as $$
declare
  v_count integer;
  v_correct integer;
  v_caught integer;
  v_streak integer;
begin
  select count(*), count(*) filter (where action='correct'),
    count(*) filter (where caught_planted_error)
  into v_count, v_correct, v_caught
  from public.answers where user_id=p_user_id;

  if v_count >= 1 then
    insert into public.user_badges(user_id,badge_code) values(p_user_id,'first_answer')
    on conflict do nothing;
  end if;
  if v_count >= 10 then
    insert into public.user_badges(user_id,badge_code) values(p_user_id,'ten_answers')
    on conflict do nothing;
  end if;
  if v_caught >= 5 then
    insert into public.user_badges(user_id,badge_code) values(p_user_id,'error_hunter')
    on conflict do nothing;
  end if;
  if v_correct >= 10 then
    insert into public.user_badges(user_id,badge_code) values(p_user_id,'corrector')
    on conflict do nothing;
  end if;

  select count(distinct (created_at at time zone 'Asia/Yekaterinburg')::date)
  into v_streak from public.answers where user_id=p_user_id
    and (created_at at time zone 'Asia/Yekaterinburg')::date between
      (now() at time zone 'Asia/Yekaterinburg')::date - 2
      and (now() at time zone 'Asia/Yekaterinburg')::date;
  if v_streak = 3 then
    insert into public.user_badges(user_id,badge_code) values(p_user_id,'streak_3')
    on conflict do nothing;
  end if;
end;
$$;

create or replace function private.reconcile_fragment(p_pair_id uuid)
returns void language plpgsql security invoker set search_path = '' as $$
declare
  v_total integer;
  v_leader text;
  v_votes integer;
  v_final text;
  v_auto text;
  v_confirmed boolean;
  v_min integer;
  v_share numeric;
  v_after integer;
  v_bonus integer;
  v_base integer;
  v_catch integer;
  v_step integer;
  v_target integer;
  v_delta integer;
  v_answer record;
begin
  select value::integer into strict v_min from public.config where key='min_votes';
  select value::numeric into strict v_share from public.config where key='consensus_share';
  select value::integer into strict v_after from public.config where key='expert_after_votes';
  select value::integer into strict v_bonus from public.config where key='bonus_match_consensus';
  select value::integer into strict v_base from public.config where key='points_per_answer';
  select value::integer into strict v_catch from public.config where key='bonus_catch_error';
  select value::integer into strict v_step from public.config where key='level_step';
  select auto_translation into strict v_auto from public.fragment_pairs where id=p_pair_id;

  select count(*) into v_total from public.answers
  where fragment_pair_id=p_pair_id
    and not (shown_variant='bad' and action='confirm');

  select answer_norm, count(*) into v_leader, v_votes
  from public.answers
  where fragment_pair_id=p_pair_id
    and not (shown_variant='bad' and action='confirm')
  group by answer_norm order by count(*) desc, answer_norm collate "C" limit 1;

  v_confirmed := v_total >= v_min and v_votes::numeric/nullif(v_total,0) >= v_share;
  if v_confirmed then
    if v_leader = private.normalize_translation(v_auto) then
      v_final := v_auto;
    else
      select btrim(answer_text) into v_final from public.answers
      where fragment_pair_id=p_pair_id and action='correct'
        and answer_norm=v_leader and answer_text is not null
      group by btrim(answer_text)
      order by count(*) desc, btrim(answer_text) collate "C" limit 1;
    end if;
    if v_final is null then
      raise exception 'Не найден оригинальный текст победившего исправления';
    end if;
    update public.fragment_pairs set status='confirmed',
      final_translation=v_final, confirmed_count=v_votes where id=p_pair_id;
  elsif v_total >= v_after then
    update public.fragment_pairs set status='expert_review',
      final_translation=null, confirmed_count=0 where id=p_pair_id;
  else
    update public.fragment_pairs set status='collecting',
      final_translation=null, confirmed_count=0 where id=p_pair_id;
  end if;

  -- Восстанавливаем бонусы при смене лидера, а не выдаём их навсегда первому лидеру.
  for v_answer in
    select id, user_id, action, shown_variant, answer_norm,
      caught_planted_error, points_awarded
    from public.answers where fragment_pair_id=p_pair_id
    order by user_id
  loop
    v_target := case
      when v_answer.shown_variant='bad' and v_answer.action='confirm' then 0
      else v_base + case when v_answer.caught_planted_error then v_catch else 0 end
    end;
    if v_confirmed and v_answer.answer_norm=v_leader
      and not (v_answer.shown_variant='bad' and v_answer.action='confirm') then
      v_target := v_target + v_bonus;
    end if;
    v_delta := v_target - v_answer.points_awarded;
    if v_delta <> 0 then
      update public.answers set points_awarded=v_target where id=v_answer.id;
      update public.users set points=points+v_delta,
        level=1+(points+v_delta)/v_step where id=v_answer.user_id;
    end if;
  end loop;
end;
$$;

create or replace function public.get_next_fragment(p_user_id uuid)
returns jsonb language plpgsql security invoker set search_path = '' as $$
declare
  v_user public.users%rowtype;
  v_pair public.fragment_pairs%rowtype;
  v_variant text;
  v_bad_probability numeric;
  v_result jsonb;
begin
  select * into v_user from public.users where id=p_user_id for update;
  if not found then raise exception 'Пользователь не найден'; end if;
  if v_user.role is null or v_user.lang_pair is null
    or v_user.class_id is null or v_user.nickname is null then
    raise exception 'Завершите регистрацию через /start';
  end if;
  if v_user.state='awaiting_correction' then
    raise exception 'Сначала отправьте исправление или /cancel';
  end if;

  if v_user.current_fragment_pair_id is not null
     and v_user.current_shown_variant is not null then
    select * into v_pair from public.fragment_pairs
      where id=v_user.current_fragment_pair_id;
    v_variant := v_user.current_shown_variant;
  else
    -- Подтверждённые переводы тоже можно проверять новым участникам.
    select fp.* into v_pair from public.fragment_pairs fp
    where fp.lang_pair=v_user.lang_pair and fp.status in ('collecting','confirmed')
      and not exists (select 1 from public.answers a
        where a.user_id=p_user_id and a.fragment_pair_id=fp.id)
    order by random() limit 1;
    if not found then return null; end if;

    select value::numeric into strict v_bad_probability from public.config
      where key='bad_variant_probability';
    v_variant := case when v_pair.bad_translation is not null
       and random() < v_bad_probability then 'bad' else 'auto' end;
    update public.users set current_fragment_pair_id=v_pair.id,
      current_shown_variant=v_variant where id=p_user_id;
  end if;

  select jsonb_build_object(
    'fragment_pair_id', v_pair.id,
    'text_ba', f.text_ba,
    'translation', case when v_variant='bad'
       then v_pair.bad_translation else v_pair.auto_translation end,
    'lang_pair', v_pair.lang_pair,
    'source', s.title
  ) into v_result
  from public.fragments f join public.sources s on s.id=f.source_id
  where f.id=v_pair.fragment_id;
  return v_result;
end;
$$;

create or replace function public.submit_answer(
  p_user_id uuid, p_fragment_pair_id uuid, p_action text, p_text text default null
) returns jsonb language plpgsql security invoker set search_path = '' as $$
declare
  v_user public.users%rowtype;
  v_pair public.fragment_pairs%rowtype;
  v_variant text;
  v_norm text;
  v_shown text;
  v_caught boolean;
  v_base integer;
  v_catch integer;
  v_step integer;
  v_points integer;
  v_answer_id uuid;
  v_result jsonb;
begin
  -- Одна короткая критическая секция для пересчёта общих очков при конкурирующих ответах.
  perform pg_catalog.pg_advisory_xact_lock(75241309);
  select * into v_user from public.users where id=p_user_id for update;
  if not found then raise exception 'Пользователь не найден'; end if;
  if p_action not in ('confirm','correct') then
    raise exception 'Действие должно быть confirm или correct';
  end if;
  if v_user.current_fragment_pair_id is distinct from p_fragment_pair_id
    or v_user.current_shown_variant is null then
    raise exception 'Задание устарело. Используйте /task';
  end if;
  if exists(select 1 from public.answers where user_id=p_user_id
    and fragment_pair_id=p_fragment_pair_id) then
    raise exception 'Вы уже отвечали на этот фрагмент';
  end if;
  select * into v_pair from public.fragment_pairs
    where id=p_fragment_pair_id for update;
  if not found then raise exception 'Фрагмент не найден'; end if;

  v_variant := v_user.current_shown_variant;
  v_shown := case when v_variant='bad' then v_pair.bad_translation
    else v_pair.auto_translation end;
  if v_shown is null then raise exception 'Вариант перевода не найден'; end if;

  if p_action='correct' then
    if v_user.state <> 'awaiting_correction' then
      raise exception 'Сначала нажмите кнопку «Исправить»';
    end if;
    if p_text is null or length(btrim(p_text))=0 or length(p_text)>500 then
      raise exception 'Исправление должно быть от 1 до 500 символов';
    end if;
    v_norm := private.normalize_translation(p_text);
    if v_norm='' or v_norm=private.normalize_translation(v_shown) then
      raise exception 'Исправление не должно совпадать с показанным текстом';
    end if;
  else
    if v_user.state='awaiting_correction' then
      raise exception 'Выберите /cancel или отправьте исправление';
    end if;
    v_norm := private.normalize_translation(v_pair.auto_translation);
  end if;

  v_caught := (v_variant='bad' and p_action='correct');
  select value::integer into strict v_base from public.config where key='points_per_answer';
  select value::integer into strict v_catch from public.config where key='bonus_catch_error';
  select value::integer into strict v_step from public.config where key='level_step';
  v_points := case when v_variant='bad' and p_action='confirm' then 0
    else v_base + case when v_caught then v_catch else 0 end end;

  insert into public.answers(user_id,fragment_pair_id,shown_variant,
    action,answer_text,answer_norm,caught_planted_error,points_awarded)
  values(p_user_id,p_fragment_pair_id,v_variant,p_action,
    case when p_action='correct' then btrim(p_text) else null end,
    v_norm,v_caught,v_points)
  returning id into v_answer_id;

  update public.users set points=points+v_points,
    level=1+(points+v_points)/v_step,
    last_active_date=(now() at time zone 'Asia/Yekaterinburg')::date,
    state='idle', current_fragment_pair_id=null, current_shown_variant=null
  where id=p_user_id;

  perform private.reconcile_fragment(p_fragment_pair_id);
  perform private.award_badges(p_user_id);

  select jsonb_build_object('points_awarded',a.points_awarded,
    'points',u.points,'level',u.level,'status',fp.status,
    'caught_planted_error',a.caught_planted_error,
    'correct_translation',case when a.shown_variant='bad' and a.action='confirm'
      then fp.auto_translation else null end,
    'final_translation',fp.final_translation)
    into v_result
  from public.answers a join public.users u on u.id=a.user_id
    join public.fragment_pairs fp on fp.id=a.fragment_pair_id
  where a.id=v_answer_id;
  return v_result;
end;
$$;

-- Отчёт открывает только отдельный секрет преподавателя, не код входа ученика.
create or replace function public.get_class_report(p_teacher_code text)
returns jsonb language plpgsql stable security definer set search_path = '' as $$
declare
  v_class public.classes%rowtype;
  v_school text;
  v_students integer;
  v_answers integer;
  v_errors numeric;
  v_top jsonb;
  v_days jsonb;
begin
  if p_teacher_code is null or length(p_teacher_code) not between 20 and 128 then
    raise exception 'Неверный код преподавателя';
  end if;
  select * into v_class from public.classes where teacher_code=p_teacher_code;
  if not found then raise exception 'Класс не найден'; end if;
  select name into v_school from public.schools where id=v_class.school_id;
  select count(*) into v_students from public.users
    where class_id=v_class.id and role='student';
  select count(*), coalesce(round(100.0*count(*) filter
    (where a.shown_variant='bad' and a.action='confirm')
    /nullif(count(*),0),2),0)
    into v_answers,v_errors
  from public.answers a join public.users u on u.id=a.user_id
  where u.class_id=v_class.id and u.role='student';

  select coalesce(jsonb_agg(to_jsonb(t)), '[]'::jsonb) into v_top
  from (select u.nickname as name, u.points, u.level, count(a.id) as answers
     from public.users u left join public.answers a on a.user_id=u.id
     where u.class_id=v_class.id and u.role='student'
     group by u.id order by u.points desc, count(a.id) desc, u.nickname limit 10) t;

  select coalesce(jsonb_agg(to_jsonb(d) order by d.day),'[]'::jsonb)
    into v_days from (
      select (a.created_at at time zone 'Asia/Yekaterinburg')::date as day,
        count(*) as answers
      from public.answers a join public.users u on u.id=a.user_id
      where u.class_id=v_class.id and u.role='student'
      group by (a.created_at at time zone 'Asia/Yekaterinburg')::date
      order by day desc limit 30
    ) d;
  return jsonb_build_object('school',v_school,'class',v_class.name,
    'students_count',v_students,'answers_count',v_answers,
    'error_rate',v_errors,'top_students',v_top,'activity',v_days);
end;
$$;

-- Публичный экспорт: семь фиксированных колонок.
create or replace view public.translations_export
with (security_barrier=true) as
select f.id as fragment_id, f.text_ba, fp.lang_pair,
  coalesce(fp.final_translation,fp.auto_translation) as translation,
  concat_ws(' · ',s.title,
    case when nullif(f.chapter,'') is not null then 'глава '||f.chapter end,
    'позиция '||f.position::text,
    case when f.time_start is not null then
      'сек. '||f.time_start::text||'–'||f.time_end::text end) as source,
  (fp.status='confirmed') as confirmed, fp.status
from public.fragment_pairs fp join public.fragments f on f.id=fp.fragment_id
join public.sources s on s.id=f.source_id;

create or replace view public.expert_review_queue
with (security_barrier=true) as
select fp.id as fragment_pair_id, f.text_ba, fp.lang_pair,
  fp.auto_translation, fp.status,
  (select count(*) from public.answers a where a.fragment_pair_id=fp.id
    and not (a.shown_variant='bad' and a.action='confirm')) as votes
from public.fragment_pairs fp join public.fragments f on f.id=fp.fragment_id
where fp.status='expert_review';

-- UUID и служебные поля доступны только серверу.
create or replace view public.user_stats
with (security_barrier=true) as
select u.id as user_id, u.nickname, u.role, u.points, u.level,
  count(a.id) as total_answers,
  count(a.id) filter (where a.created_at >=
    date_trunc('day',now() at time zone 'Asia/Yekaterinburg') at time zone 'Asia/Yekaterinburg') as day_answers,
  count(a.id) filter (where a.created_at >=
    date_trunc('week',now() at time zone 'Asia/Yekaterinburg') at time zone 'Asia/Yekaterinburg') as week_answers,
  count(a.id) filter (where a.created_at >=
    date_trunc('month',now() at time zone 'Asia/Yekaterinburg') at time zone 'Asia/Yekaterinburg') as month_answers,
  count(a.id) filter (where a.created_at >=
    date_trunc('year',now() at time zone 'Asia/Yekaterinburg') at time zone 'Asia/Yekaterinburg') as year_answers,
  count(a.id) filter (where a.action='correct') as corrections,
  count(a.id) filter (where a.shown_variant='bad' and a.action='confirm') as errors,
  coalesce(round(100.0*count(a.id) filter
    (where a.shown_variant='bad' and a.action='confirm')
    /nullif(count(a.id),0),2),0) as error_rate,
  coalesce((select count(distinct words.word)
    from public.answers a2
    join public.fragment_pairs fp on fp.id=a2.fragment_pair_id
    join public.fragments f on f.id=fp.fragment_id
    cross join lateral regexp_split_to_table(lower(f.text_ba),'[^[:alpha:]]+') as words(word)
    where a2.user_id=u.id and words.word<>''),0) as vocabulary
from public.users u left join public.answers a on a.user_id=u.id
where u.role is not null
group by u.id;

create or replace view public.leaderboard_users
with (security_barrier=true) as
select nickname as name, points, level, total_answers, day_answers,
  week_answers, month_answers, year_answers, corrections, errors,
  error_rate, vocabulary
from public.user_stats where role='student' and nickname is not null;

create or replace view public.leaderboard_schools
with (security_barrier=true) as
select s.id as school_id, s.name,
  count(distinct u.id) as users_count,
  coalesce(sum(a.points_awarded),0) as points,
  coalesce(sum(a.points_awarded) filter (where a.created_at >=
    date_trunc('day',now() at time zone 'Asia/Yekaterinburg') at time zone 'Asia/Yekaterinburg'),0) as day_points,
  coalesce(sum(a.points_awarded) filter (where a.created_at >=
    date_trunc('week',now() at time zone 'Asia/Yekaterinburg') at time zone 'Asia/Yekaterinburg'),0) as week_points,
  coalesce(sum(a.points_awarded) filter (where a.created_at >=
    date_trunc('month',now() at time zone 'Asia/Yekaterinburg') at time zone 'Asia/Yekaterinburg'),0) as month_points,
  coalesce(sum(a.points_awarded) filter (where a.created_at >=
    date_trunc('year',now() at time zone 'Asia/Yekaterinburg') at time zone 'Asia/Yekaterinburg'),0) as year_points
from public.schools s left join public.classes c on c.school_id=s.id
left join public.users u on u.class_id=c.id and u.role='student'
left join public.answers a on a.user_id=u.id
group by s.id;

create or replace view public.leaderboard_classes
with (security_barrier=true) as
select c.id as class_id, c.name, s.name as school,
  count(distinct u.id) as users_count,
  coalesce(sum(a.points_awarded),0) as points,
  coalesce(sum(a.points_awarded) filter (where a.created_at >=
    date_trunc('day',now() at time zone 'Asia/Yekaterinburg') at time zone 'Asia/Yekaterinburg'),0) as day_points,
  coalesce(sum(a.points_awarded) filter (where a.created_at >=
    date_trunc('week',now() at time zone 'Asia/Yekaterinburg') at time zone 'Asia/Yekaterinburg'),0) as week_points,
  coalesce(sum(a.points_awarded) filter (where a.created_at >=
    date_trunc('month',now() at time zone 'Asia/Yekaterinburg') at time zone 'Asia/Yekaterinburg'),0) as month_points,
  coalesce(sum(a.points_awarded) filter (where a.created_at >=
    date_trunc('year',now() at time zone 'Asia/Yekaterinburg') at time zone 'Asia/Yekaterinburg'),0) as year_points
from public.classes c join public.schools s on s.id=c.school_id
left join public.users u on u.class_id=c.id and u.role='student'
left join public.answers a on a.user_id=u.id
group by c.id,s.name;

revoke all on function private.normalize_translation(text),
  private.award_badges(uuid), private.reconcile_fragment(uuid),
  public.get_next_fragment(uuid),
  public.submit_answer(uuid,uuid,text,text),
  public.get_class_report(text) from public, anon, authenticated;
grant usage on schema private to service_role;
grant execute on function private.normalize_translation(text),
  private.award_badges(uuid), private.reconcile_fragment(uuid),
  public.get_next_fragment(uuid), public.submit_answer(uuid,uuid,text,text),
  public.get_class_report(text) to service_role;
grant execute on function public.get_class_report(text) to anon;

revoke all on public.translations_export, public.expert_review_queue,
  public.user_stats, public.leaderboard_users,
  public.leaderboard_classes, public.leaderboard_schools
  from public, anon, authenticated;
grant select on public.translations_export, public.leaderboard_users,
  public.leaderboard_classes, public.leaderboard_schools to anon;
grant select on public.translations_export, public.expert_review_queue,
  public.user_stats, public.leaderboard_users, public.leaderboard_classes,
  public.leaderboard_schools to service_role;

notify pgrst, 'reload schema';

-- Обновляем ранее подтверждённые переводы, начисления и текущих лидеров.
do $$
declare
  v_pair record;
begin
  for v_pair in select distinct fragment_pair_id as id from public.answers loop
    perform private.reconcile_fragment(v_pair.id);
  end loop;
end;
$$;

-- Закрываем наследованные права, если база ранее настраивалась вручную.
revoke all on public.user_stats from public, anon, authenticated;
revoke all on public.leaderboard_users from public, anon, authenticated;
grant select on public.leaderboard_users to anon, service_role;
grant select on public.user_stats to service_role;

commit;
