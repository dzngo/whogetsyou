begin;

create extension if not exists vector;
create extension if not exists pgcrypto;

create schema if not exists qb3;

create table qb3.prompt_snapshots (
  prompt_snapshot_id uuid primary key default gen_random_uuid(),
  registry_snapshot jsonb not null,
  configuration_hash text not null unique,
  created_at timestamptz not null default now()
);

create table qb3.campaigns (
  campaign_id text primary key,
  campaign_name text not null,
  raw_input jsonb not null,
  level_mode text not null check (level_mode in ('shallow', 'deep', 'mixed')),
  accepted_target integer not null check (accepted_target > 0),
  shallow_target integer not null check (shallow_target >= 0),
  deep_target integer not null check (deep_target >= 0),
  accepted_shallow integer not null default 0 check (accepted_shallow >= 0),
  accepted_deep integer not null default 0 check (accepted_deep >= 0),
  authorized_budget_usd numeric(14,6) not null check (authorized_budget_usd > 0),
  spent_usd numeric(14,6) not null default 0 check (spent_usd >= 0),
  reserved_usd numeric(14,6) not null default 0 check (reserved_usd >= 0),
  unknown_spend_usd numeric(14,6) not null default 0 check (unknown_spend_usd >= 0),
  status text not null default 'running' check (
    status in (
      'running', 'completed', 'cancelled_partial', 'budget_exhausted_partial',
      'unknown_spend', 'configuration_error', 'database_error',
      'safety_ceiling_reached'
    )
  ),
  cancel_requested boolean not null default false,
  prompt_snapshot_id uuid not null references qb3.prompt_snapshots(prompt_snapshot_id),
  emergency_batch_ceiling integer not null check (emergency_batch_ceiling > 0),
  next_batch_index integer not null default 1 check (next_batch_index > 0),
  notes text,
  started_at timestamptz not null default now(),
  completed_at timestamptz,
  updated_at timestamptz not null default now(),
  check (shallow_target + deep_target = accepted_target),
  check (
    (level_mode = 'shallow' and shallow_target = accepted_target and deep_target = 0)
    or (level_mode = 'deep' and deep_target = accepted_target and shallow_target = 0)
    or (
      level_mode = 'mixed'
      and shallow_target = floor(accepted_target::numeric / 2)::integer
      and deep_target = accepted_target - shallow_target
    )
  ),
  check (spent_usd + reserved_usd + unknown_spend_usd <= authorized_budget_usd)
);

create table qb3.batches (
  batch_id uuid primary key default gen_random_uuid(),
  campaign_id text not null references qb3.campaigns(campaign_id) on delete restrict,
  batch_index integer not null check (batch_index > 0),
  requested_level_mix jsonb not null,
  distribution_snapshot_id uuid,
  status text not null default 'running' check (
    status in ('running', 'completed', 'cancelled', 'failed')
  ),
  started_at timestamptz not null default now(),
  completed_at timestamptz,
  unique (campaign_id, batch_index)
);

create table qb3.missions (
  mission_id uuid primary key default gen_random_uuid(),
  campaign_id text not null references qb3.campaigns(campaign_id) on delete restrict,
  batch_id uuid not null references qb3.batches(batch_id) on delete restrict,
  mission_slot smallint not null check (mission_slot between 1 and 4),
  level text not null check (level in ('shallow', 'deep')),
  observation_report jsonb not null,
  mission jsonb not null,
  created_at timestamptz not null default now(),
  unique (batch_id, mission_slot)
);

create table qb3.candidates (
  candidate_id uuid primary key default gen_random_uuid(),
  campaign_id text not null references qb3.campaigns(campaign_id) on delete restrict,
  batch_id uuid not null references qb3.batches(batch_id) on delete restrict,
  mission_id uuid not null references qb3.missions(mission_id) on delete restrict,
  candidate_index smallint not null check (candidate_index between 1 and 20),
  question_text text not null check (length(btrim(question_text)) > 2),
  normalized_text text not null,
  level text not null check (level in ('shallow', 'deep')),
  state text not null default 'proposed' check (
    state in (
      'proposed', 'quality_rejected', 'exact_duplicate', 'semantic_duplicate',
      'awaiting_human_review', 'operationally_unresolved', 'accepted'
    )
  ),
  quality_result jsonb,
  semantic_result jsonb,
  metadata_result jsonb,
  embedding vector(1536),
  rejection_reason_codes jsonb not null default '[]'::jsonb,
  feedback_note text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (batch_id, candidate_index)
);

create table qb3.questions (
  question_id uuid primary key default gen_random_uuid(),
  candidate_id uuid not null unique references qb3.candidates(candidate_id) on delete restrict,
  question_text text not null,
  normalized_text text not null unique,
  level text not null check (level in ('shallow', 'deep')),
  embedding vector(1536) not null,
  question_form text check (
    question_form is null
    or question_form in ('direct', 'hypothetical', 'memory', 'reaction', 'choice', 'comparison')
  ),
  scenario_present boolean,
  contrast_present boolean,
  aspect text,
  scenario text,
  perspective text,
  answer_space text,
  contrast text,
  accepted_at timestamptz not null default now(),
  metadata_updated_at timestamptz
);

create table qb3.themes (
  theme_code text primary key,
  display_name text not null unique,
  description jsonb not null default '[]'::jsonb,
  active boolean not null default true,
  created_at timestamptz not null default now()
);

insert into qb3.themes (theme_code, display_name) values
  ('yourself', 'Yourself'),
  ('childhood', 'Childhood'),
  ('family', 'Family'),
  ('goals', 'Goals'),
  ('work', 'Work'),
  ('love', 'Love'),
  ('friends', 'Friends'),
  ('hobbies', 'Hobbies'),
  ('travel', 'Travel')
on conflict (theme_code) do update set display_name = excluded.display_name;

create table qb3.question_themes (
  question_id uuid not null references qb3.questions(question_id) on delete cascade,
  theme_code text not null references qb3.themes(theme_code) on delete restrict,
  created_at timestamptz not null default now(),
  primary key (question_id, theme_code)
);

create table qb3.provider_attempts (
  attempt_id text primary key,
  campaign_id text not null references qb3.campaigns(campaign_id) on delete restrict,
  batch_id uuid references qb3.batches(batch_id) on delete restrict,
  candidate_id uuid references qb3.candidates(candidate_id) on delete restrict,
  parent_attempt_id text references qb3.provider_attempts(attempt_id) on delete restrict,
  agent_role text not null,
  provider text not null,
  requested_model text not null,
  reported_model text,
  reasoning_setting text not null,
  reservation_usd numeric(14,6) not null check (reservation_usd > 0),
  actual_cost_usd numeric(14,6) check (actual_cost_usd >= 0),
  status text not null check (
    status in ('reserved', 'reconciled', 'released', 'unknown_spend', 'reservation_exceeded')
  ),
  usage jsonb,
  sanitized_error jsonb,
  started_at timestamptz not null default now(),
  completed_at timestamptz
);

create table qb3.agent_runs (
  invocation_id text primary key,
  attempt_id text not null unique references qb3.provider_attempts(attempt_id) on delete restrict,
  campaign_id text not null references qb3.campaigns(campaign_id) on delete restrict,
  batch_id uuid references qb3.batches(batch_id) on delete restrict,
  candidate_id uuid references qb3.candidates(candidate_id) on delete restrict,
  mission_id uuid references qb3.missions(mission_id) on delete restrict,
  agent_role text not null,
  prompt_key text not null,
  prompt_version text not null,
  rendered_prompt text not null,
  raw_response text,
  structured_response jsonb,
  status text not null check (status in ('started', 'succeeded', 'schema_failed', 'failed')),
  repair_of_invocation_id text references qb3.agent_runs(invocation_id) on delete restrict,
  started_at timestamptz not null default now(),
  completed_at timestamptz
);

