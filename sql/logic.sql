-- Логика базы. Для новой установки: schema.sql, seed.sql, logic.sql.


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


-- Отчёт открывает только отдельный секрет преподавателя, не код входа ученика.


-- Публичный экспорт: семь фиксированных колонок.
create or replace view public.translations_export with (security_barrier=true) as
select f.id as fragment_id,f.text_ba,fp.lang_pair,
 coalesce(fp.final_translation,fp.auto_translation) as translation,
 concat_ws(' · ',s.title,
  case when nullif(f.chapter,'') is not null then 'глава '||f.chapter end,
  'позиция '||f.position::text,
  case when f.time_start is not null then
   'сек. '||f.time_start::text||'–'||f.time_end::text end) as source,
 case when fp.status='confirmed' then fp.confirmed_count else 0 end as confirmed,
 fp.status
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
    where a2.user_id=u.id and words.word<>''),0) as vocabulary,
  private.goal_streak(u.id) as goal_streak,
  coalesce(sum(a.points_awarded) filter(where a.created_at >= date_trunc('day',now() at time zone 'Asia/Yekaterinburg') at time zone 'Asia/Yekaterinburg'),0) as day_points,
  coalesce(sum(a.points_awarded) filter(where a.created_at >= date_trunc('week',now() at time zone 'Asia/Yekaterinburg') at time zone 'Asia/Yekaterinburg'),0) as week_points,
  coalesce(sum(a.points_awarded) filter(where a.created_at >= date_trunc('month',now() at time zone 'Asia/Yekaterinburg') at time zone 'Asia/Yekaterinburg'),0) as month_points,
  coalesce(sum(a.points_awarded) filter(where a.created_at >= date_trunc('year',now() at time zone 'Asia/Yekaterinburg') at time zone 'Asia/Yekaterinburg'),0) as year_points
from public.users u left join public.answers a on a.user_id=u.id
where u.role is not null
group by u.id;

create or replace view public.leaderboard_users
with (security_barrier=true) as
select nickname as name, points, level, total_answers, day_answers,
  week_answers, month_answers, year_answers, corrections, errors,
  error_rate, vocabulary,day_points,week_points,month_points,year_points
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

revoke all on function private.goal_streak(uuid), private.award_badges(uuid)
  from public, anon, authenticated;
grant usage on schema private to service_role;
grant execute on function private.goal_streak(uuid), private.award_badges(uuid)
  to service_role;

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

-- Настройки и функции текущей версии после базовой схемы.


create schema if not exists extensions;
create extension if not exists pg_trgm with schema extensions;

alter table public.users add column if not exists current_shown_at timestamptz;
alter table public.users add column if not exists last_answer_at timestamptz;
alter table public.users add column if not exists reminders_enabled boolean not null default false;
alter table public.users add column if not exists last_reminder_date date;
alter table public.users add column if not exists deleted_at timestamptz;
alter table public.answers add column if not exists shown_at timestamptz;
alter table public.answers add column if not exists eligible boolean not null default true;
alter table public.answers add column if not exists vote_weight numeric(3,2) not null default 1.0;
alter table public.fragment_pairs add column if not exists resolved_by text
    check (resolved_by is null or resolved_by in ('consensus','expert'));
alter table public.classes add column if not exists created_by_user_id uuid references public.users(id);
update public.answers set eligible=false, vote_weight=0
  where shown_variant='bad' and action='confirm' and eligible;
update public.answers set shown_at=created_at where shown_at is null;
update public.fragment_pairs set resolved_by='consensus'
  where status='confirmed' and resolved_by is null;

create table if not exists public.synonym_map (
  lang_pair text not null references public.lang_pairs(code),
  variant text not null,
  canonical text not null,
  primary key (lang_pair,variant),
  check (length(variant) between 1 and 500),
  check (length(canonical) between 1 and 500)
);
create table if not exists public.expert_decisions (
  id uuid primary key default gen_random_uuid(),
  fragment_pair_id uuid not null references public.fragment_pairs(id),
  translation text not null,
  decision_note text,
  created_at timestamptz not null default now()
);
create table if not exists public.status_history (
  id uuid primary key default gen_random_uuid(),
  fragment_pair_id uuid not null references public.fragment_pairs(id),
  old_status text,
  new_status text not null,
  old_translation text,
  new_translation text,
  reason text not null,
  changed_at timestamptz not null default now()
);
create table if not exists public.import_batches (
 id uuid primary key default gen_random_uuid(),
 source_id uuid not null references public.sources(id),
 chapter text not null,
 content_hash text not null,
 created_at timestamptz not null default now(),
 unique(source_id,chapter,content_hash)
);
create table if not exists public.api_keys (
  id uuid primary key default gen_random_uuid(),
  partner_name text not null,
  key_hash text not null unique check (key_hash ~ '^[a-f0-9]{64}$'),
  permission text not null check (permission in ('read','write')),
  expires_at timestamptz,
  revoked_at timestamptz,
  created_at timestamptz not null default now()
);
create table if not exists public.external_answers (
  id uuid primary key default gen_random_uuid(),
  api_key_id uuid not null references public.api_keys(id),
  external_user_hash text not null,
  fragment_pair_id uuid not null references public.fragment_pairs(id),
  translation text not null,
  translation_norm text not null,
  created_at timestamptz not null default now(),
  unique (api_key_id,external_user_hash,fragment_pair_id)
);
create index if not exists ix_external_answers_pair on public.external_answers(fragment_pair_id);
create index if not exists ix_status_history_pair on public.status_history(fragment_pair_id);

insert into public.config(key,value) values
 ('daily_points_cap','150'),
 ('min_answer_seconds','2'),
 ('answer_interval_seconds','2'),
 ('vote_weight_step','0.1'),
 ('vote_weight_min','0.5'),
 ('vote_weight_max','1.5'),
 ('reminder_hour','18'),
 ('teacher_invite_code',''),
 ('expert_access_hash','')
on conflict(key) do nothing;

