\set ON_ERROR_STOP on

begin;

insert into qb3.prompt_snapshots (registry_snapshot, configuration_hash)
values ('{"test":true}'::jsonb, 'test-configuration')
returning prompt_snapshot_id as test_prompt_snapshot_id \gset

select qb3.freeze_prompt_snapshot(
  '{"prompts":[{"promptKey":"creative","version":"v1","template":"Create."}],"configuration":{"model":"test"}}'::jsonb
) as frozen_prompt_snapshot_id \gset

insert into qb3.campaigns (
  campaign_id, campaign_name, raw_input, level_mode, accepted_target,
  shallow_target, deep_target, authorized_budget_usd,
  prompt_snapshot_id, emergency_batch_ceiling
) values (
  'prompt-test', 'Prompt test', '{}'::jsonb, 'shallow', 1, 1, 0,
  1.000000, :'frozen_prompt_snapshot_id', 2
);

do $$
begin
  assert (
    select prompt #>> '{promptKey}' = 'creative'
    from qb3.load_frozen_prompt('prompt-test', 'creative')
  ), 'frozen prompt must be retrievable by campaign and key';
end;
$$;

do $$
declare
  v_rejected boolean := false;
begin
  begin
    perform * from qb3.create_campaign(
      'odd-mixed-test', 'Odd mixed test', '{}'::jsonb,
      'mixed', 5, 2.000000,
      (select prompt_snapshot_id from qb3.prompt_snapshots where configuration_hash = 'test-configuration'),
      12, null
    );
  exception when others then v_rejected := true;
  end;
  assert v_rejected, 'mixed campaigns must reject odd targets rather than silently skewing the split';
end;
$$;

select * from qb3.create_campaign(
  'control-test', 'Control test', '{"source":"sql-test"}'::jsonb,
  'mixed', 6, 2.000000, :'test_prompt_snapshot_id', 12, 'test notes'
);

do $$
begin
  assert (
    select shallow_target = 3 and deep_target = 3 and status = 'running'
    from qb3.campaigns where campaign_id = 'control-test'
  ), 'mixed campaign target must split deterministically';
end;
$$;

select * from qb3.begin_next_batch('control-test');
select * from qb3.begin_next_batch('control-test');

do $$
begin
  assert (
    select batch_index = 1
      and requested_level_mix = '{"deep":10,"shallow":10}'::jsonb
    from qb3.batches where campaign_id = 'control-test'
  ), 'first mixed batch must request ten questions per level';
  assert (
    select next_batch_index = 2
    from qb3.campaigns where campaign_id = 'control-test'
  ), 'beginning or resuming a running batch must advance its durable index once';
  assert (
    select count(*) = 1 from qb3.batches where campaign_id = 'control-test'
  ), 'begin_next_batch must resume the current running batch idempotently';
end;
$$;

select * from qb3.request_campaign_cancel('control-test');

do $$
begin
  assert (
    select cancel_requested and status = 'running'
    from qb3.campaigns where campaign_id = 'control-test'
  ), 'cancel is cooperative while an execution may be accounting';
end;
$$;

select * from qb3.resume_campaign('control-test', 0.500000);

do $$
begin
  assert (
    select not cancel_requested and authorized_budget_usd = 2.500000
    from qb3.campaigns where campaign_id = 'control-test'
  ), 'resume must add new authorization and clear cancellation';
end;
$$;

select * from qb3.campaign_command('control-test', 'status', 0);

do $$
begin
  assert (
    select count(*) = 1 from qb3.campaigns where campaign_id = 'control-test'
  ), 'status command must be read-only';
end;
$$;

insert into qb3.campaigns (
  campaign_id, campaign_name, raw_input, level_mode, accepted_target,
  shallow_target, deep_target, authorized_budget_usd,
  prompt_snapshot_id, emergency_batch_ceiling
) values (
  'budget-test', 'Budget test', '{"source":"sql-test"}'::jsonb,
  'shallow', 2, 2, 0, 1.000000,
  :'test_prompt_snapshot_id', 10
);

do $$
declare
  v_reserved boolean;
  v_reason text;