create table qb3.review_queue (
  review_id bigint generated always as identity primary key,
  candidate_id uuid not null references qb3.candidates(candidate_id) on delete restrict,
  review_type text not null check (review_type in ('quality', 'semantic', 'metadata')),
  status text not null default 'open' check (status in ('open', 'accepted', 'rejected', 'dismissed')),
  evidence jsonb not null,
  resolution jsonb,
  created_at timestamptz not null default now(),
  resolved_at timestamptz,
  unique (candidate_id, review_type)
);

create table qb3.distribution_snapshots (
  distribution_snapshot_id uuid primary key default gen_random_uuid(),
  campaign_id text not null references qb3.campaigns(campaign_id) on delete restrict,
  after_batch_id uuid references qb3.batches(batch_id) on delete restrict,
  accepted_total integer not null check (accepted_total >= 0),
  summary jsonb not null,
  created_at timestamptz not null default now()
);

alter table qb3.batches
  add constraint batches_distribution_snapshot_fkey
  foreign key (distribution_snapshot_id)
  references qb3.distribution_snapshots(distribution_snapshot_id)
  on delete set null;

create table qb3.workflow_errors (
  workflow_error_id bigint generated always as identity primary key,
  campaign_id text references qb3.campaigns(campaign_id) on delete restrict,
  workflow_id text,
  execution_id text,
  node_name text,
  sanitized_error jsonb not null,
  created_at timestamptz not null default now()
);

create index batches_campaign_idx on qb3.batches (campaign_id, batch_index);
create index missions_campaign_batch_idx on qb3.missions (campaign_id, batch_id);
create index candidates_campaign_state_idx on qb3.candidates (campaign_id, state, created_at);
create index candidates_batch_idx on qb3.candidates (batch_id, candidate_index);
create index candidates_normalized_idx on qb3.candidates (normalized_text);
create index questions_level_accepted_idx on qb3.questions (level, accepted_at);
create index question_themes_theme_idx on qb3.question_themes (theme_code, question_id);
create index provider_attempts_campaign_status_idx on qb3.provider_attempts (campaign_id, status, started_at);
create index provider_attempts_batch_idx on qb3.provider_attempts (batch_id) where batch_id is not null;
create index provider_attempts_candidate_idx on qb3.provider_attempts (candidate_id) where candidate_id is not null;
create index agent_runs_campaign_started_idx on qb3.agent_runs (campaign_id, started_at);
create index review_queue_open_idx on qb3.review_queue (created_at) where status = 'open';
create index distribution_snapshots_campaign_idx on qb3.distribution_snapshots (campaign_id, created_at desc);
create index questions_embedding_hnsw_idx
  on qb3.questions using hnsw (embedding vector_cosine_ops);

create or replace function qb3.touch_updated_at()
returns trigger
language plpgsql
as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

create trigger campaigns_touch_updated_at
before update on qb3.campaigns
for each row execute function qb3.touch_updated_at();

create trigger candidates_touch_updated_at
before update on qb3.candidates
for each row execute function qb3.touch_updated_at();

create or replace function qb3.normalize_question(p_question text)
returns text
language sql
immutable
strict
as $$
  select btrim(
    regexp_replace(
      regexp_replace(lower(p_question), '[[:punct:]]+', ' ', 'g'),
      '[[:space:]]+',
      ' ',
      'g'
    )
  );
$$;

create or replace function qb3.freeze_prompt_snapshot(p_snapshot jsonb)
returns uuid
language plpgsql
as $$
declare
  v_hash text;
  v_snapshot_id uuid;
begin
  if jsonb_typeof(p_snapshot) <> 'object'
     or jsonb_typeof(p_snapshot -> 'prompts') <> 'array'
     or jsonb_array_length(p_snapshot -> 'prompts') = 0 then
    raise exception 'prompt snapshot must contain a non-empty prompts array';
  end if;

  v_hash := encode(digest(p_snapshot::text, 'sha256'), 'hex');

  insert into qb3.prompt_snapshots (registry_snapshot, configuration_hash)
  values (p_snapshot, v_hash)
  on conflict (configuration_hash) do update
    set configuration_hash = excluded.configuration_hash
  returning prompt_snapshot_id into v_snapshot_id;

  return v_snapshot_id;
end;
$$;

create or replace function qb3.load_frozen_prompt(
  p_campaign_id text,
  p_prompt_key text
)
returns table (prompt jsonb, configuration jsonb, configuration_hash text)
language plpgsql
stable
as $$
begin
  return query
  select p,
         coalesce(ps.registry_snapshot -> 'configuration', '{}'::jsonb),
         ps.configuration_hash
  from qb3.campaigns c
  join qb3.prompt_snapshots ps using (prompt_snapshot_id)
  cross join lateral jsonb_array_elements(ps.registry_snapshot -> 'prompts') p
  where c.campaign_id = p_campaign_id
    and p ->> 'promptKey' = p_prompt_key
    and p ->> 'status' is distinct from 'inactive';

  if not found then
    raise exception 'active prompt % not found for campaign %', p_prompt_key, p_campaign_id;
  end if;
end;
$$;

create or replace function qb3.persist_agent_run(
  p_invocation_id text,
  p_attempt_id text,
  p_campaign_id text,
  p_batch_id uuid,
  p_candidate_id uuid,
  p_mission_id uuid,
  p_agent_role text,
  p_prompt_key text,
  p_prompt_version text,
  p_rendered_prompt text,
  p_raw_response text,
  p_structured_response jsonb,
  p_status text,
  p_repair_of_invocation_id text default null
)
returns setof qb3.agent_runs
language plpgsql
as $$
begin
  insert into qb3.agent_runs (
    invocation_id, attempt_id, campaign_id, batch_id, candidate_id,
    mission_id, agent_role, prompt_key, prompt_version, rendered_prompt,
    raw_response, structured_response, status, repair_of_invocation_id,
    completed_at
  ) values (
    p_invocation_id, p_attempt_id, p_campaign_id, p_batch_id,
    p_candidate_id, p_mission_id, p_agent_role, p_prompt_key,
    p_prompt_version, p_rendered_prompt, p_raw_response,
    p_structured_response, p_status, p_repair_of_invocation_id,
    case when p_status = 'started' then null else now() end
  )
  on conflict (invocation_id) do update set
    raw_response = excluded.raw_response,
    structured_response = excluded.structured_response,
    status = excluded.status,
    completed_at = excluded.completed_at;

  return query
  select a.* from qb3.agent_runs a where a.invocation_id = p_invocation_id;
end;
$$;

create or replace function qb3.create_campaign(
  p_campaign_id text,
  p_campaign_name text,
  p_raw_input jsonb,
  p_level_mode text,
  p_accepted_target integer,
  p_authorized_budget_usd numeric,
  p_prompt_snapshot_id uuid,
  p_emergency_batch_ceiling integer default 100,
  p_notes text default null
)
returns setof qb3.campaigns
language plpgsql
as $$
declare
  v_shallow_target integer;
  v_deep_target integer;
