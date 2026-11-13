begin;

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

commit;