begin
  select reserved, reason into v_reserved, v_reason
  from qb3.reserve_provider_budget(
    'attempt-1', 'budget-test', null, null, null,
    'creative', 'gemini', 'test-model', 'high', 0.400000
  );
  assert v_reserved and v_reason = 'reserved', 'first reservation must succeed';

  select reserved, reason into v_reserved, v_reason
  from qb3.reserve_provider_budget(
    'attempt-too-large', 'budget-test', null, null, null,
    'creative', 'gemini', 'test-model', 'high', 0.700000
  );
  assert not v_reserved and v_reason = 'insufficient_budget', 'hard cap must reject';

  assert (select reserved_usd = 0.400000 from qb3.campaigns where campaign_id = 'budget-test'),
    'a reservation must be charged to the campaign exactly once';
end;
$$;

insert into qb3.campaigns (
  campaign_id, campaign_name, raw_input, level_mode, accepted_target,
  shallow_target, deep_target, authorized_budget_usd,
  prompt_snapshot_id, emergency_batch_ceiling
) values (
  'ambiguous-resume-test', 'Ambiguous resume test', '{}'::jsonb,
  'shallow', 1, 1, 0, 1.000000,
  :'test_prompt_snapshot_id', 2
);

select * from qb3.reserve_provider_budget(
  'ambiguous-attempt', 'ambiguous-resume-test', null, null, null,
  'creative', 'gemini', 'test-model', 'high', 0.400000
);

do $$
declare
  v_reserved boolean;
  v_reason text;
  v_cached_result jsonb;
begin
  select reserved, reason, cached_result
  into v_reserved, v_reason, v_cached_result
  from qb3.reserve_provider_budget(
    'ambiguous-attempt', 'ambiguous-resume-test', null, null, null,
    'creative', 'gemini', 'test-model', 'high', 0.400000
  );

  assert not v_reserved and v_reason = 'attempt_in_flight',
    'a duplicate request inside the active lease must not replay or abandon the provider call';
  assert v_cached_result ->> 'status' = 'in_flight'
      and v_cached_result #>> '{structured_response,reason}' = 'provider_attempt_lease_active',
    'an active lease must return a durable in-flight result';
  assert (
    select reserved_usd = 0.400000
      and unknown_spend_usd = 0
      and status = 'running'
    from qb3.campaigns where campaign_id = 'ambiguous-resume-test'
  ), 'an active lease must preserve the original reservation and running campaign';

  update qb3.provider_attempts
  set lease_expires_at = now() - interval '1 second'
  where attempt_id = 'ambiguous-attempt';

  select reserved, reason, cached_result
  into v_reserved, v_reason, v_cached_result
  from qb3.reserve_provider_budget(
    'ambiguous-attempt', 'ambiguous-resume-test', null, null, null,
    'creative', 'gemini', 'test-model', 'high', 0.400000
  );

  assert not v_reserved and v_reason = 'idempotent_unknown_spend',
    'an expired ambiguous attempt must never be automatically purchased again';
  assert v_cached_result ->> 'status' = 'unknown_spend'
      and v_cached_result #>> '{structured_response,reason}' = 'recovered_reserved_attempt',
    'expired recovery must return a durable, inspectable failure result';
  assert (
    select reserved_usd = 0
      and unknown_spend_usd = 0.400000
      and status = 'unknown_spend'
    from qb3.campaigns where campaign_id = 'ambiguous-resume-test'
  ), 'expired recovery must conservatively stop the campaign and preserve the reservation as unknown spend';
end;
$$;

do $$
declare
  v_rejected boolean;
