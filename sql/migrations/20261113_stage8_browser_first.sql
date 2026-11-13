begin;
-- Сохраняем Telegram-пользователей и добавляем отдельную идентичность браузера.
alter table public.users alter column telegram_id drop not null;
alter table public.users add column if not exists auth_user_id uuid unique;
do $$ begin
  if not exists (select 1 from pg_constraint
    where conrelid='public.users'::regclass and conname='users_identity_present') then
    alter table public.users add constraint users_identity_present
    check (telegram_id is not null or auth_user_id is not null);
  end if;
end $$;

-- Меняем только проверки существующей логики и добавляем безопасные RPC.
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
   or (v_user.class_id is null and v_user.auth_user_id is null)
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
   'time_start',f.time_start,'time_end',f.time_end)
 from public.fragments f join public.sources s on s.id=f.source_id
 where f.id=v_pair.fragment_id);
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

commit;
