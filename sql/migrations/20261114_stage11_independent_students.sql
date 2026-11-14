begin;

-- Students may study independently. Teacher class authorization remains mandatory.
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
   'time_start',f.time_start,'time_end',f.time_end)
 from public.fragments f join public.sources s on s.id=f.source_id
 where f.id=v_pair.fragment_id);
end;
$$;

notify pgrst, 'reload schema';
commit;