begin
  if p_level_mode not in ('shallow', 'deep', 'mixed') then
    raise exception 'unsupported level mode %', p_level_mode;
  end if;

  if p_accepted_target <= 0 or p_authorized_budget_usd <= 0 then
    raise exception 'accepted target and authorized budget must be positive';
  end if;

  if p_level_mode = 'shallow' then
    v_shallow_target := p_accepted_target;
    v_deep_target := 0;
  elsif p_level_mode = 'deep' then
    v_shallow_target := 0;
    v_deep_target := p_accepted_target;
  else
    v_shallow_target := floor(p_accepted_target::numeric / 2)::integer;
    v_deep_target := p_accepted_target - v_shallow_target;
  end if;

  insert into qb3.campaigns (
    campaign_id, campaign_name, raw_input, level_mode, accepted_target,
    shallow_target, deep_target, authorized_budget_usd, prompt_snapshot_id,
    emergency_batch_ceiling, notes
  ) values (
    p_campaign_id, p_campaign_name, p_raw_input, p_level_mode,
    p_accepted_target, v_shallow_target, v_deep_target,
    p_authorized_budget_usd, p_prompt_snapshot_id,
    p_emergency_batch_ceiling, p_notes
  )
  on conflict (campaign_id) do nothing;

  return query
  select c.* from qb3.campaigns c where c.campaign_id = p_campaign_id;
end;
$$;

create or replace function qb3.begin_next_batch(p_campaign_id text)
returns setof qb3.batches
language plpgsql
as $$
declare
  v_campaign qb3.campaigns%rowtype;
  v_mix jsonb;
  v_batch_id uuid;
begin
  select * into v_campaign
  from qb3.campaigns
  where campaign_id = p_campaign_id
  for update;

  if not found then
    raise exception 'campaign % not found', p_campaign_id;
  end if;

  return query
  select b.*
  from qb3.batches b
  where b.campaign_id = p_campaign_id and b.status = 'running'
  order by b.batch_index desc
  limit 1;

  if found then
    return;
  end if;

  if v_campaign.status <> 'running' or v_campaign.cancel_requested then
    raise exception 'campaign % is not available for a new batch', p_campaign_id;
  end if;

  if v_campaign.next_batch_index > v_campaign.emergency_batch_ceiling then
    update qb3.campaigns
    set status = 'safety_ceiling_reached', completed_at = now()
    where campaign_id = p_campaign_id;
    raise exception 'campaign % reached its emergency batch ceiling', p_campaign_id;
  end if;

  if v_campaign.accepted_shallow >= v_campaign.shallow_target
     and v_campaign.accepted_deep >= v_campaign.deep_target then
    update qb3.campaigns
    set status = 'completed', completed_at = now()
    where campaign_id = p_campaign_id;
    raise exception 'campaign % is already complete', p_campaign_id;
  end if;

  if v_campaign.accepted_shallow >= v_campaign.shallow_target then
    v_mix := jsonb_build_object('shallow', 0, 'deep', 20);
  elsif v_campaign.accepted_deep >= v_campaign.deep_target then
    v_mix := jsonb_build_object('shallow', 20, 'deep', 0);
  elsif v_campaign.level_mode = 'mixed' then
    v_mix := jsonb_build_object('shallow', 10, 'deep', 10);
  elsif v_campaign.level_mode = 'shallow' then
    v_mix := jsonb_build_object('shallow', 20, 'deep', 0);
  else
    v_mix := jsonb_build_object('shallow', 0, 'deep', 20);
  end if;

  insert into qb3.batches (campaign_id, batch_index, requested_level_mix)
  values (p_campaign_id, v_campaign.next_batch_index, v_mix)
  returning batch_id into v_batch_id;

  update qb3.campaigns
  set next_batch_index = next_batch_index + 1
  where campaign_id = p_campaign_id;

  return query select b.* from qb3.batches b where b.batch_id = v_batch_id;
end;
$$;

create or replace function qb3.request_campaign_cancel(p_campaign_id text)
returns setof qb3.campaigns
language plpgsql
as $$
begin
  update qb3.campaigns
  set cancel_requested = true
  where campaign_id = p_campaign_id;

  if not found then
    raise exception 'campaign % not found', p_campaign_id;
  end if;

  return query
  select c.* from qb3.campaigns c where c.campaign_id = p_campaign_id;
end;
$$;

create or replace function qb3.resume_campaign(
  p_campaign_id text,
  p_additional_budget_usd numeric
)
returns setof qb3.campaigns
language plpgsql
as $$
declare
  v_campaign qb3.campaigns%rowtype;
begin
  if p_additional_budget_usd <= 0 then
    raise exception 'additional spending authorization must be positive';
  end if;

  select * into v_campaign
  from qb3.campaigns
  where campaign_id = p_campaign_id
  for update;

  if not found then
    raise exception 'campaign % not found', p_campaign_id;
  end if;

  if v_campaign.status in ('completed', 'configuration_error', 'database_error', 'safety_ceiling_reached') then
    raise exception 'campaign % cannot resume from status %', p_campaign_id, v_campaign.status;
  end if;

  if v_campaign.reserved_usd <> 0 or v_campaign.unknown_spend_usd <> 0 then
    raise exception 'campaign % has unresolved provider accounting', p_campaign_id;
  end if;

  update qb3.campaigns
  set authorized_budget_usd = authorized_budget_usd + p_additional_budget_usd,
      cancel_requested = false,
      status = 'running',
      completed_at = null
  where campaign_id = p_campaign_id;

  return query
  select c.* from qb3.campaigns c where c.campaign_id = p_campaign_id;
end;
$$;

create or replace function qb3.preflight_candidate(p_candidate_id uuid)
returns table (
  exact_duplicate boolean,
  matched_question_id uuid,
  normalized_text text
)
language plpgsql
as $$
declare
  v_candidate qb3.candidates%rowtype;
begin
  select * into v_candidate
  from qb3.candidates
  where candidate_id = p_candidate_id
  for update;

  if not found then
    raise exception 'candidate % not found', p_candidate_id;
  end if;

  update qb3.candidates
  set normalized_text = qb3.normalize_question(question_text)
  where candidate_id = p_candidate_id
  returning qb3.candidates.normalized_text into v_candidate.normalized_text;

  select q.question_id into matched_question_id
  from qb3.questions q
  where q.normalized_text = v_candidate.normalized_text
  limit 1;

  exact_duplicate := matched_question_id is not null;
  normalized_text := v_candidate.normalized_text;

  if exact_duplicate then
    update qb3.candidates
    set state = 'exact_duplicate',
        rejection_reason_codes = '["exact_normalized_duplicate"]'::jsonb,
        feedback_note = 'Exact normalized duplicate'
    where candidate_id = p_candidate_id;
  end if;

  return next;
end;
$$;

create or replace function qb3.persist_mission_and_candidates(
  p_campaign_id text,
  p_batch_id uuid,
  p_mission_slot integer,
  p_level text,
  p_observation_report jsonb,
  p_mission jsonb,
  p_questions jsonb
)
returns table (mission_id uuid, candidate_id uuid, candidate_index smallint, question_text text)
language plpgsql
as $$
declare
  v_mission_id uuid;
