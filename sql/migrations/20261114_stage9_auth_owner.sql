begin;
-- Standalone Compose bootstrap originally created this as postgres, preventing
-- GoTrue from executing its own CREATE OR REPLACE migrations. No data changes.
do $$ begin
  if exists(select 1 from pg_roles where rolname='supabase_auth_admin')
     and to_regprocedure('auth.uid()') is not null then
    alter function auth.uid() owner to supabase_auth_admin;
  end if;
end $$;
commit;
