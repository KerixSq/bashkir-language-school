begin;
-- GoTrue's migration tracker uses unqualified names. Keep its tables in auth,
-- without granting CREATE on public or weakening application-table permissions.
do $$ begin
  if exists(select 1 from pg_roles where rolname='supabase_auth_admin') then
    alter role supabase_auth_admin set search_path to auth, public, extensions;
  end if;
end $$;
commit;