begin
  if p_mission_slot not between 1 and 4 then
    raise exception 'mission slot must be between 1 and 4';
  end if;

  if jsonb_typeof(p_questions) <> 'array' or jsonb_array_length(p_questions) <> 5 then
    raise exception 'a Creative invocation must contain exactly five questions';
  end if;

  insert into qb3.missions (
    campaign_id, batch_id, mission_slot, level, observation_report, mission
  ) values (
    p_campaign_id, p_batch_id, p_mission_slot, p_level,
    p_observation_report, p_mission
  )
  on conflict (batch_id, mission_slot) do update
    set observation_report = excluded.observation_report,
        mission = excluded.mission
  returning qb3.missions.mission_id into v_mission_id;

  insert into qb3.candidates (
    campaign_id, batch_id, mission_id, candidate_index,
    question_text, normalized_text, level
  )
  select p_campaign_id, p_batch_id, v_mission_id,
         (((p_mission_slot - 1) * 5) + q.ordinality)::smallint,
         q.question_text,
         qb3.normalize_question(q.question_text),
         p_level
  from jsonb_array_elements_text(p_questions) with ordinality q(question_text, ordinality)
  on conflict on constraint candidates_batch_id_candidate_index_key do nothing;

  return query
  select c.mission_id, c.candidate_id, c.candidate_index, c.question_text
  from qb3.candidates c
  where c.batch_id = p_batch_id and c.mission_id = v_mission_id
  order by c.candidate_index;
end;
$$;

create or replace function qb3.reserve_provider_budget(
  p_attempt_id text,
  p_campaign_id text,
  p_batch_id uuid,
  p_candidate_id uuid,
  p_parent_attempt_id text,
  p_agent_role text,
  p_provider text,
  p_requested_model text,
  p_reasoning_setting text,
  p_reservation_usd numeric
)
returns table (
  reserved boolean,
  reason text,
  remaining_usd numeric,
  cached_result jsonb
)
language plpgsql
as $$
declare
  v_campaign qb3.campaigns%rowtype;
  v_attempt qb3.provider_attempts%rowtype;
  v_cached_result jsonb;
begin
  if p_reservation_usd <= 0 then
    raise exception 'reservation must be positive';
  end if;

  select * into v_campaign
  from qb3.campaigns
  where campaign_id = p_campaign_id
  for update;

  if not found then
    raise exception 'campaign % not found', p_campaign_id;
  end if;

  select * into v_attempt
  from qb3.provider_attempts
  where attempt_id = p_attempt_id;

  if found then
    if v_attempt.campaign_id <> p_campaign_id
      or v_attempt.reservation_usd <> p_reservation_usd
      or v_attempt.agent_role <> p_agent_role
      or v_attempt.requested_model <> p_requested_model then
      raise exception 'attempt id % reused with different parameters', p_attempt_id;
    end if;
    select jsonb_build_object(
      'invocation_id', a.invocation_id,
      'attempt_id', a.attempt_id,
      'structured_response', a.structured_response,
      'raw_response', a.raw_response,
      'status', a.status,
      'repair_of_invocation_id', a.repair_of_invocation_id
    )
    into v_cached_result
    from qb3.agent_runs a
    where a.attempt_id = p_attempt_id;

    if v_cached_result is null
       and v_attempt.agent_role = 'embedding'
       and v_attempt.status = 'reconciled' then
      select jsonb_build_object(
        'status', 'succeeded',
        'candidate_id', c.candidate_id,
        'neighbours', coalesce((
          select jsonb_agg(to_jsonb(n) order by n.cosine_distance)
          from (
            select q.question_id, q.question_text, q.level,
                   (q.embedding <=> c.embedding)::double precision as cosine_distance
            from qb3.questions q
            order by q.embedding <=> c.embedding
            limit 10
          ) n
        ), '[]'::jsonb)
      )
      into v_cached_result
      from qb3.candidates c
      where c.candidate_id = v_attempt.candidate_id
        and c.embedding is not null;
    end if;

    return query select
      v_attempt.status = 'reserved' and v_cached_result is null,
      'idempotent_' || v_attempt.status,
      v_campaign.authorized_budget_usd
        - v_campaign.spent_usd
        - v_campaign.reserved_usd
        - v_campaign.unknown_spend_usd,
      v_cached_result;
    return;
  end if;

  if v_campaign.cancel_requested or v_campaign.status <> 'running' then
    return query select false, 'campaign_not_running',
      v_campaign.authorized_budget_usd
        - v_campaign.spent_usd
        - v_campaign.reserved_usd
        - v_campaign.unknown_spend_usd,
      null::jsonb;
    return;
  end if;

  if v_campaign.spent_usd + v_campaign.reserved_usd
      + v_campaign.unknown_spend_usd + p_reservation_usd
      > v_campaign.authorized_budget_usd then
    if v_campaign.reserved_usd = 0 then
      update qb3.campaigns
      set status = 'budget_exhausted_partial', completed_at = now()
      where campaign_id = p_campaign_id;
    end if;
    return query select false, 'insufficient_budget',
      v_campaign.authorized_budget_usd
        - v_campaign.spent_usd
        - v_campaign.reserved_usd
        - v_campaign.unknown_spend_usd,
      null::jsonb;
    return;
  end if;

  insert into qb3.provider_attempts (
    attempt_id, campaign_id, batch_id, candidate_id, parent_attempt_id,
    agent_role, provider, requested_model, reasoning_setting,
    reservation_usd, status
  ) values (
    p_attempt_id, p_campaign_id, p_batch_id, p_candidate_id,
    p_parent_attempt_id, p_agent_role, p_provider, p_requested_model,
    p_reasoning_setting, p_reservation_usd, 'reserved'
  );

  update qb3.campaigns
  set reserved_usd = reserved_usd + p_reservation_usd
  where campaign_id = p_campaign_id;

  return query select true, 'reserved',
    v_campaign.authorized_budget_usd
      - v_campaign.spent_usd
      - v_campaign.reserved_usd
      - v_campaign.unknown_spend_usd
      - p_reservation_usd,
    null::jsonb;
end;
$$;

create or replace function qb3.reconcile_provider_attempt(
  p_attempt_id text,
  p_actual_cost_usd numeric,
  p_reported_model text,
  p_usage jsonb
)
returns table (status text, spent_usd numeric, reserved_usd numeric, unknown_spend_usd numeric)
language plpgsql
as $$
declare
  v_attempt qb3.provider_attempts%rowtype;
begin
  if p_actual_cost_usd < 0 then
    raise exception 'actual cost cannot be negative';
  end if;

  select * into v_attempt
  from qb3.provider_attempts
  where attempt_id = p_attempt_id
  for update;

  if not found then
    raise exception 'attempt % not found', p_attempt_id;
  end if;

  if v_attempt.status = 'reconciled' then
    if v_attempt.actual_cost_usd <> p_actual_cost_usd then
      raise exception 'attempt % reconciled with a different cost', p_attempt_id;
    end if;
  elsif v_attempt.status <> 'reserved' then
    raise exception 'attempt % cannot reconcile from status %', p_attempt_id, v_attempt.status;
  elsif p_actual_cost_usd > v_attempt.reservation_usd then
    update qb3.provider_attempts
    set status = 'reservation_exceeded', actual_cost_usd = p_actual_cost_usd,
        reported_model = p_reported_model, usage = p_usage, completed_at = now()
    where attempt_id = p_attempt_id;

    update qb3.campaigns c
    set reserved_usd = c.reserved_usd - v_attempt.reservation_usd,
        spent_usd = c.spent_usd + v_attempt.reservation_usd,
        unknown_spend_usd = c.unknown_spend_usd
          + (p_actual_cost_usd - v_attempt.reservation_usd),
        status = 'configuration_error'
    where c.campaign_id = v_attempt.campaign_id;
  else
    update qb3.provider_attempts
    set status = 'reconciled', actual_cost_usd = p_actual_cost_usd,
        reported_model = p_reported_model, usage = p_usage, completed_at = now()
    where attempt_id = p_attempt_id;

    update qb3.campaigns c
    set reserved_usd = c.reserved_usd - v_attempt.reservation_usd,
        spent_usd = c.spent_usd + p_actual_cost_usd
    where c.campaign_id = v_attempt.campaign_id;
  end if;

  return query
  select c.status, c.spent_usd, c.reserved_usd, c.unknown_spend_usd
  from qb3.campaigns c
  where c.campaign_id = v_attempt.campaign_id;