begin
  v_rejected := false;
  begin
    perform * from qb3.reserve_provider_budget('attempt-1', 'budget-test', null, null, null, 'creative', 'openai', 'test-model', 'high', 0.400000);
  exception when others then v_rejected := true;
  end;
  assert v_rejected, 'attempt id reuse must reject a changed provider';

  v_rejected := false;
  begin
    perform * from qb3.reserve_provider_budget('attempt-1', 'budget-test', null, null, null, 'creative', 'gemini', 'test-model', 'low', 0.400000);
  exception when others then v_rejected := true;
  end;
  assert v_rejected, 'attempt id reuse must reject changed reasoning';

  v_rejected := false;
  begin
    perform * from qb3.reserve_provider_budget('attempt-1', 'budget-test', gen_random_uuid(), null, null, 'creative', 'gemini', 'test-model', 'high', 0.400000);
  exception when others then v_rejected := true;
  end;
  assert v_rejected, 'attempt id reuse must reject a changed batch';

  v_rejected := false;
  begin
    perform * from qb3.reserve_provider_budget('attempt-1', 'budget-test', null, gen_random_uuid(), null, 'creative', 'gemini', 'test-model', 'high', 0.400000);
  exception when others then v_rejected := true;
  end;
  assert v_rejected, 'attempt id reuse must reject a changed candidate';

  v_rejected := false;
  begin
    perform * from qb3.reserve_provider_budget('attempt-1', 'budget-test', null, null, 'parent-attempt', 'creative', 'gemini', 'test-model', 'high', 0.400000);
  exception when others then v_rejected := true;
  end;
  assert v_rejected, 'attempt id reuse must reject a changed parent';
end;
$$;

select * from qb3.reconcile_provider_attempt(
  'attempt-1', 0.250000, 'reported-test-model', '{"input_tokens":10,"output_tokens":5}'::jsonb
);

select * from qb3.persist_agent_run(
  'invocation-1', 'attempt-1', 'budget-test', null, null, null,
  'creative', 'creative', 'v1', 'Rendered credential-free prompt',
  'Raw response', '{"questions":[]}'::jsonb, 'succeeded', null
);

do $$
begin
  assert (
    select rendered_prompt = 'Rendered credential-free prompt'
      and structured_response = '{"questions":[]}'::jsonb
    from qb3.agent_runs where invocation_id = 'invocation-1'
  ), 'agent trace must preserve rendered input and structured output';
end;
$$;

do $$
declare
  v_reserved boolean;
  v_reason text;
  v_cached_result jsonb;
begin
  select reserved, reason, cached_result
  into v_reserved, v_reason, v_cached_result
  from qb3.reserve_provider_budget(
    'attempt-1', 'budget-test', null, null, null,
    'creative', 'gemini', 'test-model', 'high', 0.400000
  );

  assert not v_reserved and v_reason = 'idempotent_reconciled',
    'a completed attempt must not call the provider again';
  assert v_cached_result ->> 'status' = 'succeeded'
      and v_cached_result -> 'structured_response' = '{"questions":[]}'::jsonb,
    'a completed attempt must return its cached agent result to the resumed workflow';
end;
$$;

insert into qb3.provider_attempts (
  attempt_id, campaign_id, agent_role, provider, requested_model,
  reasoning_setting, reservation_usd, actual_cost_usd, status, completed_at
) values
  ('repair-base-attempt', 'budget-test', 'semantic', 'openai', 'test-model',
   'high', 0.010000, 0.001000, 'reconciled', now()),
  ('repair-child-attempt', 'budget-test', 'structured_output_repair', 'openai', 'test-model',
   'low', 0.010000, 0.001000, 'reconciled', now());

update qb3.provider_attempts
set parent_attempt_id = 'repair-base-attempt'
where attempt_id = 'repair-child-attempt';

insert into qb3.agent_runs (
  invocation_id, attempt_id, campaign_id, agent_role, prompt_key,
  prompt_version, rendered_prompt, raw_response, structured_response,
  status, repair_of_invocation_id, completed_at
) values
  ('repair-base-invocation', 'repair-base-attempt', 'budget-test', 'semantic',
   'semantic_judge', 'v1', 'original prompt', '{"decision":"distinct",}', '{}'::jsonb,
   'schema_failed', null, now()),
  ('repair-child-invocation', 'repair-child-attempt', 'budget-test', 'structured_output_repair',
   'repair_structured_output', 'v1', 'repair prompt', '{"repairable":true}',
   '{"repairable":true,"repaired_output":{"decision":"distinct"},"error":null,"original_schema_validated":true}'::jsonb,
   'succeeded', 'repair-base-invocation', now());

do $$
declare
  v_reserved boolean;
  v_reason text;
  v_cached_result jsonb;
