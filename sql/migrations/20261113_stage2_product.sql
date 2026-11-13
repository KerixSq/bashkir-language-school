-- Применять после 20261113_stage1_fixes.sql, если база уже существует.
-- Повторный запуск не сбрасывает ответы, цели и серии.
begin;

alter table public.users add column if not exists last_goal_date date;
insert into public.config(key,value) values ('daily_goal','5')
on conflict(key) do nothing;

create or replace function private.goal_streak(p_user_id uuid)
returns integer language sql stable security invoker set search_path = '' as $$
  with goal_days as (
    select (a.created_at at time zone 'Asia/Yekaterinburg')::date as day
    from public.answers a where a.user_id = p_user_id
    group by 1
    having count(*) >= (select value::integer from public.config where key = 'daily_goal')
  ), today as (
    select (now() at time zone 'Asia/Yekaterinburg')::date as day
  ), anchor as (
    select case when exists(select 1 from goal_days g where g.day = t.day)
      then t.day else t.day - 1 end as day from today t
  ), numbered as (
    select g.day, row_number() over(order by g.day desc) as position
    from goal_days g where g.day <= (select day from anchor)
  )
  select count(*)::integer from numbered n cross join anchor a
  where n.day = a.day - (n.position::integer - 1);
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

  select private.goal_streak(p_user_id) into v_streak;
  if v_streak >= 3 then
    insert into public.user_badges(user_id,badge_code) values(p_user_id,'streak_3')
    on conflict do nothing;
  end if;
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
  v_goal integer;
  v_day date;
  v_today_count integer;
  v_goal_just_reached boolean;
begin
  -- Одна короткая критическая секция для пересчёта общих очков при конкурирующих ответах.
  perform pg_catalog.pg_advisory_xact_lock(75241309);
  select * into v_user from public.users where id=p_user_id for update;
  if not found then raise exception 'Пользователь не найден'; end if;
  if p_action not in ('confirm','correct') then
    raise exception 'Действие должно быть confirm или correct';
  end if;
  if exists(select 1 from public.answers where user_id=p_user_id
    and fragment_pair_id=p_fragment_pair_id) then
    return jsonb_build_object('duplicate',true, 'points',v_user.points,
      'level',v_user.level);
  end if;
  if v_user.current_fragment_pair_id is distinct from p_fragment_pair_id
    or v_user.current_shown_variant is null then
    raise exception 'Задание устарело. Используйте /task';
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

  v_day := (now() at time zone 'Asia/Yekaterinburg')::date;
  select value::integer into strict v_goal from public.config where key='daily_goal';
  select count(*) into v_today_count from public.answers
  where user_id=p_user_id and (created_at at time zone 'Asia/Yekaterinburg')::date=v_day;
  v_goal_just_reached := v_today_count = v_goal and
    v_user.last_goal_date is distinct from v_day;

  update public.users set points=points+v_points,
    level=1+(points+v_points)/v_step,
    last_active_date=v_day,
    last_goal_date=case when v_today_count >= v_goal then v_day else last_goal_date end,
    state='idle', current_fragment_pair_id=null, current_shown_variant=null
  where id=p_user_id;

  perform private.reconcile_fragment(p_fragment_pair_id);
  perform private.award_badges(p_user_id);

  select jsonb_build_object('points_awarded',a.points_awarded,
    'points',u.points,'level',u.level,'status',fp.status,
    'caught_planted_error',a.caught_planted_error,
    'correct_translation',case when a.shown_variant='bad' and a.action='confirm'
      then fp.auto_translation else null end,
    'final_translation',fp.final_translation,
    'daily_goal',v_goal, 'today_answers',v_today_count,
    'goal_just_reached',v_goal_just_reached,
    'goal_streak',private.goal_streak(p_user_id))
    into v_result
  from public.answers a join public.users u on u.id=a.user_id
    join public.fragment_pairs fp on fp.id=a.fragment_pair_id
  where a.id=v_answer_id;
  return v_result;
end;
$$;

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
    where a2.user_id=u.id and words.word<>''),0) as vocabulary,
  private.goal_streak(u.id) as goal_streak
from public.users u left join public.answers a on a.user_id=u.id
where u.role is not null
group by u.id;

revoke all on function private.goal_streak(uuid) from public, anon, authenticated;
grant usage on schema private to service_role;
grant execute on function private.goal_streak(uuid) to service_role;
revoke all on function public.submit_answer(uuid,uuid,text,text)
  from public, anon, authenticated;
grant execute on function public.submit_answer(uuid,uuid,text,text)
  to service_role;
revoke all on public.user_stats from public, anon, authenticated;
grant select on public.user_stats to service_role;
notify pgrst, 'reload schema';
commit;
