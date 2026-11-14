begin;
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
   'source_kind',s.kind,'source_license',s.license,'source_url',case when s.kind='audio' and s.url ~ '^/web/assets/original-audio/[0-9a-f]{64}\.(wav|mp3)$' then s.url end,
   'time_start',f.time_start,'time_end',f.time_end)
 from public.fragments f join public.sources s on s.id=f.source_id
 where f.id=v_pair.fragment_id);
end;
$$;

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
commit;