begin
  select reserved, reason, cached_result
  into v_reserved, v_reason, v_cached_result
  from qb3.reserve_provider_budget(
    'repair-base-attempt', 'budget-test', null, null, null,
    'semantic', 'openai', 'test-model', 'high', 0.010000
  );

  assert not v_reserved and v_reason = 'idempotent_reconciled',
    'a repaired attempt must remain idempotent on resume';
  assert v_cached_result ->> 'status' = 'succeeded'
      and v_cached_result -> 'structured_response' = '{"decision":"distinct"}'::jsonb
      and v_cached_result ->> 'repair_of_invocation_id' = 'repair-base-invocation',
    'resume must return the repaired original-role payload instead of the stale schema failure';
end;
$$;

do $$
begin
  assert (
    select spent_usd = 0.250000 and reserved_usd = 0
    from qb3.campaigns where campaign_id = 'budget-test'
  ), 'reconciliation must move reservation to actual spend';
end;
$$;

select * from qb3.reserve_provider_budget(
  'attempt-release', 'budget-test', null, null, null,
  'quality', 'openai', 'test-model', 'medium', 0.200000
);
select * from qb3.release_provider_attempt('attempt-release', '{"kind":"no_charge"}'::jsonb);

select * from qb3.reserve_provider_budget(
  'attempt-unknown', 'budget-test', null, null, null,
  'semantic', 'openai', 'test-model', 'high', 0.300000
);
select * from qb3.mark_provider_attempt_unknown(
  'attempt-unknown', '{"kind":"ambiguous_transport"}'::jsonb
);

do $$
begin
  assert (
    select status = 'running'
      and reserved_usd = 0
      and unknown_spend_usd = 0.300000
    from qb3.campaigns where campaign_id = 'budget-test'
  ), 'ambiguous spend must remain budgeted without globally stopping safe work';
end;
$$;

insert into qb3.campaigns (
  campaign_id, campaign_name, raw_input, level_mode, accepted_target,
  shallow_target, deep_target, authorized_budget_usd,
  prompt_snapshot_id, emergency_batch_ceiling
) values (
  'admission-test', 'Admission test', '{"source":"sql-test"}'::jsonb,
  'mixed', 2, 1, 1, 1.000000,
  :'test_prompt_snapshot_id', 10
);

insert into qb3.batches (campaign_id, batch_index, requested_level_mix)
values ('admission-test', 1, '{"shallow":5,"deep":15}'::jsonb)
returning batch_id as test_batch_id \gset

insert into qb3.missions (
  campaign_id, batch_id, mission_slot, level, observation_report, mission
) values (
  'admission-test', :'test_batch_id', 1, 'shallow', '{}'::jsonb, '{}'::jsonb
) returning mission_id as test_mission_id \gset

do $$
declare
  v_batch_id uuid;
  v_rejected boolean := false;
begin
  select batch_id into v_batch_id from qb3.batches
  where campaign_id = 'admission-test' and batch_index = 1;
  begin
    perform * from qb3.persist_mission_and_candidates(
      'admission-test', v_batch_id, 2, 'shallow', '{}'::jsonb,
      '{"mission_slot":2,"level":"shallow","brief":"wrong level"}'::jsonb,
      '["A?","B?","C?","D?","E?"]'::jsonb
    );
  exception when others then v_rejected := true;
  end;
  assert v_rejected, 'mission persistence must reject a level that contradicts the batch mix';
  assert (select count(*) = 0 from qb3.candidates where batch_id = v_batch_id),
    'an invalid mission must not create candidates';
end;
$$;

select * from qb3.persist_mission_and_candidates(
  'admission-test', :'test_batch_id', 2, 'deep',
  '{"summary":"test"}'::jsonb,
  '{"mission_slot":2,"level":"deep","brief":"distinct everyday situations"}'::jsonb,
  '[]'::jsonb
);

do $$
begin
  assert (
    select count(*) = 1 from qb3.missions
    where batch_id = (select batch_id from qb3.batches where campaign_id = 'admission-test' and batch_index = 1)
      and mission_slot = 2
  ), 'mission must be durable before the Creative provider call';
  assert (
    select count(*) = 0 from qb3.candidates
    where batch_id = (select batch_id from qb3.batches where campaign_id = 'admission-test' and batch_index = 1)
      and candidate_index between 6 and 10
  ), 'pre-Creative mission persistence must not fabricate candidates';