end;
$$;

create or replace function qb3.release_provider_attempt(
  p_attempt_id text,
  p_sanitized_error jsonb default null
)
returns table (status text, reserved_usd numeric)
language plpgsql
as $$
declare
  v_attempt qb3.provider_attempts%rowtype;
begin
  select * into v_attempt
  from qb3.provider_attempts
  where attempt_id = p_attempt_id
  for update;

  if not found then
    raise exception 'attempt % not found', p_attempt_id;
  end if;

  if v_attempt.status = 'reserved' then
    update qb3.provider_attempts
    set status = 'released', sanitized_error = p_sanitized_error, completed_at = now()
    where attempt_id = p_attempt_id;

    update qb3.campaigns c
    set reserved_usd = c.reserved_usd - v_attempt.reservation_usd
    where c.campaign_id = v_attempt.campaign_id;
  elsif v_attempt.status <> 'released' then
    raise exception 'attempt % cannot release from status %', p_attempt_id, v_attempt.status;
  end if;

  return query
  select c.status, c.reserved_usd
  from qb3.campaigns c
  where c.campaign_id = v_attempt.campaign_id;
end;
$$;

create or replace function qb3.mark_provider_attempt_unknown(
  p_attempt_id text,
  p_sanitized_error jsonb
)
returns table (status text, reserved_usd numeric, unknown_spend_usd numeric)
language plpgsql
as $$
declare
  v_attempt qb3.provider_attempts%rowtype;
begin
  select * into v_attempt
  from qb3.provider_attempts
  where attempt_id = p_attempt_id
  for update;

  if not found then
    raise exception 'attempt % not found', p_attempt_id;
  end if;

  if v_attempt.status = 'reserved' then
    update qb3.provider_attempts
    set status = 'unknown_spend', sanitized_error = p_sanitized_error, completed_at = now()
    where attempt_id = p_attempt_id;

    update qb3.campaigns c
    set reserved_usd = c.reserved_usd - v_attempt.reservation_usd,
        unknown_spend_usd = c.unknown_spend_usd + v_attempt.reservation_usd,
        status = 'unknown_spend'
    where c.campaign_id = v_attempt.campaign_id;
  elsif v_attempt.status <> 'unknown_spend' then
    raise exception 'attempt % cannot become unknown from status %', p_attempt_id, v_attempt.status;
  end if;

  return query
  select c.status, c.reserved_usd, c.unknown_spend_usd
  from qb3.campaigns c
  where c.campaign_id = v_attempt.campaign_id;
end;
$$;

create or replace function qb3.find_nearest_questions(
  p_embedding vector(1536),
  p_limit integer default 10
)
returns table (
  question_id uuid,
  question_text text,
  level text,
  cosine_distance double precision
)
language sql
stable
as $$
  select q.question_id, q.question_text, q.level,
         (q.embedding <=> p_embedding)::double precision
  from qb3.questions q
  order by q.embedding <=> p_embedding
  limit least(greatest(p_limit, 0), 10);
$$;

create or replace function qb3.store_candidate_embedding_and_find(
  p_candidate_id uuid,
  p_embedding vector(1536)
)
returns table (candidate_id uuid, neighbours jsonb)
language plpgsql
as $$
begin
  update qb3.candidates c
  set embedding = p_embedding
  where c.candidate_id = p_candidate_id;

  if not found then
    raise exception 'candidate % not found', p_candidate_id;
  end if;

  return query
  select p_candidate_id,
         coalesce(jsonb_agg(to_jsonb(n) order by n.cosine_distance), '[]'::jsonb)
  from qb3.find_nearest_questions(p_embedding, 10) n;
end;
$$;

create or replace function qb3.accept_candidate(p_candidate_id uuid)
returns table (accepted boolean, question_id uuid, reason text)
language plpgsql
as $$
declare
  v_candidate qb3.candidates%rowtype;
  v_question_id uuid;
begin
  select * into v_candidate
  from qb3.candidates
  where candidate_id = p_candidate_id
  for update;

  if not found then
    raise exception 'candidate % not found', p_candidate_id;
  end if;

  select q.question_id into v_question_id
  from qb3.questions q
  where q.candidate_id = p_candidate_id;

  if found then
    return query select true, v_question_id, 'idempotent_accepted';
    return;
  end if;

  if v_candidate.state <> 'proposed' then
    return query select false, null::uuid, 'candidate_not_proposed';
    return;
  end if;

  if v_candidate.embedding is null then
    return query select false, null::uuid, 'embedding_missing';
    return;
  end if;

  if exists (
    select 1 from qb3.questions q
    where q.normalized_text = v_candidate.normalized_text
  ) then
    update qb3.candidates
    set state = 'exact_duplicate', feedback_note = 'Exact normalized duplicate'
    where candidate_id = p_candidate_id;
    return query select false, null::uuid, 'exact_duplicate';
    return;
  end if;

  insert into qb3.questions (
    candidate_id, question_text, normalized_text, level, embedding
  ) values (
    v_candidate.candidate_id, v_candidate.question_text,
    v_candidate.normalized_text, v_candidate.level, v_candidate.embedding
  ) returning qb3.questions.question_id into v_question_id;

  update qb3.candidates
  set state = 'accepted'
  where candidate_id = p_candidate_id;

  update qb3.campaigns
  set accepted_shallow = accepted_shallow
        + case when v_candidate.level = 'shallow' then 1 else 0 end,
      accepted_deep = accepted_deep
        + case when v_candidate.level = 'deep' then 1 else 0 end
  where campaign_id = v_candidate.campaign_id;

  return query select true, v_question_id, 'accepted';
exception
  when unique_violation then
    update qb3.candidates
    set state = 'exact_duplicate', feedback_note = 'Exact normalized duplicate'
    where candidate_id = p_candidate_id;
    return query select false, null::uuid, 'exact_duplicate';
end;
$$;

create or replace function qb3.apply_candidate_decision(
  p_candidate_id uuid,
  p_decision text,
  p_reason_codes jsonb default '[]'::jsonb,
  p_feedback_note text default null,
  p_stage_result jsonb default null
)
returns table (state text, accepted_question_id uuid)
language plpgsql
as $$
declare
  v_question_id uuid;
begin
  if p_decision not in (
    'quality_rejected', 'exact_duplicate', 'semantic_duplicate',
    'awaiting_human_review', 'operationally_unresolved', 'accepted'
  ) then
    raise exception 'unsupported candidate decision %', p_decision;
  end if;

  if p_decision = 'accepted' then
    select a.question_id into v_question_id
    from qb3.accept_candidate(p_candidate_id) a
    where a.accepted;
  else
    update qb3.candidates c
    set state = p_decision,
        rejection_reason_codes = coalesce(p_reason_codes, '[]'::jsonb),
        feedback_note = p_feedback_note,
        quality_result = case
          when p_decision = 'quality_rejected' then p_stage_result
          else c.quality_result
        end,
        semantic_result = case
          when p_decision in ('semantic_duplicate', 'awaiting_human_review')
            then p_stage_result
          else c.semantic_result
        end
    where c.candidate_id = p_candidate_id;

    if not found then
      raise exception 'candidate % not found', p_candidate_id;
    end if;

    if p_decision = 'awaiting_human_review' then
      insert into qb3.review_queue (
        candidate_id, review_type, evidence
      ) values (
        p_candidate_id,
        case
          when p_stage_result ? 'semantic_verdict' then 'semantic'
          else 'quality'
        end,
        coalesce(p_stage_result, '{}'::jsonb)
      ) on conflict (candidate_id, review_type) do nothing;
    end if;
  end if;

  return query
  select c.state, v_question_id
  from qb3.candidates c
  where c.candidate_id = p_candidate_id;
