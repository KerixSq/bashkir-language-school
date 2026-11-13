begin;

-- Оригинальные ID нужны для сверки после дедупликации пяти разговорников.
create table if not exists public.phrasebook_rows (
  source_hash text not null check (source_hash ~ '^[0-9a-f]{64}$'),
  row_id text not null,
  record_hash text not null check (record_hash ~ '^[0-9a-f]{64}$'),
  source_id uuid not null references public.sources(id),
  fragment_id uuid not null references public.fragments(id),
  file_name text not null,
  line_number integer not null check (line_number >= 1),
  primary key (source_hash, row_id)
);

create index if not exists ix_phrasebook_rows_fragment
  on public.phrasebook_rows(fragment_id);

alter table public.phrasebook_rows enable row level security;
revoke all on public.phrasebook_rows from public, anon, authenticated;
grant select, insert, update, delete on public.phrasebook_rows to service_role;

notify pgrst, 'reload schema';
commit;
