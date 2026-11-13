#!/bin/sh
set -eu

# PostgreSQL image executes this script once, on creation of an empty volume.
psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" \
  -v rest_password="$AUTHENTICATOR_PASSWORD" \
  -v auth_password="$AUTH_ADMIN_PASSWORD" <<'SQL'
CREATE ROLE anon NOLOGIN;
CREATE ROLE authenticated NOLOGIN;
CREATE ROLE service_role NOLOGIN BYPASSRLS;
SELECT format('CREATE ROLE authenticator LOGIN NOINHERIT PASSWORD %L', :'rest_password') \gexec
SELECT format('CREATE ROLE supabase_auth_admin LOGIN PASSWORD %L', :'auth_password') \gexec
GRANT anon, authenticated, service_role TO authenticator;
GRANT USAGE ON SCHEMA public TO anon, authenticated, service_role;
CREATE SCHEMA IF NOT EXISTS auth AUTHORIZATION supabase_auth_admin;
ALTER ROLE supabase_auth_admin SET search_path TO auth, public, extensions;
CREATE SCHEMA IF NOT EXISTS extensions;
GRANT USAGE ON SCHEMA auth TO anon, authenticated, service_role;
GRANT CREATE ON DATABASE bashkir TO supabase_auth_admin;
CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE OR REPLACE FUNCTION auth.uid()
RETURNS uuid LANGUAGE sql STABLE SET search_path = '' AS $$
  SELECT nullif(nullif(current_setting('request.jwt.claims', true), '')::jsonb ->> 'sub', '')::uuid;
$$;
REVOKE ALL ON FUNCTION auth.uid() FROM PUBLIC;
GRANT EXECUTE ON FUNCTION auth.uid() TO authenticated, service_role;
-- GoTrue migrations replace auth.uid(); the migration role must own it.
ALTER FUNCTION auth.uid() OWNER TO supabase_auth_admin;
SQL
