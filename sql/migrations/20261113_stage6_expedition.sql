begin;

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

commit;
