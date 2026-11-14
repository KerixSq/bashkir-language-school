begin;
alter table public.users alter column reminders_enabled set default false;
insert into public.config(key,value) values('reminder_hour','18') on conflict(key) do nothing;

create or replace function public.claim_daily_reminders(
 p_now timestamptz default now(),p_limit integer default 20)
returns table(user_id uuid,telegram_id bigint,reminder_date date)
language plpgsql security invoker set search_path = '' as $$
declare
 v_local timestamp := p_now at time zone 'Asia/Yekaterinburg';
 v_day date := v_local::date;
 v_start timestamptz := v_day::timestamp at time zone 'Asia/Yekaterinburg';
 v_hour integer;
 v_goal integer;
begin
 if p_now is null or p_limit is null or p_limit not between 1 and 100 then
   raise exception 'Invalid reminder clock/batch'; end if;
 select value::integer into strict v_hour from public.config where key='reminder_hour';
 select value::integer into strict v_goal from public.config where key='daily_goal';
 if v_hour not between 0 and 23 or v_goal<1 then raise exception 'Invalid reminder configuration'; end if;
 if extract(hour from v_local)<>v_hour then return; end if;
 return query
 with due as (
   select u.id from public.users u
   where u.reminders_enabled and u.deleted_at is null and u.telegram_id>0
     and u.nickname is not null and u.lang_pair is not null
     and (u.role='student' or (u.role='teacher' and u.class_id is not null))
     and (u.last_reminder_date is null or u.last_reminder_date<v_day)
     and (select count(*) from public.answers a where a.user_id=u.id
       and a.created_at>=v_start and a.created_at<v_start+interval '1 day')<v_goal
     and exists(select 1 from public.fragment_pairs fp where fp.lang_pair=u.lang_pair
       and fp.status in ('collecting','confirmed') and not exists(
         select 1 from public.answers a where a.user_id=u.id and a.fragment_pair_id=fp.id))
   order by u.id limit p_limit for update of u skip locked
 )
 update public.users u set last_reminder_date=v_day from due
 where u.id=due.id returning u.id,u.telegram_id,v_day;
end;
$$;
revoke all on function public.claim_daily_reminders(timestamptz,integer) from public,anon,authenticated;
grant execute on function public.claim_daily_reminders(timestamptz,integer) to service_role;

notify pgrst,'reload schema';
commit;