alter table public.synonym_map enable row level security;
alter table public.expert_decisions enable row level security;
alter table public.status_history enable row level security;
alter table public.import_batches enable row level security;
alter table public.api_keys enable row level security;
alter table public.external_answers enable row level security;
revoke all on public.synonym_map,public.expert_decisions,public.status_history,
  public.api_keys,public.external_answers,public.import_batches from public,anon,authenticated;
grant select,insert,update,delete on public.synonym_map,public.expert_decisions,
  public.status_history,public.api_keys,public.external_answers,
  public.import_batches to service_role;

create or replace function private.secret_hash(p_secret text)
returns text language sql immutable set search_path = '' as $$
 select pg_catalog.encode(pg_catalog.sha256(pg_catalog.convert_to(p_secret,'UTF8')),'hex');
$$;

create or replace function private.normalize_translation(p_text text)
returns text language sql immutable set search_path = '' as $$
  select pg_catalog.replace(pg_catalog.lower(pg_catalog.btrim(
    pg_catalog.regexp_replace(
      pg_catalog.regexp_replace(coalesce(p_text,''), '[[:space:]]+', ' ', 'g'),
      '^[[:punct:]«»„“” ]+|[[:punct:]«»„“” ]+$', '', 'g')
  )), 'ё','е');
$$;

create or replace function private.canonical_translation(p_pair text,p_text text)
returns text language sql stable security invoker set search_path = '' as $$
 select coalesce(
   (select sm.canonical from public.synonym_map sm
     where sm.lang_pair=p_pair and sm.variant=private.normalize_translation(p_text)),
   private.normalize_translation(p_text));
$$;

create or replace function private.vote_weight(p_user uuid)
returns numeric language sql stable security invoker set search_path = '' as $$
 select greatest(
   (select value::numeric from public.config where key='vote_weight_min'),
   least((select value::numeric from public.config where key='vote_weight_max'),
     1 + (select value::numeric from public.config where key='vote_weight_step') *
       (count(*) filter(where caught_planted_error) -
        count(*) filter(where shown_variant='bad' and action='confirm'))
   )
 )::numeric(3,2)
 from public.answers where user_id=p_user;
$$;

create or replace function private.track_status_change()
returns trigger language plpgsql security invoker set search_path = '' as $$
begin
 if old.status is distinct from new.status or
    old.final_translation is distinct from new.final_translation or
    old.resolved_by is distinct from new.resolved_by then
   insert into public.status_history(fragment_pair_id,old_status,new_status,
      old_translation,new_translation,reason)
   values(new.id,old.status,new.status,old.final_translation,new.final_translation,
     coalesce(new.resolved_by,'votes'));
 end if;
 return new;
end;
$$;
drop trigger if exists track_status_change on public.fragment_pairs;
create trigger track_status_change after update on public.fragment_pairs
for each row execute function private.track_status_change();

create or replace function private.reconcile_fragment(p_pair_id uuid)
returns void language plpgsql security invoker set search_path = '' as $$
declare
 v_pair public.fragment_pairs%rowtype;
 v_people integer;
 v_total_weight numeric;
 v_leader text;
 v_leader_count integer;
 v_leader_weight numeric;
 v_final text;
 v_confirmed boolean;
 v_min integer;
 v_share numeric;
 v_after integer;
 v_bonus integer;
 v_base integer;
 v_catch integer;
 v_step integer;
 v_cap integer;
 v_target integer;
 v_delta integer;
 v_other integer;
 v_answer record;
begin
 select * into strict v_pair from public.fragment_pairs where id=p_pair_id;
 select value::integer into strict v_min from public.config where key='min_votes';
 select value::numeric into strict v_share from public.config where key='consensus_share';
 select value::integer into strict v_after from public.config where key='expert_after_votes';
 select value::integer into strict v_bonus from public.config where key='bonus_match_consensus';
 select value::integer into strict v_base from public.config where key='points_per_answer';
 select value::integer into strict v_catch from public.config where key='bonus_catch_error';
 select value::integer into strict v_step from public.config where key='level_step';
 select value::integer into strict v_cap from public.config where key='daily_points_cap';

 select count(*),coalesce(sum(vote_weight),0) into v_people,v_total_weight
 from public.answers where fragment_pair_id=p_pair_id and eligible;
 select private.canonical_translation(v_pair.lang_pair,a.answer_norm), count(*),sum(a.vote_weight)
 into v_leader,v_leader_count,v_leader_weight
 from public.answers a where a.fragment_pair_id=p_pair_id and a.eligible
 group by 1 order by sum(a.vote_weight) desc, count(*) desc,
 private.canonical_translation(v_pair.lang_pair,a.answer_norm) collate "C" limit 1;

 if v_pair.resolved_by='expert' then
   v_final := v_pair.final_translation;
   v_leader := private.canonical_translation(v_pair.lang_pair,v_final);
   select count(*) into v_leader_count from public.answers a
   where a.fragment_pair_id=p_pair_id and a.eligible
    and private.canonical_translation(v_pair.lang_pair,a.answer_norm)=v_leader;
   v_confirmed := true;
   update public.fragment_pairs set confirmed_count=v_leader_count where id=p_pair_id;
 else
   v_confirmed := v_people >= v_min and
      v_leader_weight/nullif(v_total_weight,0) >= v_share;
   if v_confirmed then
     if v_leader=private.canonical_translation(v_pair.lang_pair,v_pair.auto_translation) then
       v_final:=v_pair.auto_translation;
     else
       select pg_catalog.btrim(a.answer_text) into v_final
       from public.answers a where a.fragment_pair_id=p_pair_id and a.eligible
         and a.action='correct' and a.answer_text is not null
         and private.canonical_translation(v_pair.lang_pair,a.answer_norm)=v_leader
       group by pg_catalog.btrim(a.answer_text)
       order by count(*) desc, pg_catalog.btrim(a.answer_text) collate "C" limit 1;
     end if;
     if v_final is null then raise exception 'Нет исходного текста для перевода'; end if;
     update public.fragment_pairs set status='confirmed',final_translation=v_final,
       confirmed_count=v_leader_count,resolved_by='consensus' where id=p_pair_id;
   elsif v_people>=v_after then
     update public.fragment_pairs set status='expert_review',final_translation=null,
       confirmed_count=0,resolved_by=null where id=p_pair_id;
   else
     update public.fragment_pairs set status='collecting',final_translation=null,
       confirmed_count=0,resolved_by=null where id=p_pair_id;
   end if;
 end if;

 for v_answer in
  select a.* from public.answers a where a.fragment_pair_id=p_pair_id
  order by a.user_id, a.created_at, a.id
 loop
   v_target:=case when not v_answer.eligible then 0
     else v_base + case when v_answer.caught_planted_error then v_catch else 0 end end;
   if v_confirmed and v_answer.eligible and
     private.canonical_translation(v_pair.lang_pair,v_answer.answer_norm)=v_leader then
     v_target:=v_target+v_bonus;
   end if;
   select coalesce(sum(points_awarded),0)::integer into v_other from public.answers
     where user_id=v_answer.user_id and id<>v_answer.id
       and (created_at at time zone 'Asia/Yekaterinburg')::date =
           (v_answer.created_at at time zone 'Asia/Yekaterinburg')::date;
   v_target:=least(v_target,greatest(0,v_cap-v_other));
   v_delta:=v_target-v_answer.points_awarded;
   if v_delta<>0 then
     update public.answers set points_awarded=v_target where id=v_answer.id;
     update public.users set points=greatest(0,points+v_delta),
       level=1+greatest(0,points+v_delta)/v_step where id=v_answer.user_id;
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
 v_prob numeric;