end;
$$;

select * from qb3.persist_mission_and_candidates(
  'admission-test', :'test_batch_id', 2, 'deep',
  '{"summary":"test"}'::jsonb,
  '{"mission_slot":2,"level":"deep","brief":"distinct everyday situations"}'::jsonb,
  '["Question one?","Question two?","Question three?","Question four?","Question five?"]'::jsonb
);

do $$
begin
  assert (
    select count(*) = 5 from qb3.candidates
    where campaign_id = 'admission-test' and candidate_index between 6 and 10
  ), 'one Creative invocation must persist five independent candidates';
end;
$$;

do $$
declare
  v_batch_id uuid;
  v_candidate_id uuid;
  v_rejected boolean := false;
begin
  select batch_id into v_batch_id from qb3.batches
  where campaign_id = 'admission-test' and batch_index = 1;
  select candidate_id into v_candidate_id from qb3.candidates
  where batch_id = v_batch_id order by candidate_index limit 1;
  begin
    perform * from qb3.apply_quality_results(
      v_batch_id,
      jsonb_build_array(
        jsonb_build_object('candidate_id', v_candidate_id, 'verdict', 'pass'),
        jsonb_build_object('candidate_id', v_candidate_id, 'verdict', 'pass')
      ), false
    );
  exception when others then v_rejected := true;
  end;
  assert v_rejected, 'quality application must reject duplicate candidate ids atomically';
end;
$$;

do $$
declare
  v_batch_id uuid;
  v_decisions jsonb;
  v_escalation jsonb;
  v_metadata jsonb;
begin
  select batch_id into v_batch_id from qb3.batches
  where campaign_id = 'admission-test' and batch_index = 1;

  select jsonb_agg(jsonb_build_object(
    'candidate_id', candidate_id,
    'verdict', case candidate_index when 7 then 'reject' when 8 then 'uncertain' else 'pass' end,
    'reason_codes', case candidate_index when 7 then '["too_deep_for_level"]'::jsonb else '[]'::jsonb end,
    'feedback_note', case candidate_index when 7 then 'Wrong level' when 8 then 'Needs a second look' else 'Clear' end
  ) order by candidate_index) into v_decisions
  from qb3.candidates where batch_id = v_batch_id and candidate_index between 6 and 10;

  perform * from qb3.apply_quality_results(v_batch_id, v_decisions, false);

  select jsonb_agg(jsonb_build_object(
    'candidate_id', candidate_id, 'verdict', 'uncertain',
    'reason_codes', '["genuinely_uncertain"]'::jsonb,
    'feedback_note', 'Human review required'
  )) into v_escalation from qb3.candidates
  where batch_id = v_batch_id and quality_result ->> 'verdict' = 'uncertain';
  perform * from qb3.apply_quality_results(v_batch_id, v_escalation, true);

  assert (select count(*) = 3 from qb3.get_preflight_candidates(v_batch_id)),
    'quality processing must leave only independently passed candidates eligible';
  assert (select count(*) = 1 from qb3.review_queue where review_type = 'quality'),
    'escalated uncertainty must enter human review';

  update qb3.candidates
  set embedding = array_fill((candidate_index::numeric / 100)::real, array[1536])::vector
  where batch_id = v_batch_id and state = 'proposed'
    and quality_result ->> 'verdict' = 'pass';

  assert (select count(*) = 0 from qb3.get_preflight_candidates(v_batch_id)),
    'preflight replay must skip candidates whose embeddings are already stored';

  assert (select count(*) = 1 from qb3.get_semantic_groups(v_batch_id)),
    'three eligible candidates must fit in one semantic group of at most five';

  select jsonb_agg(jsonb_build_object(
    'candidate_id', candidate_id,
    'verdict', case candidate_index when 6 then 'distinct' when 9 then 'duplicate' else 'uncertain' end,
    'matched_question_ids', '[]'::jsonb,
    'relations', '{"scenario":"different","perspective":"different","answer_space":"different"}'::jsonb,
    'reason_codes', case candidate_index when 9 then '["same_answer_space"]'::jsonb else '[]'::jsonb end,
    'feedback_note', 'Semantic test decision'
  ) order by candidate_index) into v_decisions
  from qb3.candidates where batch_id = v_batch_id and state = 'proposed'
    and quality_result ->> 'verdict' = 'pass';
  perform * from qb3.apply_semantic_results(v_batch_id, v_decisions);

  select jsonb_build_array(jsonb_build_object(
    'candidate_id', candidate_id, 'themes', jsonb_build_array('yourself'),
    'question_form', 'direct', 'scenario_present', false,
    'contrast_present', false, 'aspect', 'preference',
    'scenario', null, 'perspective', 'self',
    'answer_space', 'short answer', 'contrast', null
  )) into v_metadata from qb3.candidates
  where batch_id = v_batch_id and candidate_index = 6;

  begin
    perform * from qb3.apply_metadata_results(v_batch_id, '[]'::jsonb);
    raise exception 'missing metadata unexpectedly accepted';
  exception
    when raise_exception then
      if sqlerrm = 'missing metadata unexpectedly accepted' then raise; end if;
  end;

  begin
    perform * from qb3.apply_metadata_results(v_batch_id, v_metadata || v_metadata);
    raise exception 'duplicate metadata unexpectedly accepted';
  exception
    when raise_exception then
      if sqlerrm = 'duplicate metadata unexpectedly accepted' then raise; end if;
  end;

  perform * from qb3.apply_metadata_results(v_batch_id, v_metadata);

  assert (select metadata_result is not null from qb3.candidates
    where batch_id = v_batch_id and candidate_index = 6),
    'metadata batch application must persist per-question metadata';
