begin;

do $$
declare
  v_snapshot_id uuid;
  v_batch_id uuid;
  v_row record;
begin
  insert into qb3.prompt_snapshots (registry_snapshot, configuration_hash)
  values ('[]'::jsonb, 'route-candidate-test') returning prompt_snapshot_id into v_snapshot_id;
  insert into qb3.campaigns (
    campaign_id, campaign_name, raw_input, level_mode, accepted_target,
    shallow_target, deep_target, authorized_budget_usd, prompt_snapshot_id,
    emergency_batch_ceiling, status
  ) values ('route-candidate-test', 'Route candidate test', '{}'::jsonb, 'shallow',
    10, 10, 0, 1, v_snapshot_id, 12, 'running');
  insert into qb3.batches (campaign_id, batch_index, requested_level_mix, status)
  values ('route-candidate-test', 1, '{"shallow":20,"deep":0}'::jsonb, 'running')
  returning batch_id into v_batch_id;

  select * into v_row from qb3.persist_mission_and_route_candidate(
    'route-candidate-test', v_batch_id, 2, 'shallow', '{}'::jsonb,
    '{"mission_slot":2,"level":"shallow","brief":"Everyday choices","shallow_family":"everyday_choices_and_spending","routes":[]}'::jsonb,
    4, 'What do I usually do when I am bored?'
  );
  if v_row.candidate_index <> 9 or v_row.question_text <> 'What do I usually do when I am bored?' then
    raise exception 'route candidate must persist at its mission and route slot';
  end if;
  perform qb3.persist_mission_and_route_candidate(
    'route-candidate-test', v_batch_id, 2, 'shallow', '{}'::jsonb,
    '{"mission_slot":2,"level":"shallow","brief":"Everyday choices","shallow_family":"everyday_choices_and_spending","routes":[]}'::jsonb,
    4, 'What do I usually do when I am bored?'
  );
  if (select count(*) from qb3.candidates where batch_id = v_batch_id and candidate_index = 9) <> 1 then
    raise exception 'route persistence must be idempotent';
  end if;
end;
$$;

rollback;
