-- ============================================================
-- Who Gets You? — Supabase schema
-- Run this once in the Supabase SQL Editor (Dashboard → SQL Editor → New query).
-- Safe to re-run: it drops and recreates the game tables.
-- ============================================================

-- Clean slate (only these app tables) --------------------------------
drop table if exists guesses cascade;
drop table if exists submissions cascade;
drop table if exists rounds cascade;
drop table if exists players cascade;
drop table if exists rooms cascade;

-- Rooms --------------------------------------------------------------
create table rooms (
  id                uuid primary key default gen_random_uuid(),
  code              text unique not null,
  name              text not null,
  host_id           uuid not null,            -- players.id of the host
  is_private        boolean not null default false,
  started           boolean not null default false,
  settings          jsonb not null default '{"max_score":100,"language":"en","llm_model":"gemini-2.5-flash"}'::jsonb,
  -- transient in-game state (used from Phase 2 onward)
  phase             text,                      -- theme_selection | level_selection | question_generation | answer_entry | guessing | reveal | results
  round             integer not null default 0,
  turn_index        integer not null default 0,
  storyteller_order jsonb not null default '[]'::jsonb,
  selected_theme    text,
  selected_level    text,                      -- shallow | deep
  question          jsonb,                     -- { question, question_en, angle_key }
  winners           jsonb not null default '[]'::jsonb,
  end_reason        text,
  created_at        timestamptz not null default now(),
  updated_at        timestamptz not null default now()
);

create index rooms_code_idx on rooms (code);

-- Players ------------------------------------------------------------
create table players (
  id          uuid primary key default gen_random_uuid(),
  room_id     uuid not null references rooms(id) on delete cascade,
  name        text not null,
  role        text not null default 'joiner',  -- host | joiner
  connected   boolean not null default true,
  score       integer not null default 0,
  joined_at   timestamptz not null default now()
);

create index players_room_idx on players (room_id);

-- Rounds -------------------------------------------------------------
create table rounds (
  id             uuid primary key default gen_random_uuid(),
  room_id        uuid not null references rooms(id) on delete cascade,
  round_no       integer not null,
  storyteller_id uuid,
  theme          text,
  level          text,
  question       jsonb,                         -- { question, question_en, angle_key }
  summary        jsonb,                         -- scoring result for the round
  created_at     timestamptz not null default now(),
  unique (room_id, round_no)
);

create index rounds_room_idx on rounds (room_id);

-- Submissions (one plausible answer per player per round) -------------
create table submissions (
  id             uuid primary key default gen_random_uuid(),
  round_id       uuid not null references rounds(id) on delete cascade,
  player_id      uuid not null,
  text           text not null,
  is_storyteller boolean not null default false,
  created_at     timestamptz not null default now(),
  unique (round_id, player_id)
);

create index submissions_round_idx on submissions (round_id);

-- Guesses (each listener picks one submission as the storyteller's) ---
create table guesses (
  id            uuid primary key default gen_random_uuid(),
  round_id      uuid not null references rounds(id) on delete cascade,
  player_id     uuid not null,
  submission_id uuid not null references submissions(id) on delete cascade,
  created_at    timestamptz not null default now(),
  unique (round_id, player_id)
);

create index guesses_round_idx on guesses (round_id);

-- ============================================================
-- Row Level Security
-- The browser (anon key) only READS — this is what powers Realtime.
-- All writes go through the server (service role key) which bypasses RLS.
-- ============================================================
alter table rooms       enable row level security;
alter table players     enable row level security;
alter table rounds      enable row level security;
alter table submissions enable row level security;
alter table guesses     enable row level security;

create policy "anon read rooms"       on rooms       for select using (true);
create policy "anon read players"     on players     for select using (true);
create policy "anon read rounds"      on rounds      for select using (true);
create policy "anon read submissions" on submissions for select using (true);
create policy "anon read guesses"     on guesses     for select using (true);

-- ============================================================
-- Realtime: broadcast row changes to subscribed clients.
-- ============================================================
alter publication supabase_realtime add table rooms;
alter publication supabase_realtime add table players;
alter publication supabase_realtime add table rounds;
alter publication supabase_realtime add table submissions;
alter publication supabase_realtime add table guesses;