end;
$$;

insert into qb3.candidates (
  campaign_id, batch_id, mission_id, candidate_index, question_text,
  normalized_text, level, embedding
) values (
  'admission-test', :'test_batch_id', :'test_mission_id', 1,
  'A test question?', qb3.normalize_question('A test question?'), 'shallow',
  array_fill(0.01::real, array[1536])::vector
) returning candidate_id as candidate_one_id \gset

select * from qb3.accept_candidate(:'candidate_one_id');
select * from qb3.accept_candidate(:'candidate_one_id');

select * from qb3.apply_question_metadata(
  :'candidate_one_id',
  '{"themes":["yourself","hobbies"],"question_form":"direct","scenario_present":false,"contrast_present":false,"aspect":"preference","perspective":"self knowledge","answer_space":"short factual answer"}'::jsonb
);

do $$
begin
  assert (
    select count(*) = 2
    from qb3.question_themes qt
    join qb3.questions q using (question_id)
    where q.question_text = 'A test question?'
  ), 'metadata must support zero-to-many equal theme memberships';
end;
$$;

insert into qb3.candidates (
  campaign_id, batch_id, mission_id, candidate_index, question_text,
  normalized_text, level, embedding
) values (
  'admission-test', :'test_batch_id', :'test_mission_id', 2,
  'A TEST question!', qb3.normalize_question('A TEST question!'), 'shallow',
  array_fill(0.02::real, array[1536])::vector
) returning candidate_id as candidate_two_id \gset

select * from qb3.preflight_candidate(:'candidate_two_id');

do $$
begin
  assert (
    select state = 'exact_duplicate'
    from qb3.candidates
    where campaign_id = 'admission-test' and candidate_index = 2
  ), 'preflight must identify an accepted normalized duplicate';
end;
$$;

select * from qb3.accept_candidate(:'candidate_two_id');

do $$
begin
  assert (select count(*) = 2 from qb3.questions), 'accepted bank must contain two unique admitted questions';
  assert (
    select accepted_shallow = 1 and accepted_deep = 1
    from qb3.campaigns where campaign_id = 'admission-test'
  ), 'idempotent admission must increment campaign once';
  assert (
    select state = 'exact_duplicate'
    from qb3.candidates
    where campaign_id = 'admission-test' and candidate_index = 2
  ), 'normalized duplicate must be rejected without semantic admission';
  assert qb3.normalize_question('  Hello,   WORLD! ') = 'hello world',
    'normalization must collapse punctuation, case, and whitespace';
  assert (
    select count(*) <= 10
    from qb3.find_nearest_questions(array_fill(0.01::real, array[1536])::vector, 99)
  ), 'nearest-neighbour function must cap results at ten';
