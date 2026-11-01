begin;

do $$
declare
  v_campaign_id text := 'test-deterministic-shallow-gate';
  v_snapshot_id uuid;
  v_batch_id uuid;
  v_mission_id uuid;
  v_short_id uuid;
  v_long_id uuid;
  v_second_person_id uuid;
begin
  insert into qb3.prompt_snapshots (registry_snapshot, configuration_hash)
  values ('[]'::jsonb, 'deterministic-shallow-gate-test')
  returning prompt_snapshot_id into v_snapshot_id;
  insert into qb3.campaigns (
    campaign_id, campaign_name, raw_input, level_mode, accepted_target,
    shallow_target, deep_target, authorized_budget_usd, prompt_snapshot_id,
    emergency_batch_ceiling, status
  ) values (
    v_campaign_id, 'Deterministic shallow gate test', '{}'::jsonb, 'shallow',
    10, 10, 0, 1, v_snapshot_id, 12, 'running'
  );
  insert into qb3.batches (campaign_id, batch_index, requested_level_mix, status)
  values (v_campaign_id, 1, '{"shallow": 20, "deep": 0}'::jsonb, 'running')
  returning batch_id into v_batch_id;
  insert into qb3.missions (campaign_id, batch_id, mission_slot, level, observation_report, mission)
  values (v_campaign_id, v_batch_id, 1, 'shallow', '{}'::jsonb, '{}'::jsonb)
  returning mission_id into v_mission_id;

  insert into qb3.candidates (campaign_id, batch_id, mission_id, candidate_index, question_text, normalized_text, level)
  values (v_campaign_id, v_batch_id, v_mission_id, 1, 'What food do I dislike?', 'what food do i dislike', 'shallow')
  returning candidate_id into v_short_id;
  insert into qb3.candidates (campaign_id, batch_id, mission_id, candidate_index, question_text, normalized_text, level)
  values (v_campaign_id, v_batch_id, v_mission_id, 2, 'What would I do if I had exactly 200 euros to spend this weekend?', 'what would i do with exactly 200 euros', 'shallow')
  returning candidate_id into v_long_id;
  insert into qb3.candidates (campaign_id, batch_id, mission_id, candidate_index, question_text, normalized_text, level)
  values (v_campaign_id, v_batch_id, v_mission_id, 3, 'What do you think I usually do first when I get home?', 'what do you think i do first', 'shallow')
  returning candidate_id into v_second_person_id;

  perform qb3.apply_deterministic_shallow_gate(v_batch_id);

  if (select state from qb3.candidates where candidate_id = v_short_id) <> 'proposed' then
    raise exception 'plain shallow question should not be rejected';
  end if;
  if (select state from qb3.candidates where candidate_id = v_long_id) <> 'quality_rejected'
     or not (select rejection_reason_codes ? 'shallow_precision_burden' from qb3.candidates where candidate_id = v_long_id) then
    raise exception 'precision burden should be deterministically rejected';
  end if;
  if (select state from qb3.candidates where candidate_id = v_second_person_id) <> 'quality_rejected'
     or not (select rejection_reason_codes ? 'shallow_second_person_voice' from qb3.candidates where candidate_id = v_second_person_id) then
    raise exception 'second-person voice should be deterministically rejected';
  end if;
  if (select status from qb3.candidate_stage_work where candidate_id = v_long_id and stage = 'quality') <> 'complete' then
    raise exception 'deterministic quality rejection must complete the quality stage';
  end if;
end;
$$;

rollback;