begin
 select * into v_user from public.users where id=p_user_id for update;
 if not found or v_user.deleted_at is not null then raise exception 'Пользователь не найден'; end if;
 if v_user.role is null or v_user.lang_pair is null
   or (v_user.role='teacher' and v_user.class_id is null)
   or v_user.nickname is null then raise exception 'Завершите регистрацию через /start'; end if;
 if v_user.state='awaiting_correction' then
   raise exception 'Сначала отправьте исправление или /cancel'; end if;
 if v_user.current_fragment_pair_id is not null and v_user.current_shown_variant is not null then
   select * into v_pair from public.fragment_pairs where id=v_user.current_fragment_pair_id;
   v_variant:=v_user.current_shown_variant;
   if v_user.current_shown_at is null then
     update public.users set current_shown_at=now() where id=p_user_id;
   end if;
 else
   select fp.* into v_pair from public.fragment_pairs fp
   where fp.lang_pair=v_user.lang_pair and fp.status in ('collecting','confirmed')
     and not exists(select 1 from public.answers a where a.user_id=p_user_id
       and a.fragment_pair_id=fp.id)
   order by (fp.id = v_user.last_skipped_fragment_pair_id) asc,
     (fp.status = 'confirmed') asc,
     (select count(*) from public.answers a2
       where a2.fragment_pair_id=fp.id and a2.eligible) desc,
     pg_catalog.random() limit 1;
   if not found then return null; end if;
   select value::numeric into strict v_prob from public.config where key='bad_variant_probability';
   v_variant:=case when v_pair.bad_translation is not null and pg_catalog.random()<v_prob
     then 'bad' else 'auto' end;
   update public.users set current_fragment_pair_id=v_pair.id,
     current_shown_variant=v_variant,current_shown_at=now() where id=p_user_id;
 end if;
 return (select jsonb_build_object('fragment_pair_id',v_pair.id,'text_ba',f.text_ba,
   'translation',case when v_variant='bad' then v_pair.bad_translation else v_pair.auto_translation end,
   'lang_pair',v_pair.lang_pair,'source',s.title,
   'source_kind',s.kind,'source_license',s.license,'source_url',case when s.kind='audio' then s.url end,
   'time_start',f.time_start,'time_end',f.time_end)
 from public.fragments f join public.sources s on s.id=f.source_id
 where f.id=v_pair.fragment_id);
end;
$$;

create or replace function public.skip_fragment(p_user_id uuid, p_fragment_pair_id uuid)
returns boolean language plpgsql security invoker set search_path = '' as $$
declare v_current uuid;
begin
  select current_fragment_pair_id into v_current from public.users
  where id=p_user_id and deleted_at is null for update;
  if not found or v_current is distinct from p_fragment_pair_id then
    return false;
  end if;
  update public.users set state='idle', current_fragment_pair_id=null,
    current_shown_variant=null, current_shown_at=null,
    last_skipped_fragment_pair_id=p_fragment_pair_id
  where id=p_user_id;
  return true;
end;
$$;

create or replace function public.submit_answer(
 p_user_id uuid,p_fragment_pair_id uuid,p_action text,p_text text default null
) returns jsonb language plpgsql security invoker set search_path = '' as $$
declare
 v_user public.users%rowtype;
 v_pair public.fragment_pairs%rowtype;
 v_shown text;
 v_norm text;
 v_caught boolean;
 v_fast numeric;
 v_interval numeric;
 v_elapsed numeric;
 v_base integer;
 v_catch integer;
 v_step integer;
 v_cap integer;
 v_points integer;
 v_used integer;
 v_id uuid;
 v_goal integer;
 v_day date;
 v_today integer;
 v_just boolean;