end;
$$;

insert into qb3.candidates (
  campaign_id, batch_id, mission_id, candidate_index, question_text,
  normalized_text, level, embedding
) values (
  'admission-test', :'test_batch_id', :'test_mission_id', 5,
  'A surplus candidate?', qb3.normalize_question('A surplus candidate?'), 'shallow',
  array_fill(0.05::real, array[1536])::vector
);

update qb3.batches
set status = 'completed', completed_at = now()
where batch_id = :'test_batch_id';

select * from qb3.complete_batch(:'test_batch_id');

do $$
begin
  assert (
    select state = 'proposed'
    from qb3.candidates
    where campaign_id = 'admission-test' and candidate_index = 5
  ), 'metadata-pending questions must not terminalize possible replacements';
  assert (
    select status = 'waiting_recovery'
    from qb3.campaigns where campaign_id = 'admission-test'
  ), 'an accepted-but-unready target must wait for metadata recovery';
end;
$$;

insert into qb3.campaigns (
  campaign_id, campaign_name, raw_input, level_mode, accepted_target,
  shallow_target, deep_target, accepted_shallow, accepted_deep,
  authorized_budget_usd, prompt_snapshot_id, emergency_batch_ceiling
) values (
  'level-terminality-test', 'Level terminality test', '{}'::jsonb, 'mixed', 2,
  1, 1, 1, 0, 1.000000, :'test_prompt_snapshot_id', 2
);

insert into qb3.batches (campaign_id, batch_index, requested_level_mix)
values ('level-terminality-test', 1, '{"shallow":1,"deep":1}'::jsonb)
returning batch_id as level_terminality_batch_id \gset

insert into qb3.missions (
  campaign_id, batch_id, mission_slot, level, observation_report, mission
) values
  ('level-terminality-test', :'level_terminality_batch_id', 1, 'shallow', '{}'::jsonb, '{}'::jsonb),
  ('level-terminality-test', :'level_terminality_batch_id', 2, 'deep', '{}'::jsonb, '{}'::jsonb);

insert into qb3.candidates (
  campaign_id, batch_id, mission_id, candidate_index, question_text, normalized_text, level
)
select 'level-terminality-test', :'level_terminality_batch_id', mission_id,
       mission_slot, 'Level candidate ' || mission_slot || '?',
       'level candidate ' || mission_slot, level
from qb3.missions
where batch_id = :'level_terminality_batch_id';

select * from qb3.complete_batch(:'level_terminality_batch_id');

do $$
begin
  assert (
    select status = 'waiting_recovery'
    from qb3.campaigns where campaign_id = 'level-terminality-test'
  ), 'a mixed campaign must wait for recoverable candidate work before generating replacements';
  assert (
    select state = 'proposed'
    from qb3.candidates
    where campaign_id = 'level-terminality-test' and level = 'shallow'
  ), 'an accepted counter without a Ready Question cannot terminalize a level';
  assert (
    select state = 'proposed'
    from qb3.candidates
    where campaign_id = 'level-terminality-test' and level = 'deep'
  ), 'batch completion must preserve candidates for an unfinished level';
end;
$$;

insert into qb3.candidates (
  campaign_id, batch_id, mission_id, candidate_index, question_text,
  normalized_text, level
) values (
  'admission-test', :'test_batch_id', :'test_mission_id', 3,
  'A distinct candidate?', qb3.normalize_question('A distinct candidate?'), 'deep'
) returning candidate_id as candidate_three_id \gset

select * from qb3.store_candidate_embedding_and_find(
  :'candidate_three_id', array_fill(0.03::real, array[1536])::vector
);

insert into qb3.provider_attempts (
  attempt_id, campaign_id, batch_id, candidate_id, agent_role, provider,
  requested_model, reported_model, reasoning_setting, reservation_usd,
  actual_cost_usd, status, usage, completed_at
) values (
  'embedding-attempt-complete', 'admission-test', :'test_batch_id',
  :'candidate_three_id', 'embedding', 'openai', 'text-embedding-3-small',
  'text-embedding-3-small', 'none', 0.001000, 0.000001, 'reconciled',
  '{"total_tokens":5}'::jsonb, now()
);

