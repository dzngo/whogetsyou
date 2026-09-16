\set ON_ERROR_STOP on

begin;

-- Upgrade path: make provider-attempt resume aware of a successful repair child.
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

commit;