begin
 -- Сначала одна пара, затем все её участники в едином порядке: без глобальной блокировки.
 select * into v_pair from public.fragment_pairs where id=p_fragment_pair_id for update;
 if not found then raise exception 'Фрагмент не найден'; end if;
 perform 1 from public.users u where u.id=p_user_id or exists(
   select 1 from public.answers a where a.user_id=u.id and a.fragment_pair_id=p_fragment_pair_id)
 order by u.id for update;
 select * into v_user from public.users where id=p_user_id;
 if not found or v_user.deleted_at is not null then raise exception 'Пользователь не найден'; end if;
 if p_action not in ('confirm','correct') then raise exception 'Неверное действие'; end if;
 if exists(select 1 from public.answers where user_id=p_user_id and fragment_pair_id=p_fragment_pair_id) then
   return jsonb_build_object('duplicate',true,'points',v_user.points,'level',v_user.level);
 end if;
 if v_user.current_fragment_pair_id is distinct from p_fragment_pair_id
   or v_user.current_shown_variant is null then
   raise exception 'Задание устарело. Используйте /task'; end if;
 if v_user.state='awaiting_correction' and p_action<>'correct' then
   raise exception 'Сначала отправьте исправление или /cancel'; end if;
 if p_action='correct' and v_user.state<>'awaiting_correction'
   and v_user.auth_user_id is null then
   raise exception 'Сначала нажмите кнопку «Исправить»'; end if;
 select value::numeric into strict v_fast from public.config where key='min_answer_seconds';
 select value::numeric into strict v_interval from public.config where key='answer_interval_seconds';
 v_elapsed:=extract(epoch from now()-coalesce(v_user.current_shown_at,now()));
 if v_elapsed<v_fast then
   return jsonb_build_object('too_fast',true,'retry_seconds',ceil(v_fast-v_elapsed));
 end if;
 if v_user.last_answer_at is not null and extract(epoch from now()-v_user.last_answer_at)<v_interval then
   return jsonb_build_object('too_fast',true,
       'retry_seconds',ceil(v_interval-extract(epoch from now()-v_user.last_answer_at)));
 end if;
 v_shown:=case when v_user.current_shown_variant='bad' then v_pair.bad_translation
   else v_pair.auto_translation end;
 if v_shown is null then raise exception 'Нет показанного перевода'; end if;
 if p_action='correct' then
   if p_text is null or char_length(pg_catalog.btrim(p_text))=0 or char_length(p_text)>500 then
     raise exception 'Исправление должно быть от 1 до 500 символов'; end if;
   v_norm:=private.normalize_translation(p_text);
   if v_norm='' or v_norm=private.normalize_translation(v_shown) then
     raise exception 'Исправление не должно совпадать с показанным текстом'; end if;
 else
   v_norm:=private.normalize_translation(v_pair.auto_translation);
 end if;
 v_caught:=v_user.current_shown_variant='bad' and p_action='correct';
 select value::integer into strict v_base from public.config where key='points_per_answer';
 select value::integer into strict v_catch from public.config where key='bonus_catch_error';
 select value::integer into strict v_step from public.config where key='level_step';
 select value::integer into strict v_cap from public.config where key='daily_points_cap';
 v_day:=(now() at time zone 'Asia/Yekaterinburg')::date;
 select coalesce(sum(points_awarded),0)::integer into v_used from public.answers
   where user_id=p_user_id and (created_at at time zone 'Asia/Yekaterinburg')::date=v_day;
 v_points:=case when v_user.current_shown_variant='bad' and p_action='confirm' then 0
   else v_base+case when v_caught then v_catch else 0 end end;
 v_points:=least(v_points,greatest(0,v_cap-v_used));
 insert into public.answers(user_id,fragment_pair_id,shown_variant,action,
   answer_text,answer_norm,caught_planted_error,points_awarded,shown_at,eligible,vote_weight)
 values(p_user_id,p_fragment_pair_id,v_user.current_shown_variant,p_action,
   case when p_action='correct' then pg_catalog.btrim(p_text) else null end,
   v_norm,v_caught,v_points,v_user.current_shown_at,
   not(v_user.current_shown_variant='bad' and p_action='confirm'),
   case when v_user.current_shown_variant='bad' and p_action='confirm' then 0
        else private.vote_weight(p_user_id) end)
 returning id into v_id;
 select value::integer into strict v_goal from public.config where key='daily_goal';
 select count(*) into v_today from public.answers a where a.user_id=p_user_id
   and (a.created_at at time zone 'Asia/Yekaterinburg')::date=v_day;
 v_just:=v_today=v_goal and v_user.last_goal_date is distinct from v_day;
 update public.users set points=points+v_points,level=1+(points+v_points)/v_step,
   last_active_date=v_day,last_answer_at=now(),
   last_goal_date=case when v_today>=v_goal then v_day else last_goal_date end,
   state='idle',current_fragment_pair_id=null,current_shown_variant=null,
   current_shown_at=null where id=p_user_id;
 perform private.reconcile_fragment(p_fragment_pair_id);
 perform private.award_badges(p_user_id);
 return (select jsonb_build_object('points_awarded',a.points_awarded,
   'points',u.points,'level',u.level,'status',fp.status,
   'caught_planted_error',a.caught_planted_error,
   'correct_translation',case when a.shown_variant='bad' and a.action='confirm'
        then fp.auto_translation else null end,
   'final_translation',fp.final_translation,
   'daily_goal',v_goal,'today_answers',v_today,'goal_just_reached',v_just,
   'goal_streak',private.goal_streak(p_user_id))
 from public.answers a join public.users u on u.id=a.user_id
 join public.fragment_pairs fp on fp.id=a.fragment_pair_id where a.id=v_id);
end;
$$;

create or replace function private.expert_authorized(p_code text)
returns boolean language sql stable security invoker set search_path = '' as $$
 select coalesce(length(p_code) between 24 and 128 and exists(
   select 1 from public.config where key='expert_access_hash' and value<>''
     and value=private.secret_hash(p_code)),false);
$$;