do $$
declare
  v_accepted boolean;
  v_accept_reason text;
  v_reserved boolean;
  v_reason text;
  v_cached_result jsonb;
begin
  select accepted, reason into v_accepted, v_accept_reason
  from qb3.accept_candidate((
    select candidate_id from qb3.candidates
    where campaign_id = 'admission-test' and candidate_index = 3
  ));
  assert not v_accepted and v_accept_reason = 'campaign_not_accepting',
    'admission must stop atomically after the campaign becomes terminal';

  select reserved, reason, cached_result
  into v_reserved, v_reason, v_cached_result
  from qb3.reserve_provider_budget(
    'embedding-attempt-complete', 'admission-test',
    (select batch_id from qb3.batches where campaign_id = 'admission-test' and batch_index = 1),
    (select candidate_id from qb3.candidates where campaign_id = 'admission-test' and candidate_index = 3),
    null, 'embedding', 'openai',
    'text-embedding-3-small', 'none', 0.001000
  );

  assert not v_reserved and v_reason = 'idempotent_reconciled',
    'a completed embedding attempt must not call the provider again';
  assert v_cached_result ->> 'candidate_id' = (
        select candidate_id::text from qb3.candidates
        where campaign_id = 'admission-test' and candidate_index = 3
      )
      and jsonb_typeof(v_cached_result -> 'neighbours') = 'array',
    'a completed embedding attempt must return cached neighbours on resume';
end;
$$;

do $$
begin
  assert (
    select embedding is not null from qb3.candidates
    where campaign_id = 'admission-test' and candidate_index = 3
  ), 'embedding must be stored once on the candidate before semantic judgment';
end;
$$;

select * from qb3.apply_candidate_decision(
  :'candidate_three_id', 'semantic_duplicate',
  '["same_scenario"]'::jsonb, 'Same scenario and answer space',
  '{"verdict":"duplicate"}'::jsonb
);

do $$
begin
  assert (
    select state = 'semantic_duplicate'
      and rejection_reason_codes = '["same_scenario"]'::jsonb
    from qb3.candidates
    where campaign_id = 'admission-test' and candidate_index = 3
  ), 'deterministic decision must persist state and feedback';
end;
$$;

insert into qb3.candidates (
  campaign_id, batch_id, mission_id, candidate_index, question_text,
  normalized_text, level
) values (
  'admission-test', :'test_batch_id', :'test_mission_id', 4,
  'A provider-failure candidate?', qb3.normalize_question('A provider-failure candidate?'), 'deep'
) returning candidate_id as candidate_four_id \gset

select * from qb3.mark_candidates_operationally_unresolved(
  :'test_batch_id', jsonb_build_array(:'candidate_four_id'),
  'semantic', 'Provider did not return a usable decision'
);

do $$
begin
  assert (
    select state = 'operationally_unresolved'
      and rejection_reason_codes = '["provider_failure_semantic"]'::jsonb
    from qb3.candidates
    where campaign_id = 'admission-test' and candidate_index = 4
  ), 'provider failure must affect only the supplied candidate ids';
  assert (
    select state = 'semantic_duplicate'
    from qb3.candidates
    where campaign_id = 'admission-test' and candidate_index = 3
  ), 'isolated provider failure must preserve unaffected candidate outcomes';
end;
$$;

select qb3.refresh_distribution_snapshot('admission-test', :'test_batch_id') as snapshot_id \gset

do $$
begin
  assert (
    select accepted_total = 2
    from qb3.distribution_snapshots
    where campaign_id = 'admission-test'
    order by created_at desc
    limit 1
  ), 'distribution snapshot must count accepted questions only';
  assert (
    select (summary #>> '{levels,deep}')::integer = 1
      and (summary #>> '{levels,shallow}')::integer = 0
      and (summary ->> 'ready_total')::integer = 1
    from qb3.distribution_snapshots
    where campaign_id = 'admission-test'
    order by created_at desc
    limit 1
  ), 'distribution dimensions must exclude admitted questions still missing metadata';
end;
$$;

rollback;

\echo 'Question Bank v3 SQL contract tests passed.'
