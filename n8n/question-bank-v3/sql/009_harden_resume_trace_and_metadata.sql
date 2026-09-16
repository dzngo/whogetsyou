\set ON_ERROR_STOP on

-- Reliability hardening for resumable provider attempts, exact campaign mixes,
-- pre-provider mission traceability, and atomic metadata completeness.

begin;

alter table qb3.provider_attempts
  add column if not exists lease_expires_at timestamptz
  not null default (now() + interval '30 minutes');

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

  if p_level_mode = 'mixed' and mod(p_accepted_target, 2) <> 0 then
    raise exception 'mixed accepted target must be even for an exact 50/50 split';
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
  v_requested_mix jsonb;
  v_expected_level text;
begin
  if p_mission_slot not between 1 and 4 then
    raise exception 'mission slot must be between 1 and 4';
  end if;

  if jsonb_typeof(p_questions) <> 'array'
     or jsonb_array_length(p_questions) not in (0, 5) then
    raise exception 'mission persistence requires zero questions before Creative or exactly five afterward';
  end if;

  select b.requested_level_mix into v_requested_mix
  from qb3.batches b
  where b.batch_id = p_batch_id and b.campaign_id = p_campaign_id;

  if not found then
    raise exception 'batch % does not belong to campaign %', p_batch_id, p_campaign_id;
  end if;

  v_expected_level := case
    when p_mission_slot <= coalesce((v_requested_mix ->> 'shallow')::integer, 0) / 5
      then 'shallow' else 'deep' end;

  if p_level <> v_expected_level
     or (p_mission ->> 'mission_slot')::integer <> p_mission_slot
     or p_mission ->> 'level' <> p_level then
    raise exception 'mission slot %, level %, and requested level mix are inconsistent', p_mission_slot, p_level;
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

  if jsonb_array_length(p_questions) = 0 then
    return query select v_mission_id, null::uuid, null::smallint, null::text;
    return;
  end if;

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
  where attempt_id = p_attempt_id
  for update;

  if found then
    if v_attempt.campaign_id <> p_campaign_id
      or v_attempt.reservation_usd <> p_reservation_usd
      or v_attempt.agent_role <> p_agent_role
      or v_attempt.provider <> p_provider
      or v_attempt.requested_model <> p_requested_model
      or v_attempt.reasoning_setting <> p_reasoning_setting
      or v_attempt.batch_id is distinct from p_batch_id
      or v_attempt.candidate_id is distinct from p_candidate_id
      or v_attempt.parent_attempt_id is distinct from p_parent_attempt_id then
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

    -- A schema-failed base attempt may already have a successful repair child.
    -- Resume must return the repaired original-role payload instead of launching
    -- another provider call or replaying the stale schema failure.
    if v_attempt.status = 'reconciled'
       and v_cached_result ->> 'status' = 'schema_failed' then
      select jsonb_build_object(
        'invocation_id', repair_run.invocation_id,
        'attempt_id', child.attempt_id,
        'structured_response', repair_run.structured_response -> 'repaired_output',
        'raw_response', repair_run.raw_response,
        'status', 'succeeded',
        'repair_of_invocation_id', base_run.invocation_id
      )
      into v_cached_result
      from qb3.agent_runs base_run
      join qb3.provider_attempts child
        on child.parent_attempt_id = base_run.attempt_id
       and child.status = 'reconciled'
      join qb3.agent_runs repair_run
        on repair_run.attempt_id = child.attempt_id
       and repair_run.status = 'succeeded'
      where base_run.attempt_id = p_attempt_id
        and repair_run.structured_response ->> 'repairable' = 'true'
        and repair_run.structured_response ->> 'original_schema_validated' = 'true'
        and repair_run.structured_response ? 'repaired_output'
      order by child.completed_at desc nulls last
      limit 1;
    end if;

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

    -- A fresh reservation may still belong to an in-flight worker. Do not
    -- replay it and do not declare unknown spend until its lease expires.
    if v_attempt.status = 'reserved' and v_cached_result is null then
      if v_attempt.lease_expires_at > now() then
        v_cached_result := jsonb_build_object(
          'status', 'in_flight',
          'attempt_id', p_attempt_id,
          'structured_response', jsonb_build_object(
            'status', 'pending',
            'transport_status', 'in_flight',
            'reason', 'provider_attempt_lease_active'
          )
        );

        return query select false, 'attempt_in_flight',
          v_campaign.authorized_budget_usd
            - v_campaign.spent_usd
            - v_campaign.reserved_usd
            - v_campaign.unknown_spend_usd,
          v_cached_result;
        return;
      end if;

      -- Once the lease has expired, the provider may have accepted the request
      -- before the worker crashed. Never replay it automatically, because that
      -- could buy the same call twice.
      update qb3.provider_attempts
      set status = 'unknown_spend',
          sanitized_error = jsonb_build_object(
            'reason', 'recovered_reserved_attempt',
            'message', 'Reserved provider attempt recovered without a durable result; automatic replay blocked'
          ),
          completed_at = now()
      where attempt_id = p_attempt_id;

      update qb3.campaigns
      set reserved_usd = reserved_usd - v_attempt.reservation_usd,
          unknown_spend_usd = unknown_spend_usd + v_attempt.reservation_usd,
          status = 'unknown_spend'
      where campaign_id = p_campaign_id;

      v_cached_result := jsonb_build_object(
        'status', 'unknown_spend',
        'attempt_id', p_attempt_id,
        'structured_response', jsonb_build_object(
          'status', 'failed',
          'transport_status', 'unknown_spend',
          'reason', 'recovered_reserved_attempt'
        )
      );

      return query select false, 'idempotent_unknown_spend',
        v_campaign.authorized_budget_usd
          - v_campaign.spent_usd
          - v_campaign.unknown_spend_usd
          - v_attempt.reservation_usd,
        v_cached_result;
      return;
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

create or replace function qb3.apply_metadata_results(
  p_batch_id uuid,
  p_items jsonb
)
returns table (candidate_id uuid, question_id uuid)
language plpgsql
as $$
declare
  v_item jsonb;
  v_expected_count integer;
  v_actual_count integer;
  v_distinct_count integer;
begin
  if jsonb_typeof(p_items) <> 'array' then
    raise exception 'metadata items must be an array';
  end if;

  select count(*)::integer into v_expected_count
  from qb3.candidates c
  where c.batch_id = p_batch_id
    and c.state = 'accepted'
    and c.metadata_result is null;

  v_actual_count := jsonb_array_length(p_items);
  select count(distinct value ->> 'candidate_id')::integer
  into v_distinct_count
  from jsonb_array_elements(p_items);

  if v_actual_count <> v_expected_count then
    raise exception 'metadata item count % does not match expected accepted candidate count %',
      v_actual_count, v_expected_count;
  end if;

  if v_distinct_count <> v_actual_count then
    raise exception 'metadata items must contain each candidate id exactly once';
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

commit;