create or replace function public.expert_list_queue(p_code text)
returns jsonb language plpgsql stable security definer set search_path = '' as $$
declare v_items jsonb;
begin
 if not private.expert_authorized(p_code) then raise exception 'Неверный код эксперта'; end if;
 select coalesce(jsonb_agg(to_jsonb(t)),'[]'::jsonb) into v_items
 from (
  select fp.id as fragment_pair_id,f.text_ba,fp.lang_pair,fp.auto_translation,
     s.title as source,fp.status,
     (select coalesce(jsonb_agg(jsonb_build_object('translation',v.translation,
       'votes',v.votes,'weight',v.weight)),'[]'::jsonb) from (
        select case when a.action='confirm' then fp.auto_translation
             else a.answer_text end as translation,
          count(*) as votes,sum(a.vote_weight) as weight
        from public.answers a where a.fragment_pair_id=fp.id and a.eligible
        group by 1 order by 2 desc,1 limit 20
      ) v) as options,
     (select coalesce(bool_or(extensions.similarity(
           private.normalize_translation(a1.answer_norm),
           private.normalize_translation(a2.answer_norm))>=0.65),false)
        from public.answers a1 join public.answers a2
          on a1.fragment_pair_id=a2.fragment_pair_id and a1.id<a2.id
       where a1.fragment_pair_id=fp.id and a1.eligible and a2.eligible
         and a1.answer_norm<>a2.answer_norm) as similar_variants,
     (with variants as (
       select private.normalize_translation(a.answer_norm) as normalized,
         min(case when a.action='confirm' then fp.auto_translation else a.answer_text end) as translation,
         count(*) as votes
       from public.answers a where a.fragment_pair_id=fp.id and a.eligible
       group by 1 order by votes desc,1 limit 20
     ), candidates as (
       select a.translation as left_translation,a.votes as left_votes,
         b.translation as right_translation,b.votes as right_votes,
         round(extensions.similarity(a.normalized,b.normalized)::numeric,3) as similarity
       from variants a join variants b on a.normalized collate "C" < b.normalized collate "C"
       where extensions.similarity(a.normalized,b.normalized)>=0.65
       order by similarity desc,a.normalized collate "C",b.normalized collate "C" limit 10
     ) select coalesce(jsonb_agg(to_jsonb(candidates)),'[]'::jsonb) from candidates) as similarity_candidates
  from public.fragment_pairs fp join public.fragments f on f.id=fp.fragment_id
  join public.sources s on s.id=f.source_id
  where fp.status='expert_review' order by f.created_at desc limit 100
 ) t;
 return v_items;
end;
$$;

create or replace function public.expert_resolve(p_code text,p_fragment_pair_id uuid,p_translation text)
returns jsonb language plpgsql security definer set search_path = '' as $$
declare v_pair public.fragment_pairs%rowtype;
 v_people integer;
begin
 if not private.expert_authorized(p_code) then raise exception 'Неверный код эксперта'; end if;
 if p_translation is null or length(pg_catalog.btrim(p_translation)) not between 1 and 500
   then raise exception 'Нужен итоговый перевод до 500 символов'; end if;
 select * into v_pair from public.fragment_pairs where id=p_fragment_pair_id for update;
 if not found or v_pair.status<>'expert_review' then
   raise exception 'Фрагмент не находится в очереди экспертов'; end if;
 perform 1 from public.users u where exists(select 1 from public.answers a
   where a.fragment_pair_id=p_fragment_pair_id and a.user_id=u.id)
 order by u.id for update;
 insert into public.expert_decisions(fragment_pair_id,translation)
 values(p_fragment_pair_id,pg_catalog.btrim(p_translation));
 select count(*) into v_people from public.answers a where a.fragment_pair_id=p_fragment_pair_id
   and a.eligible and private.canonical_translation(v_pair.lang_pair,a.answer_norm)=
     private.canonical_translation(v_pair.lang_pair,p_translation);
 update public.fragment_pairs set status='confirmed',resolved_by='expert',
   final_translation=pg_catalog.btrim(p_translation),confirmed_count=v_people
 where id=p_fragment_pair_id;
 perform private.reconcile_fragment(p_fragment_pair_id);
 return jsonb_build_object('status','confirmed','confirmed_count',v_people);
end;
$$;

create or replace function private.api_key_row(p_key text,p_permission text)
returns uuid language sql stable security invoker set search_path = '' as $$
 select id from public.api_keys where key_hash=private.secret_hash(p_key)
 and revoked_at is null and (expires_at is null or expires_at>now())
 and (permission='write' or p_permission='read')
 and length(p_key) between 30 and 128 limit 1;
$$;

create or replace function public.api_get_fragments(
 p_key text,p_lang_pair text,p_limit integer default 20,p_cursor uuid default null
) returns jsonb language plpgsql stable security definer set search_path = '' as $$
declare v_items jsonb; v_next uuid;
begin
 if private.api_key_row(p_key,'read') is null then raise exception 'Недействительный API-ключ'; end if;
 if p_limit is null or p_limit<1 or p_limit>100 then raise exception 'Лимит: 1–100'; end if;
 if not exists(select 1 from public.lang_pairs where code=p_lang_pair) then
   raise exception 'Неверная языковая пара'; end if;
 select coalesce(jsonb_agg(to_jsonb(t) order by t.fragment_pair_id),'[]'::jsonb),max(t.fragment_pair_id::text)::uuid
   into v_items,v_next
 from (select fp.id as fragment_pair_id,f.text_ba,fp.lang_pair,fp.auto_translation,
   fp.final_translation,fp.status,s.title as source
   from public.fragment_pairs fp join public.fragments f on f.id=fp.fragment_id
   join public.sources s on s.id=f.source_id
   where fp.lang_pair=p_lang_pair and (p_cursor is null or fp.id>p_cursor)
   order by fp.id limit p_limit) t;
 return jsonb_build_object('items',v_items,'next_cursor',v_next);
end;
$$;

create or replace function public.api_submit_answer(
 p_key text,p_external_user text,p_fragment_pair_id uuid,p_translation text
) returns jsonb language plpgsql security definer set search_path = '' as $$
declare v_key uuid; v_user_hash text; v_id uuid;
begin
 v_key:=private.api_key_row(p_key,'write');
 if v_key is null then raise exception 'Нет права записи по API-ключу'; end if;
 if p_external_user is null or length(p_external_user) not between 1 and 100
   or p_translation is null or length(pg_catalog.btrim(p_translation)) not between 1 and 500
   then raise exception 'Неверные данные ответа'; end if;
 if not exists(select 1 from public.fragment_pairs where id=p_fragment_pair_id) then
   raise exception 'Фрагмент не найден'; end if;
 v_user_hash:=private.secret_hash(v_key::text||':'||p_external_user);
 insert into public.external_answers(api_key_id,external_user_hash,fragment_pair_id,
   translation,translation_norm)
 values(v_key,v_user_hash,p_fragment_pair_id,pg_catalog.btrim(p_translation),
   private.normalize_translation(p_translation))
 on conflict(api_key_id,external_user_hash,fragment_pair_id) do nothing
 returning id into v_id;
 return jsonb_build_object('accepted',v_id is not null,'duplicate',v_id is null);
end;
$$;

