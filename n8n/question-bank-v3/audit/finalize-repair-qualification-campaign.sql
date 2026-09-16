\set ON_ERROR_STOP on

begin;

do $$
declare
  v_campaign qb3.campaigns%rowtype;
  v_attempts integer;
  v_runs integer;
  v_attempt_cost numeric;
begin
  select * into v_campaign
  from qb3.campaigns
  where campaign_id = 'qb3-repair-qualification'
  for update;

  if not found then
    raise exception 'repair qualification campaign not found';
  end if;

  select count(*), coalesce(sum(actual_cost_usd), 0)
  into v_attempts, v_attempt_cost
  from qb3.provider_attempts
  where campaign_id = 'qb3-repair-qualification';

  select count(*) into v_runs
  from qb3.agent_runs
  where campaign_id = 'qb3-repair-qualification';

  if v_campaign.spent_usd <> v_attempt_cost
     or v_campaign.reserved_usd <> 0
     or v_campaign.unknown_spend_usd <> 0
     or v_attempts <> 4
     or v_runs <> 4 then
    raise exception 'repair qualification accounting or trace invariant failed';
  end if;

  update qb3.campaigns
  set status = 'cancelled_partial',
      cancel_requested = true,
      completed_at = now(),
      updated_at = now(),
      notes = concat_ws(E'\n', notes,
        'Qualification passed on n8n execution 2834. A prior fixture run also called the provider, then failed trace persistence because its pinned parent row was absent; that preserved execution was backfilled for audit.'
      )
  where campaign_id = 'qb3-repair-qualification';
end;
$$;

commit;