end;
$$;

create or replace function qb3.apply_question_metadata(
  p_candidate_id uuid,
  p_metadata jsonb
)
returns table (question_id uuid, theme_codes text[])
language plpgsql
as $$
declare
  v_question_id uuid;
  v_theme_codes text[];
begin
  select q.question_id into v_question_id
  from qb3.questions q
  where q.candidate_id = p_candidate_id
  for update;

  if not found then
    raise exception 'accepted question for candidate % not found', p_candidate_id;
  end if;

  select coalesce(array_agg(value order by value), '{}'::text[])
  into v_theme_codes
  from jsonb_array_elements_text(coalesce(p_metadata -> 'themes', '[]'::jsonb));

  if exists (
    select 1 from unnest(v_theme_codes) code
    where not exists (
      select 1 from qb3.themes t where t.theme_code = code and t.active
    )
  ) then
    raise exception 'metadata contains an unknown or inactive theme';
  end if;

  update qb3.questions q
  set question_form = nullif(p_metadata ->> 'question_form', ''),
      scenario_present = (p_metadata ->> 'scenario_present')::boolean,
      contrast_present = (p_metadata ->> 'contrast_present')::boolean,
      aspect = nullif(p_metadata ->> 'aspect', ''),
      scenario = nullif(p_metadata ->> 'scenario', ''),
      perspective = nullif(p_metadata ->> 'perspective', ''),
      answer_space = nullif(p_metadata ->> 'answer_space', ''),
      contrast = nullif(p_metadata ->> 'contrast', ''),
      metadata_updated_at = now()
  where q.question_id = v_question_id;

  delete from qb3.question_themes qt where qt.question_id = v_question_id;
  insert into qb3.question_themes (question_id, theme_code)
  select v_question_id, code from unnest(v_theme_codes) code;

  return query select v_question_id, v_theme_codes;
end;
$$;

create or replace function qb3.initialize_campaign(
  p_campaign_id text,
  p_campaign_name text,
  p_raw_input jsonb,
  p_level_mode text,
  p_accepted_target integer,
  p_authorized_budget_usd numeric,
  p_configuration_snapshot jsonb,
  p_emergency_batch_ceiling integer default 100,
  p_notes text default null
)
returns setof qb3.campaigns
language plpgsql
as $$
declare
  v_snapshot_id uuid;
begin
  v_snapshot_id := qb3.freeze_prompt_snapshot(p_configuration_snapshot);
  return query
  select * from qb3.create_campaign(
    p_campaign_id, p_campaign_name, p_raw_input, p_level_mode,
    p_accepted_target, p_authorized_budget_usd, v_snapshot_id,
    p_emergency_batch_ceiling, p_notes
  );
end;
$$;

create or replace function qb3.get_quality_groups(
  p_batch_id uuid,
  p_only_uncertain boolean default false
)
returns table (group_index integer, candidates jsonb)
language sql
stable
as $$
  with eligible as (
    select c.*,
           ((row_number() over (order by c.candidate_index) - 1) / 10)::integer + 1 as group_index
    from qb3.candidates c
    where c.batch_id = p_batch_id
      and c.state = 'proposed'
      and (
        (not p_only_uncertain and c.quality_result is null)
        or (p_only_uncertain and c.quality_result ->> 'verdict' = 'uncertain')
      )
  )
  select e.group_index,
         jsonb_agg(jsonb_build_object(
           'candidate_id', e.candidate_id,
           'question', e.question_text,
           'level', e.level,
           'previous_quality_result', e.quality_result
         ) order by e.candidate_index)
  from eligible e
  group by e.group_index
  order by e.group_index;
$$;

create or replace function qb3.apply_quality_results(
  p_batch_id uuid,
  p_decisions jsonb,
  p_escalation boolean default false
)
returns table (candidate_id uuid, state text, verdict text)
language plpgsql
as $$
declare
  v_decision jsonb;
  v_candidate qb3.candidates%rowtype;
begin
  if jsonb_typeof(p_decisions) <> 'array' then
    raise exception 'quality decisions must be an array';
  end if;

  for v_decision in select value from jsonb_array_elements(p_decisions)
  loop
    select * into v_candidate
    from qb3.candidates c
    where c.candidate_id = (v_decision ->> 'candidate_id')::uuid
      and c.batch_id = p_batch_id
    for update;

    if not found then
      raise exception 'quality decision references a candidate outside batch %', p_batch_id;
    end if;

    if v_decision ->> 'verdict' not in ('pass', 'reject', 'uncertain') then
      raise exception 'unsupported quality verdict %', v_decision ->> 'verdict';
    end if;

    update qb3.candidates c
    set quality_result = v_decision || jsonb_build_object('escalated', p_escalation),
        state = case
          when v_decision ->> 'verdict' = 'reject' then 'quality_rejected'
          when p_escalation and v_decision ->> 'verdict' = 'uncertain' then 'awaiting_human_review'
          else c.state
        end,
        rejection_reason_codes = case
          when v_decision ->> 'verdict' = 'reject'
            or (p_escalation and v_decision ->> 'verdict' = 'uncertain')
          then coalesce(v_decision -> 'reason_codes', '[]'::jsonb)
          else c.rejection_reason_codes
        end,
        feedback_note = case
          when v_decision ->> 'verdict' <> 'pass' then v_decision ->> 'feedback_note'
          else c.feedback_note
        end
    where c.candidate_id = v_candidate.candidate_id;

    if p_escalation and v_decision ->> 'verdict' = 'uncertain' then
      insert into qb3.review_queue (candidate_id, review_type, evidence)
      values (v_candidate.candidate_id, 'quality', v_decision)
      on conflict on constraint review_queue_candidate_id_review_type_key do nothing;
    end if;
  end loop;

  return query
  select c.candidate_id, c.state, c.quality_result ->> 'verdict'
  from qb3.candidates c
  where c.batch_id = p_batch_id
  order by c.candidate_index;
end;
$$;

create or replace function qb3.get_preflight_candidates(p_batch_id uuid)
returns table (candidate_id uuid, question_text text, level text)
language sql
stable
as $$
  select c.candidate_id, c.question_text, c.level
  from qb3.candidates c
  where c.batch_id = p_batch_id
    and c.state = 'proposed'
    and c.quality_result ->> 'verdict' = 'pass'
  order by c.candidate_index;
$$;

create or replace function qb3.get_semantic_groups(p_batch_id uuid)
returns table (group_index integer, candidates jsonb)
language sql
stable
as $$
  with eligible as (
    select c.*,
           ((row_number() over (order by c.candidate_index) - 1) / 5)::integer + 1 as group_index
    from qb3.candidates c
    where c.batch_id = p_batch_id
      and c.state = 'proposed'
      and c.quality_result ->> 'verdict' = 'pass'
      and c.embedding is not null
      and c.semantic_result is null
  )
  select e.group_index,
         jsonb_agg(jsonb_build_object(
           'candidate_id', e.candidate_id,
           'question', e.question_text,
           'level', e.level,
           'nearest_questions', coalesce((
             select jsonb_agg(to_jsonb(n) order by n.cosine_distance)
             from qb3.find_nearest_questions(e.embedding, 10) n
           ), '[]'::jsonb)
         ) order by e.candidate_index)
  from eligible e
  group by e.group_index
  order by e.group_index;