create or replace function public.create_teacher_class(
 p_user_id uuid,p_invite text,p_name text
) returns jsonb language plpgsql security invoker set search_path = '' as $$
declare v_teacher public.users%rowtype; v_school uuid;
 v_count integer; v_join text; v_teacher_code text;
begin
 select * into v_teacher from public.users where id=p_user_id for update;
 if not found or v_teacher.role<>'teacher' or v_teacher.class_id is null
     or v_teacher.deleted_at is not null then raise exception 'Нет прав преподавателя'; end if;
 if not exists(select 1 from public.config where key='teacher_invite_code' and value<>''
   and value=private.secret_hash(p_invite)) then
   raise exception 'Неверный код приглашения'; end if;
 if length(pg_catalog.btrim(p_name)) not between 2 and 60 then
   raise exception 'Название класса: 2–60 символов'; end if;
 select school_id into strict v_school from public.classes where id=v_teacher.class_id;
 select count(*) into v_count from public.classes where created_by_user_id=p_user_id;
 if v_count>=3 then raise exception 'Лимит: не больше трёх новых классов'; end if;
 v_join:=pg_catalog.substring(pg_catalog.translate(
   pg_catalog.upper(pg_catalog.replace(gen_random_uuid()::text,'-','')),'01','XY'),1,8);
 v_teacher_code:=pg_catalog.replace(gen_random_uuid()::text,'-','')||
                 pg_catalog.replace(gen_random_uuid()::text,'-','');
 insert into public.classes(school_id,name,join_code,teacher_code,created_by_user_id)
 values(v_school,pg_catalog.btrim(p_name),v_join,v_teacher_code,p_user_id);
 return jsonb_build_object('join_code',v_join,'teacher_code',v_teacher_code);
end;
$$;

-- В официальном ТЗ confirmed — число проголосовавших, не boolean.


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
 v_progress jsonb;
 v_mistakes jsonb;
 v_goal integer;
begin
 if p_teacher_code is null or length(p_teacher_code) not between 20 and 128 then
    raise exception 'Неверный код преподавателя'; end if;
 select * into v_class from public.classes where teacher_code=p_teacher_code;
 if not found then raise exception 'Класс не найден'; end if;
 select name into v_school from public.schools where id=v_class.school_id;
 select value::integer into strict v_goal from public.config where key='daily_goal';
 select count(*) into v_students from public.users where class_id=v_class.id and role='student';
 select count(*),coalesce(round(100.0 * count(*) filter
   (where a.shown_variant='bad' and a.action='confirm') / nullif(count(*),0),2),0)
 into v_answers,v_errors from public.answers a
 join public.users u on u.id=a.user_id where u.class_id=v_class.id and u.role='student';
 select coalesce(jsonb_agg(to_jsonb(t)),'[]'::jsonb) into v_top from (
   select u.nickname as name,u.points,u.level,count(a.id) as answers
   from public.users u left join public.answers a on a.user_id=u.id
   where u.class_id=v_class.id and u.role='student'
   group by u.id order by u.points desc,count(a.id) desc,u.nickname limit 10
 ) t;
 select coalesce(jsonb_agg(to_jsonb(d) order by d.day),'[]'::jsonb)
 into v_days from (
    select (a.created_at at time zone 'Asia/Yekaterinburg')::date as day,
      count(*) as answers
    from public.answers a join public.users u on u.id=a.user_id
    where u.class_id=v_class.id and u.role='student'
    group by 1 order by 1 desc limit 30
 ) d;
 select coalesce(jsonb_agg(to_jsonb(p) order by p.today_answers desc,p.name), '[]'::jsonb)
 into v_progress from (
   select u.nickname as name,count(a.id) as today_answers,
     (count(a.id)>=v_goal) as completed
   from public.users u left join public.answers a on a.user_id=u.id
      and (a.created_at at time zone 'Asia/Yekaterinburg')::date=
        (now() at time zone 'Asia/Yekaterinburg')::date
   where u.class_id=v_class.id and u.role='student'
   group by u.id
 ) p;
 select coalesce(jsonb_agg(to_jsonb(m) order by m.errors desc),'[]'::jsonb)
 into v_mistakes from (
   select f.text_ba,fp.lang_pair,count(*) as errors
   from public.answers a join public.users u on u.id=a.user_id
   join public.fragment_pairs fp on fp.id=a.fragment_pair_id
   join public.fragments f on f.id=fp.fragment_id
   where u.class_id=v_class.id and u.role='student'
     and a.shown_variant='bad' and a.action='confirm'
   group by f.id,fp.lang_pair order by count(*) desc limit 5
 ) m;
 return jsonb_build_object('school',v_school,'class',v_class.name,
   'students_count',v_students,'answers_count',v_answers,'error_rate',v_errors,
   'top_students',v_top,'activity',v_days,
   'students_progress',v_progress,'frequent_mistakes',v_mistakes);
end;
$$;

revoke all on function public.get_class_report(text) from public, anon, authenticated;
grant execute on function public.get_class_report(text) to anon, service_role;

-- Список экспертов и личные записи не предоставляются публичному роли API.
revoke all on function private.secret_hash(text),private.canonical_translation(text,text),
 private.vote_weight(uuid),private.track_status_change(),private.expert_authorized(text),
 private.api_key_row(text,text) from public,anon,authenticated;
revoke all on function public.expert_list_queue(text),
 public.expert_resolve(text,uuid,text),public.api_get_fragments(text,text,integer,uuid),
 public.api_submit_answer(text,text,uuid,text),public.create_teacher_class(uuid,text,text)
 from public,anon,authenticated;
revoke all on function private.normalize_translation(text),private.reconcile_fragment(uuid),
 public.get_next_fragment(uuid),public.submit_answer(uuid,uuid,text,text),
 public.skip_fragment(uuid,uuid)
 from public,anon,authenticated;
grant execute on function public.expert_list_queue(text),
 public.expert_resolve(text,uuid,text),public.api_get_fragments(text,text,integer,uuid),
 public.api_submit_answer(text,text,uuid,text) to anon;
