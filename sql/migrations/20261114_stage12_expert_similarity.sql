begin;
-- Advisory text similarity only. Existing authorization and grants are preserved.
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
notify pgrst, 'reload schema';
commit;
