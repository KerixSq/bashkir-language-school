begin;

-- Идентификатор строки исходного JSONL уникален внутри файла, но не во всём корпусе.
-- Старые записи сохраняют исходный ID как суффикс: file_name::original_id.
update public.phrasebook_rows
set row_id = file_name || '::' || row_id
where left(row_id, char_length(file_name) + 2) <> file_name || '::';

-- Пропущенное задание не показываем повторно, пока есть другие варианты.
alter table public.users
  add column if not exists last_skipped_fragment_pair_id uuid
  references public.fragment_pairs(id) on delete set null;

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
 if v_user.role is null or v_user.lang_pair is null or v_user.class_id is null
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

revoke all on function public.get_next_fragment(uuid), public.skip_fragment(uuid, uuid)
  from public, anon, authenticated;
grant execute on function public.get_next_fragment(uuid), public.skip_fragment(uuid, uuid)
  to service_role;

notify pgrst, 'reload schema';
commit;