grant execute on function private.secret_hash(text),private.canonical_translation(text,text),
 private.vote_weight(uuid),private.track_status_change(),private.expert_authorized(text),
 private.api_key_row(text,text),private.normalize_translation(text),
 private.reconcile_fragment(uuid),public.get_next_fragment(uuid),
 public.submit_answer(uuid,uuid,text,text), public.skip_fragment(uuid,uuid),
 public.create_teacher_class(uuid,text,text),
 public.expert_list_queue(text),public.expert_resolve(text,uuid,text),
 public.api_get_fragments(text,text,integer,uuid),
 public.api_submit_answer(text,text,uuid,text) to service_role;

notify pgrst,'reload schema';


-- Только агрегированные переводы; данные учеников не раскрываются.
create or replace view public.adventure_progress with (security_barrier = true) as
select lp.code as lang_pair,
  count(fp.id) filter (where fp.status = 'confirmed' and s.license <> 'demo') as confirmed,
  count(fp.id) filter (where fp.status = 'collecting' and s.license <> 'demo') as collecting,
  count(fp.id) filter (where fp.status = 'expert_review' and s.license <> 'demo') as expert_review
from public.lang_pairs lp
left join public.fragment_pairs fp on fp.lang_pair = lp.code
left join public.fragments f on f.id = fp.fragment_id
left join public.sources s on s.id = f.source_id
group by lp.code;

revoke all on public.adventure_progress from public, anon, authenticated;
grant select on public.adventure_progress to anon, service_role;
notify pgrst, 'reload schema';
-- Compare the active assignment while holding its user's row lock. A delayed
-- callback must never restore awaiting_correction after an answer or /cancel.
create or replace function public.begin_correction(p_user_id uuid, p_fragment_pair_id uuid)
returns boolean language plpgsql security invoker set search_path = '' as $$
begin
  perform 1 from public.users where id=p_user_id and deleted_at is null
    and current_fragment_pair_id=p_fragment_pair_id
    and current_shown_variant is not null
    and state in ('idle','awaiting_correction') for update;
  if not found then return false; end if;
  if exists(select 1 from public.answers
    where user_id=p_user_id and fragment_pair_id=p_fragment_pair_id) then
    return false;
  end if;
  update public.users set state='awaiting_correction' where id=p_user_id;
  return true;
end;
$$;

revoke all on function public.begin_correction(uuid,uuid) from public,anon,authenticated;
grant execute on function public.begin_correction(uuid,uuid) to service_role;
notify pgrst, 'reload schema';


-- Браузер работает с Supabase Auth; идентификатор ученика из клиента не принимаем.
create or replace function public.web_register(
 p_nickname text, p_lang_pair text, p_join_code text default null
) returns jsonb language plpgsql security definer set search_path = '' as $$
declare
 v_auth uuid := auth.uid();
 v_class uuid;
 v_user public.users%rowtype;
begin
 if v_auth is null then raise exception 'Нужно войти в игру'; end if;
 if p_nickname is null or char_length(p_nickname) not between 3 and 20
   or p_nickname !~ '^[[:alnum:] _-]+$' then
   raise exception 'Никнейм: 3–20 символов, буквы, цифры, пробел, - или _';
 end if;
 if not exists (select 1 from public.lang_pairs where code=p_lang_pair)
   or not exists (select 1 from public.fragment_pairs where lang_pair=p_lang_pair) then
   raise exception 'Для этой пары пока нет заданий';
 end if;
 if nullif(trim(p_join_code),'') is not null then
   select id into v_class from public.classes where join_code=upper(trim(p_join_code));
   if not found then raise exception 'Неверный код класса'; end if;
 end if;
 select * into v_user from public.users where auth_user_id=v_auth for update;
 if found and v_user.deleted_at is not null then
   raise exception 'Этот профиль удалён';
 end if;
 if found then
   update public.users set nickname=trim(p_nickname),
     lang_pair=p_lang_pair,
     class_id=case when nullif(trim(p_join_code),'') is not null then v_class else class_id end,
     current_fragment_pair_id=case when lang_pair is distinct from p_lang_pair then null else current_fragment_pair_id end,
     current_shown_variant=case when lang_pair is distinct from p_lang_pair then null else current_shown_variant end,
     current_shown_at=case when lang_pair is distinct from p_lang_pair then null else current_shown_at end,
     state='idle'
   where id=v_user.id;
 else
   insert into public.users(auth_user_id,nickname,role,class_id,lang_pair,state)
   values (v_auth,trim(p_nickname),'student',v_class,p_lang_pair,'idle');
 end if;
 return public.web_profile();
end;
$$;

create or replace function public.web_profile()
returns jsonb language plpgsql stable security definer set search_path = '' as $$
declare
 v_user public.users%rowtype;
 v_day date := (now() at time zone 'Asia/Yekaterinburg')::date;
 v_today integer;
 v_goal integer;
 v_badges jsonb;
 v_class_name text;
begin
 if auth.uid() is null then raise exception 'Нужно войти в игру'; end if;
 select * into v_user from public.users
 where auth_user_id=auth.uid() and deleted_at is null and role='student';
 if not found then return null; end if;
 select count(*) into v_today from public.answers a where a.user_id=v_user.id
   and (a.created_at at time zone 'Asia/Yekaterinburg')::date=v_day;
 select value::integer into v_goal from public.config where key='daily_goal';
 select coalesce(jsonb_agg(jsonb_build_object('title',b.title,'code',b.code)
   order by b.code),'[]'::jsonb) into v_badges
 from public.user_badges ub join public.badges b on b.code=ub.badge_code
 where ub.user_id=v_user.id;
 select c.name into v_class_name from public.classes c where c.id=v_user.class_id;
 return jsonb_build_object('nickname',v_user.nickname,'lang_pair',v_user.lang_pair,
   'points',v_user.points,'level',v_user.level,'today_answers',v_today,
   'daily_goal',coalesce(v_goal,5),'streak',private.goal_streak(v_user.id),
   'badges',v_badges,'class_name',v_class_name,
   'total_answers',(select count(*) from public.answers where user_id=v_user.id));
end;
$$;

