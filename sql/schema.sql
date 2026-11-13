-- 01. Схема. Запустить первой в Supabase SQL Editor.
create schema if not exists private;

create table if not exists public.lang_pairs (
  code text primary key,
  name text not null
);
create table if not exists public.schools (
  id uuid primary key default gen_random_uuid(),
  name text not null
);
create table if not exists public.classes (
  id uuid primary key default gen_random_uuid(),
  school_id uuid not null references public.schools(id),
  name text not null,
  join_code text not null unique check (join_code ~ '^[A-HJ-NP-Z2-9]{6,8}$'),
  teacher_code text not null unique check (teacher_code ~ '^[A-Za-z0-9_-]{20,128}$')
);
create table if not exists public.sources (
  id uuid primary key default gen_random_uuid(),
  title text not null,
  kind text not null check (kind in ('text','audio')),
  license text not null,
  url text
);
create table if not exists public.fragments (
  id uuid primary key default gen_random_uuid(),
  source_id uuid not null references public.sources(id),
  text_ba text not null,
  chapter text,
  position integer not null check (position >= 1),
  time_start numeric check (time_start >= 0),
  time_end numeric,
  created_at timestamptz not null default now(),
  check (time_end is null or (time_start is not null and time_end > time_start))
);
-- Соответствие каждой строки корпуса исходному ID после дедупликации.
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

create table if not exists public.fragment_pairs (
  id uuid primary key default gen_random_uuid(),
  fragment_id uuid not null references public.fragments(id),
  lang_pair text not null references public.lang_pairs(code),
  auto_translation text not null,
  bad_translation text,
  status text not null default 'collecting'
    check (status in ('collecting','confirmed','expert_review')),
  final_translation text,
  confirmed_count integer not null default 0 check (confirmed_count >= 0),
  unique (fragment_id, lang_pair)
);
create table if not exists public.users (
  id uuid primary key default gen_random_uuid(),
  telegram_id bigint unique,
  auth_user_id uuid unique,
  constraint users_identity_present check (telegram_id is not null or auth_user_id is not null),
  username text,
  display_name text,
  nickname text check (nickname is null or (char_length(nickname) between 3 and 20 and nickname ~ '^[[:alnum:] _-]+$')),
  role text check (role in ('student','teacher')),
  class_id uuid references public.classes(id) on delete set null,
  lang_pair text references public.lang_pairs(code),
  points integer not null default 0 check (points >= 0),
  level integer not null default 1 check (level >= 1),
  state text not null default 'idle' check
    (state in ('idle','choosing_nickname','choosing_role','joining_class','choosing_pair','awaiting_correction')),
  current_fragment_pair_id uuid references public.fragment_pairs(id) on delete set null,
  last_skipped_fragment_pair_id uuid references public.fragment_pairs(id) on delete set null,
  current_shown_variant text check (current_shown_variant in ('auto','bad')),
  last_active_date date,
  last_goal_date date,
  created_at timestamptz not null default now()
);
create table if not exists public.answers (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.users(id),
  fragment_pair_id uuid not null references public.fragment_pairs(id),
  shown_variant text not null check (shown_variant in ('auto','bad')),
  action text not null check (action in ('confirm','correct')),
  answer_text text,
  answer_norm text not null,
  caught_planted_error boolean not null default false,
  points_awarded integer not null default 0 check (points_awarded >= 0),
  created_at timestamptz not null default now(),
  unique (user_id, fragment_pair_id)
);
create table if not exists public.config (
  key text primary key,
  value text not null
);
create table if not exists public.badges (
  code text primary key,
  title text not null,
  description text not null
);
create table if not exists public.user_badges (
  user_id uuid not null references public.users(id),
  badge_code text not null references public.badges(code),
  awarded_at timestamptz not null default now(),
  primary key(user_id, badge_code)
);

create index if not exists ix_classes_school on public.classes(school_id);
create index if not exists ix_fragments_source on public.fragments(source_id);
create index if not exists ix_pairs_pair_status on public.fragment_pairs(lang_pair,status);
create index if not exists ix_users_class on public.users(class_id);
create index if not exists ix_answers_fragment on public.answers(fragment_pair_id,answer_norm);
create index if not exists ix_answers_user_date on public.answers(user_id,created_at);
create index if not exists ix_answers_date on public.answers(created_at);

-- RLS включена на ВСЕХ таблицах. Прямого доступа у публичных ролей нет.
alter table public.lang_pairs enable row level security;
alter table public.schools enable row level security;
alter table public.classes enable row level security;
alter table public.sources enable row level security;
alter table public.fragments enable row level security;
alter table public.phrasebook_rows enable row level security;
alter table public.fragment_pairs enable row level security;
alter table public.users enable row level security;
alter table public.answers enable row level security;
alter table public.config enable row level security;
alter table public.badges enable row level security;
alter table public.user_badges enable row level security;

revoke all on table public.lang_pairs, public.schools, public.classes,
  public.sources, public.fragments, public.phrasebook_rows, public.fragment_pairs, public.users,
  public.answers, public.config, public.badges, public.user_badges
  from public, anon, authenticated;
grant select, insert, update, delete on table
  public.lang_pairs, public.schools, public.classes, public.sources,
  public.fragments, public.phrasebook_rows, public.fragment_pairs, public.users, public.answers,
  public.config, public.badges, public.user_badges to service_role;

-- Поля текущей версии; новые объекты и права описаны в logic.sql.
alter table public.users add column if not exists current_shown_at timestamptz;
alter table public.users add column if not exists last_answer_at timestamptz;
alter table public.users add column if not exists reminders_enabled boolean not null default false;
alter table public.users add column if not exists last_reminder_date date;
alter table public.users add column if not exists deleted_at timestamptz;
alter table public.answers add column if not exists shown_at timestamptz;
alter table public.answers add column if not exists eligible boolean not null default true;
alter table public.answers add column if not exists vote_weight numeric(3,2) not null default 1;
alter table public.fragment_pairs add column if not exists resolved_by text
    check (resolved_by is null or resolved_by in ('consensus','expert'));
alter table public.classes add column if not exists created_by_user_id uuid references public.users(id);