$$;

create or replace function qb3.apply_semantic_results(
  p_batch_id uuid,
  p_decisions jsonb
)
returns table (candidate_id uuid, state text, accepted_question_id uuid)
language plpgsql
as $$
declare
  v_decision jsonb;
  v_candidate_id uuid;
  v_question_id uuid;
begin
  if jsonb_typeof(p_decisions) <> 'array' then
    raise exception 'semantic decisions must be an array';
  end if;

  for v_decision in select value from jsonb_array_elements(p_decisions)
  loop
    v_candidate_id := (v_decision ->> 'candidate_id')::uuid;
    if not exists (
      select 1 from qb3.candidates c
      where c.candidate_id = v_candidate_id and c.batch_id = p_batch_id
        and c.state = 'proposed' and c.embedding is not null
    ) then
      raise exception 'semantic decision references an ineligible candidate';
    end if;

    if v_decision ->> 'verdict' = 'distinct' then
      update qb3.candidates set semantic_result = v_decision
      where qb3.candidates.candidate_id = v_candidate_id;
      select a.question_id into v_question_id
      from qb3.accept_candidate(v_candidate_id) a where a.accepted;
    elsif v_decision ->> 'verdict' = 'duplicate' then
      perform * from qb3.apply_candidate_decision(
        v_candidate_id, 'semantic_duplicate',
        coalesce(v_decision -> 'reason_codes', '[]'::jsonb),
        v_decision ->> 'feedback_note', v_decision
      );
      v_question_id := null;
    elsif v_decision ->> 'verdict' = 'uncertain' then
      perform * from qb3.apply_candidate_decision(
        v_candidate_id, 'awaiting_human_review',
        coalesce(v_decision -> 'reason_codes', '[]'::jsonb),
        v_decision ->> 'feedback_note', v_decision
      );
      v_question_id := null;
    else
      raise exception 'unsupported semantic verdict %', v_decision ->> 'verdict';
    end if;
  end loop;

  return query
  select c.candidate_id, c.state, q.question_id
  from qb3.candidates c
  left join qb3.questions q using (candidate_id)
  where c.batch_id = p_batch_id
  order by c.candidate_index;
end;
$$;

create or replace function qb3.get_metadata_group(p_batch_id uuid)
returns table (questions jsonb, themes jsonb)
language sql
stable
as $$
  select coalesce(jsonb_agg(jsonb_build_object(
           'candidate_id', c.candidate_id,
           'question', c.question_text,
           'level', c.level
         ) order by c.candidate_index) filter (where c.candidate_id is not null), '[]'::jsonb),
         (select coalesce(jsonb_agg(jsonb_build_object(
            'theme_code', t.theme_code,
            'display_name', t.display_name,
            'description', t.description
          ) order by t.display_name), '[]'::jsonb)
          from qb3.themes t where t.active)
  from qb3.candidates c
  join qb3.questions q using (candidate_id)
  where c.batch_id = p_batch_id and c.metadata_result is null;
$$;

create or replace function qb3.apply_metadata_results(
  p_batch_id uuid,
  p_items jsonb
)
returns table (candidate_id uuid, question_id uuid)
language plpgsql
as $$
declare
  v_item jsonb;
begin
  if jsonb_typeof(p_items) <> 'array' then
    raise exception 'metadata items must be an array';
  end if;

  for v_item in select value from jsonb_array_elements(p_items)
  loop
    if not exists (
      select 1 from qb3.candidates c
      where c.candidate_id = (v_item ->> 'candidate_id')::uuid
        and c.batch_id = p_batch_id and c.state = 'accepted'
    ) then
      raise exception 'metadata references a candidate outside accepted batch rows';
    end if;

    perform * from qb3.apply_question_metadata((v_item ->> 'candidate_id')::uuid, v_item);
    update qb3.candidates c set metadata_result = v_item
    where c.candidate_id = (v_item ->> 'candidate_id')::uuid;
  end loop;

  return query
  select c.candidate_id, q.question_id
  from qb3.candidates c join qb3.questions q using (candidate_id)
  where c.batch_id = p_batch_id
  order by c.candidate_index;
end;
$$;

create or replace function qb3.mark_batch_operationally_unresolved(
  p_batch_id uuid,
  p_stage text,
  p_reason text
)
returns integer
language plpgsql
as $$
declare
  v_count integer;
begin
  update qb3.candidates c
  set state = 'operationally_unresolved',
      rejection_reason_codes = jsonb_build_array('provider_failure_' || p_stage),
      feedback_note = left(p_reason, 500)
  where c.batch_id = p_batch_id and c.state = 'proposed';
  get diagnostics v_count = row_count;
  return v_count;
end;
$$;

create or replace function qb3.mark_candidates_operationally_unresolved(
  p_batch_id uuid,
  p_candidate_ids jsonb,
  p_stage text,
  p_reason text
)
returns table (candidate_id uuid, state text)
language plpgsql
as $$
begin
  if jsonb_typeof(p_candidate_ids) <> 'array' then
    raise exception 'candidate ids must be an array';
  end if;

  return query
  update qb3.candidates c
  set state = 'operationally_unresolved',
      rejection_reason_codes = jsonb_build_array('provider_failure_' || p_stage),
      feedback_note = left(p_reason, 500)
  where c.batch_id = p_batch_id
    and c.state = 'proposed'
    and c.candidate_id in (
      select value::uuid from jsonb_array_elements_text(p_candidate_ids)
    )
  returning c.candidate_id, c.state;
end;
$$;

create or replace function qb3.complete_batch(p_batch_id uuid)
returns table (campaign_status text, distribution_snapshot_id uuid)
language plpgsql
as $$
declare
  v_campaign_id text;
  v_snapshot_id uuid;
begin
  update qb3.batches b
  set status = 'completed', completed_at = coalesce(completed_at, now())
  where b.batch_id = p_batch_id
  returning b.campaign_id into v_campaign_id;

  if not found then
    raise exception 'batch % not found', p_batch_id;
  end if;

  update qb3.campaigns c
  set status = case
        when c.accepted_shallow >= c.shallow_target
          and c.accepted_deep >= c.deep_target then 'completed'
        when c.cancel_requested then 'cancelled_partial'
        when c.spent_usd + c.reserved_usd + c.unknown_spend_usd
          >= c.authorized_budget_usd then 'budget_exhausted_partial'
        else c.status
      end,
      completed_at = case
        when (c.accepted_shallow >= c.shallow_target and c.accepted_deep >= c.deep_target)
          or c.cancel_requested
          or c.spent_usd + c.reserved_usd + c.unknown_spend_usd >= c.authorized_budget_usd
        then now() else c.completed_at end
  where c.campaign_id = v_campaign_id;

  v_snapshot_id := qb3.refresh_distribution_snapshot(v_campaign_id, p_batch_id);

  return query
  select c.status, v_snapshot_id
  from qb3.campaigns c where c.campaign_id = v_campaign_id;
end;
$$;

create or replace function qb3.refresh_distribution_snapshot(
  p_campaign_id text,
  p_after_batch_id uuid
)
returns uuid
language plpgsql
as $$
declare
  v_snapshot_id uuid;
  v_summary jsonb;
  v_accepted_total integer;