create or replace function public.web_next_fragment()
returns jsonb language plpgsql security definer set search_path = '' as $$
declare v_user uuid;
begin
 if auth.uid() is null then raise exception 'Нужно войти в игру'; end if;
 select id into v_user from public.users where auth_user_id=auth.uid()
   and role='student' and deleted_at is null;
 if not found then raise exception 'Сначала создай профиль'; end if;
 return public.get_next_fragment(v_user);
end;
$$;

create or replace function public.web_submit_answer(
 p_fragment_pair_id uuid,p_action text,p_text text default null
) returns jsonb language plpgsql security definer set search_path = '' as $$
declare v_user uuid;
begin
 if auth.uid() is null then raise exception 'Нужно войти в игру'; end if;
 select id into v_user from public.users where auth_user_id=auth.uid()
   and role='student' and deleted_at is null;
 if not found then raise exception 'Сначала создай профиль'; end if;
 return public.submit_answer(v_user,p_fragment_pair_id,p_action,p_text);
end;
$$;

create or replace function public.web_skip_fragment(p_fragment_pair_id uuid)
returns boolean language plpgsql security definer set search_path = '' as $$
declare v_user uuid;
begin
 if auth.uid() is null then raise exception 'Нужно войти в игру'; end if;
 select id into v_user from public.users where auth_user_id=auth.uid()
   and role='student' and deleted_at is null;
 if not found then raise exception 'Сначала создай профиль'; end if;
 return public.skip_fragment(v_user,p_fragment_pair_id);
end;
$$;

revoke all on function
 public.web_register(text,text,text), public.web_profile(),
 public.web_next_fragment(),public.web_submit_answer(uuid,text,text),
 public.web_skip_fragment(uuid) from public,anon,authenticated;
grant execute on function
 public.web_register(text,text,text),public.web_profile(),
 public.web_next_fragment(),public.web_submit_answer(uuid,text,text),
 public.web_skip_fragment(uuid) to authenticated;

grant select on public.translations_export,public.leaderboard_users,
 public.leaderboard_classes,public.leaderboard_schools,
 public.adventure_progress to authenticated;
notify pgrst, 'reload schema';

-- Standalone Compose bootstrap originally created this as postgres, preventing
-- GoTrue from executing its own CREATE OR REPLACE migrations. No data changes.
do $$ begin
  if exists(select 1 from pg_roles where rolname='supabase_auth_admin')
     and to_regprocedure('auth.uid()') is not null then
    alter function auth.uid() owner to supabase_auth_admin;
  end if;
end $$;

-- GoTrue's migration tracker uses unqualified names. Keep its tables in auth,
-- without granting CREATE on public or weakening application-table permissions.
do $$ begin
  if exists(select 1 from pg_roles where rolname='supabase_auth_admin') then
    alter role supabase_auth_admin set search_path to auth, public, extensions;
  end if;
end $$;

create or replace function public.import_audio_fragments(p_source jsonb,p_segments jsonb)
returns jsonb language plpgsql security invoker set search_path = '' as $$
declare
 sid uuid := (p_source->>'id')::uuid;
 item jsonb;
 fid uuid;
 pid uuid;
 t0 numeric;
 t1 numeric;
 src public.sources%rowtype;
 frag public.fragments%rowtype;
 pair public.fragment_pairs%rowtype;
begin
 if p_source->>'kind' is distinct from 'audio'
   or coalesce(length(trim(p_source->>'title')),0) not between 1 and 500
   or coalesce(length(trim(p_source->>'license')),0) not between 1 and 500
   or coalesce(p_source->>'url','') !~ '^/web/assets/original-audio/[0-9a-f]{64}\.(wav|mp3)$'
   or jsonb_typeof(p_segments) is distinct from 'array' then
   raise exception 'Invalid audio source/segments'; end if;
 if jsonb_array_length(p_segments) not between 1 and 1000 then
   raise exception 'Expected 1-1000 audio segments'; end if;
 insert into public.sources(id,title,kind,license,url)
 values(sid,p_source->>'title','audio',p_source->>'license',p_source->>'url') on conflict do nothing;
 select * into strict src from public.sources where id=sid;
 if (src.title,src.kind,src.license,src.url) is distinct from
   (p_source->>'title','audio',p_source->>'license',p_source->>'url') then
   raise exception 'Audio source conflict'; end if;
 for item in select value from jsonb_array_elements(p_segments) loop
   fid := (item->>'id')::uuid; pid := (item->>'pair_id')::uuid;
   t0 := (item->>'time_start')::numeric; t1 := (item->>'time_end')::numeric;
   if t0 is null or t1 is null or t0::text in ('NaN','Infinity','-Infinity')
     or t1::text in ('NaN','Infinity','-Infinity') or t0<0 or t1<=t0 or t1>28800
     or coalesce(item->>'lang_pair','') not in ('ba-ru','ba-kk')
     or coalesce(length(trim(item->>'text_ba')),0) not between 1 and 5000
     or coalesce(length(trim(item->>'translation')),0) not between 1 and 500 then
     raise exception 'Invalid audio segment'; end if;
   insert into public.fragments(id,source_id,text_ba,position,time_start,time_end)
   values(fid,sid,item->>'text_ba',(item->>'position')::integer,t0,t1) on conflict do nothing;
   select * into strict frag from public.fragments where id=fid;
   if (frag.source_id,frag.text_ba,frag.position,frag.time_start,frag.time_end) is distinct from
     (sid,item->>'text_ba',(item->>'position')::integer,t0,t1) then
     raise exception 'Audio fragment conflict'; end if;
   insert into public.fragment_pairs(id,fragment_id,lang_pair,auto_translation)
   values(pid,fid,item->>'lang_pair',item->>'translation') on conflict do nothing;
   select * into strict pair from public.fragment_pairs where id=pid;
   if (pair.fragment_id,pair.lang_pair,pair.auto_translation) is distinct from
     (fid,item->>'lang_pair',item->>'translation') then
     raise exception 'Audio translation conflict'; end if;
 end loop;
 return jsonb_build_object('source_id',sid,'segments',jsonb_array_length(p_segments));
end;
$$;
revoke all on function public.import_audio_fragments(jsonb,jsonb) from public,anon,authenticated;
grant execute on function public.import_audio_fragments(jsonb,jsonb) to service_role;

notify pgrst,'reload schema';
