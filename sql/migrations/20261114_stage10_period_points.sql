begin;
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
notify pgrst, 'reload schema';
commit;