begin
  select count(*)::integer into v_accepted_total from qb3.questions;

  with recent_batches as (
    select b.batch_id
    from qb3.batches b
    where b.status = 'completed'
    order by b.completed_at desc nulls last
    limit 5
  ), recent_candidates as (
    select c.* from qb3.candidates c
    where c.batch_id in (select batch_id from recent_batches)
  ), recent_attempts as (
    select p.* from qb3.provider_attempts p
    where p.batch_id in (select batch_id from recent_batches)
  )
  select jsonb_build_object(
    'accepted_total', v_accepted_total,
    'levels', (select jsonb_build_object(
      'shallow', count(*) filter (where q.level = 'shallow'),
      'deep', count(*) filter (where q.level = 'deep')
    ) from qb3.questions q),
    'forms', coalesce((select jsonb_object_agg(form_name, form_count)
      from (select coalesce(question_form, 'unclassified') form_name, count(*) form_count
            from qb3.questions group by 1) f), '{}'::jsonb),
    'scenario_presence', (select jsonb_build_object(
      'present', count(*) filter (where scenario_present is true),
      'absent', count(*) filter (where scenario_present is false),
      'unclassified', count(*) filter (where scenario_present is null)
    ) from qb3.questions),
    'contrast_presence', (select jsonb_build_object(
      'present', count(*) filter (where contrast_present is true),
      'absent', count(*) filter (where contrast_present is false),
      'unclassified', count(*) filter (where contrast_present is null)
    ) from qb3.questions),
    'themes', coalesce((select jsonb_object_agg(t.theme_code, jsonb_build_object(
        'count', coalesce(tc.question_count, 0),
        'percentage', case when v_accepted_total = 0 then 0
          else round(100.0 * coalesce(tc.question_count, 0) / v_accepted_total, 2) end
      ))
      from qb3.themes t
      left join (select theme_code, count(*) question_count from qb3.question_themes group by theme_code) tc using (theme_code)
      where t.active), '{}'::jsonb),
    'without_theme', (select count(*) from qb3.questions q
      where not exists (select 1 from qb3.question_themes qt where qt.question_id = q.question_id)),
    'theme_combinations', coalesce((select jsonb_agg(to_jsonb(combo) order by combo.question_count desc, combo.theme_codes)
      from (select array_agg(qt.theme_code order by qt.theme_code) theme_codes, count(*) question_count
            from qb3.question_themes qt group by qt.question_id) combo), '[]'::jsonb),
    'representative_recent_accepted', coalesce((select jsonb_agg(to_jsonb(r) order by r.accepted_at desc)
      from (select q.question_id, q.question_text, q.level, q.question_form, q.accepted_at
            from qb3.questions q order by q.accepted_at desc limit 20) r), '[]'::jsonb),
    'recent_activity', jsonb_build_object(
      'batch_count', (select count(*) from recent_batches),
      'candidate_count', (select count(*) from recent_candidates),
      'accepted_count', (select count(*) from recent_candidates where state = 'accepted'),
      'acceptance_rate', (select case when count(*) = 0 then 0 else round(100.0 * count(*) filter (where state = 'accepted') / count(*), 2) end from recent_candidates),
      'quality_rejected_count', (select count(*) from recent_candidates where state = 'quality_rejected'),
      'quality_rejection_rate', (select case when count(*) = 0 then 0 else round(100.0 * count(*) filter (where state = 'quality_rejected') / count(*), 2) end from recent_candidates),
      'semantic_duplicate_count', (select count(*) from recent_candidates where state in ('exact_duplicate', 'semantic_duplicate')),
      'semantic_duplicate_rate', (select case when count(*) = 0 then 0 else round(100.0 * count(*) filter (where state in ('exact_duplicate', 'semantic_duplicate')) / count(*), 2) end from recent_candidates),
      'uncertainty_count', (select count(*) from recent_candidates where state = 'awaiting_human_review'),
      'uncertainty_rate', (select case when count(*) = 0 then 0 else round(100.0 * count(*) filter (where state = 'awaiting_human_review') / count(*), 2) end from recent_candidates),
      'provider_failure_count', (select count(*) from recent_attempts where status in ('released', 'unknown_spend', 'reservation_exceeded')),
      'provider_failure_rate', (select case when count(*) = 0 then 0 else round(100.0 * count(*) filter (where status in ('released', 'unknown_spend', 'reservation_exceeded')) / count(*), 2) end from recent_attempts)
    ),
    'rejection_reasons', coalesce((select jsonb_agg(jsonb_build_object('reason_code', reason_code, 'count', reason_count) order by reason_count desc, reason_code)
      from (select reason_code, count(*) reason_count from recent_candidates c
            cross join lateral jsonb_array_elements_text(c.rejection_reason_codes) reason_code
            group by reason_code limit 30) reasons), '[]'::jsonb),
    'feedback_notes', coalesce((select jsonb_agg(feedback_note order by created_at desc)
      from (select feedback_note, created_at from recent_candidates
            where feedback_note is not null and btrim(feedback_note) <> ''
            order by created_at desc limit 30) notes), '[]'::jsonb),
    'recent_missions', coalesce((select jsonb_agg(jsonb_build_object(
        'mission_id', m.mission_id, 'level', m.level, 'mission', m.mission,
        'accepted_count', coalesce(mc.accepted_count, 0),
        'duplicate_count', coalesce(mc.duplicate_count, 0),
        'quality_rejected_count', coalesce(mc.quality_rejected_count, 0)
      ) order by m.created_at desc)
      from qb3.missions m
      left join (select mission_id,
          count(*) filter (where state = 'accepted') accepted_count,
          count(*) filter (where state in ('exact_duplicate','semantic_duplicate')) duplicate_count,
          count(*) filter (where state = 'quality_rejected') quality_rejected_count
        from qb3.candidates group by mission_id) mc using (mission_id)
      where m.batch_id in (select batch_id from recent_batches)), '[]'::jsonb)
  ) into v_summary;

  insert into qb3.distribution_snapshots (
    campaign_id, after_batch_id, accepted_total, summary
  ) values (
    p_campaign_id, p_after_batch_id, v_accepted_total, v_summary
  ) returning distribution_snapshot_id into v_snapshot_id;

  if p_after_batch_id is not null then
    update qb3.batches
    set distribution_snapshot_id = v_snapshot_id
    where batch_id = p_after_batch_id;
  end if;

  return v_snapshot_id;
end;
$$;

create view qb3.campaign_status as
select
  c.campaign_id,
  c.campaign_name,
  c.level_mode,
  c.status,
  c.accepted_target,
  c.accepted_shallow,
  c.accepted_deep,
  c.accepted_shallow + c.accepted_deep as accepted_total,
  c.authorized_budget_usd,
  c.spent_usd,
  c.reserved_usd,
  c.unknown_spend_usd,
  c.authorized_budget_usd - c.spent_usd - c.reserved_usd
    - c.unknown_spend_usd as remaining_usd,
  c.cancel_requested,
  c.next_batch_index,
  c.emergency_batch_ceiling,
  c.started_at,
  c.updated_at,
  c.completed_at
from qb3.campaigns c;

create or replace function qb3.campaign_command(
  p_campaign_id text,
  p_action text,
  p_additional_budget_usd numeric default 0
)
returns table (result jsonb)
language plpgsql
as $$
begin
  if p_action = 'cancel' then
    perform * from qb3.request_campaign_cancel(p_campaign_id);
  elsif p_action = 'resume' then
    perform * from qb3.resume_campaign(p_campaign_id, p_additional_budget_usd);
  elsif p_action <> 'status' then
    raise exception 'unsupported campaign action %', p_action;
  end if;

  return query
  select to_jsonb(s) from qb3.campaign_status s
  where s.campaign_id = p_campaign_id;

  if not found then
    raise exception 'campaign % not found', p_campaign_id;
  end if;
end;
$$;

commit;
