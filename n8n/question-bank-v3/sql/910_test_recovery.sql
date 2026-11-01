\set ON_ERROR_STOP on

begin;

insert into qb3.prompt_snapshots (registry_snapshot, configuration_hash)
values ('{}'::jsonb, 'recovery-contract-test')
returning prompt_snapshot_id as recovery_prompt_id \gset

insert into qb3.campaigns (
  campaign_id, campaign_name, raw_input, level_mode, accepted_target,
  shallow_target, deep_target, authorized_budget_usd,
  prompt_snapshot_id, emergency_batch_ceiling
) values (
  'recovery-contract-test', 'Recovery contract test', '{}'::jsonb,
  'shallow', 12, 12, 0, 1.000000, :'recovery_prompt_id', 4
);

do $$
begin
  assert qb3.claim_campaign_worker('recovery-contract-test', 'worker-a'),
    'first campaign worker must acquire the lease';
  assert not qb3.claim_campaign_worker('recovery-contract-test', 'worker-b'),
    'second campaign worker must be excluded';
  assert qb3.claim_campaign_worker('recovery-contract-test', 'worker-a'),
    'owner may renew its lease';
  assert qb3.renew_campaign_worker('recovery-contract-test', 'worker-a'),
    'only the current owner may extend its lease during long work';
  begin
    perform qb3.renew_campaign_worker('recovery-contract-test', 'worker-b');
    assert false, 'a competing worker must not renew the lease';
  exception when raise_exception then
    null;
  end;
  assert not qb3.release_campaign_worker('recovery-contract-test', 'worker-b'),
    'a competing worker cannot release the owner';
  assert qb3.release_campaign_worker('recovery-contract-test', 'worker-a'),
    'owner may release its lease';
  assert qb3.claim_campaign_worker('recovery-contract-test', 'worker-b'),
    'another worker may acquire after release';
  assert qb3.release_campaign_worker('recovery-contract-test', 'worker-b'),
    'new owner may release';
end;
$$;

select batch_id as recovery_batch_id
from qb3.begin_next_batch('recovery-contract-test') \gset

insert into qb3.missions (
  campaign_id, batch_id, mission_slot, level, observation_report, mission
) values (
  'recovery-contract-test', :'recovery_batch_id', 1, 'shallow',
  '{}'::jsonb, '{}'::jsonb
) returning mission_id as recovery_mission_id \gset

do $$
declare
  v_id uuid;
  v_batch uuid;
  v_mission uuid;
begin
  select b.batch_id into v_batch from qb3.batches b
  where b.campaign_id = 'recovery-contract-test';
  select m.mission_id into v_mission from qb3.missions m
  where m.campaign_id = 'recovery-contract-test';
  for i in 1..12 loop
    insert into qb3.candidates (
      campaign_id, batch_id, mission_id, candidate_index,
      question_text, normalized_text, level, embedding
    ) values (
      'recovery-contract-test', v_batch, v_mission, i,
      'Recovery question ' || i || '?', 'recovery question ' || i,
      'shallow', array_fill(0.01::real, array[1536])::vector
    ) returning candidate_id into v_id;
    perform * from qb3.accept_candidate(v_id);
  end loop;

  assert (select count(*) = 12 from qb3.candidate_stage_work w
          join qb3.candidates c using (candidate_id)
          where c.campaign_id = 'recovery-contract-test'
            and w.stage = 'metadata' and w.status = 'pending'),
    'admission must create one pending metadata work item per question';
  assert (select count(*) = 0 from qb3.ready_questions q
          join qb3.candidates c using (candidate_id)
          where c.campaign_id = 'recovery-contract-test'),
    'accepted questions without metadata must not be ready';
end;
$$;

select work_group_id as recovery_group_id,
       jsonb_array_length(questions) as recovery_group_size
from qb3.claim_metadata_group('recovery-contract-test', :'recovery_batch_id') \gset

do $$
begin
  assert (select count(*) = 12 from qb3.candidate_stage_work w
          join qb3.candidates c using (candidate_id)
          where c.campaign_id = 'recovery-contract-test'
            and w.stage = 'metadata' and w.status = 'running'),
    'first metadata claim must contain all 12';
end;
$$;

select * from qb3.reserve_metadata_attempt(
  'recovery-metadata-o1', 'recovery-contract-test',
  :'recovery_batch_id', null, 'test-model', 'low', 0.040000,
  :'recovery_group_id'
);

select qb3.mark_provider_attempt_sending('recovery-metadata-o1');
select * from qb3.reconcile_provider_attempt(
  'recovery-metadata-o1', 0.010000, 'test-model', '{}'::jsonb
);

do $$
declare
  v_items jsonb;
  v_applied jsonb;
  v_pending jsonb;
  v_invalid jsonb;
begin
  select jsonb_agg(jsonb_build_object(
    'candidate_id', candidate_id,
    'themes', jsonb_build_array('yourself'),
    'question_form', 'direct',
    'scenario_present', false,
    'contrast_present', false,
    'aspect', 'routine',
    'scenario', null,
    'perspective', 'habit',
    'answer_space', 'activities',
    'contrast', null
  ) order by candidate_index) into v_items
  from qb3.candidates
  where campaign_id = 'recovery-contract-test' and candidate_index <= 8;

  select applied_ids, pending_ids, invalid_items
  into v_applied, v_pending, v_invalid
  from qb3.apply_metadata_group_partial(
    (select work_group_id from qb3.provider_attempts
     where attempt_id = 'recovery-metadata-o1'), v_items
  );

  assert jsonb_array_length(v_applied) = 8, 'valid partial metadata must be saved';
  assert jsonb_array_length(v_pending) = 4, 'only four questions must remain pending';
  assert jsonb_array_length(v_invalid) = 0, 'valid items must not be rejected';
  assert (select count(*) = 8 from qb3.ready_questions q
          join qb3.candidates c using (candidate_id)
          where c.campaign_id = 'recovery-contract-test'),
    'ready view must contain exactly the metadata-complete questions';

  select applied_ids, pending_ids into v_applied, v_pending
  from qb3.apply_metadata_items_partial('recovery-metadata-o1', v_items);
  assert jsonb_array_length(v_applied) = 0 and jsonb_array_length(v_pending) = 4,
    'replaying a callback must not rewrite completed metadata';
end;
$$;

update qb3.candidate_stage_work w
set next_retry_at = now() - interval '1 second'
from qb3.candidates c
where w.candidate_id = c.candidate_id and w.stage = 'metadata'
  and c.campaign_id = 'recovery-contract-test' and w.status = 'retry_wait';

select work_group_id as recovery_second_group_id,
       jsonb_array_length(questions) as recovery_second_group_size
from qb3.claim_metadata_group('recovery-contract-test', :'recovery_batch_id') \gset

do $$
begin
  assert (select count(*) = 4 from qb3.candidate_stage_work w
          join qb3.candidates c using (candidate_id)
          where c.campaign_id = 'recovery-contract-test'
            and w.stage = 'metadata' and w.status = 'running'),
    'resumed metadata request must contain only the unfinished four';
end;
$$;

select * from qb3.reserve_metadata_attempt(
  'recovery-metadata-o2', 'recovery-contract-test',
  :'recovery_batch_id', 'recovery-metadata-o1', 'test-model', 'low',
  0.040000, :'recovery_second_group_id'
);
select qb3.mark_provider_attempt_sending('recovery-metadata-o2');
update qb3.provider_attempts
set lease_expires_at = now() - interval '1 second'
where attempt_id = 'recovery-metadata-o2';
select * from qb3.recover_expired_provider_attempts('recovery-contract-test');

do $$
begin
  assert (select status = 'unknown_spend' from qb3.provider_attempts
          where attempt_id = 'recovery-metadata-o2'),
    'an expired sent attempt must retain unknown spend';
  assert (select status = 'running' and unknown_spend_usd = 0.040000
          from qb3.campaigns where campaign_id = 'recovery-contract-test'),
    'unknown spend must count against budget without stopping safe recovery';
  assert (select count(*) = 4 from qb3.candidate_stage_work w
          join qb3.candidates c using (candidate_id)
          where c.campaign_id = 'recovery-contract-test'
            and w.stage = 'metadata' and w.status = 'retry_wait'
            and w.attempt_count = 2),
    'all four affected questions should wait for their final allowed attempt';
end;
$$;

update qb3.candidate_stage_work w
set next_retry_at = now() - interval '1 second'
from qb3.candidates c
where w.candidate_id = c.candidate_id and w.stage = 'metadata'
  and c.campaign_id = 'recovery-contract-test' and w.status = 'retry_wait';

select work_group_id as recovery_third_group_id
from qb3.claim_metadata_group('recovery-contract-test', :'recovery_batch_id') \gset

select * from qb3.reserve_metadata_attempt(
  'recovery-metadata-o3', 'recovery-contract-test',
  :'recovery_batch_id', 'recovery-metadata-o2', 'test-model', 'low',
  0.040000, :'recovery_third_group_id'
);

-- The worker crashes between reservation and the durable pre-send marker.
update qb3.provider_attempts
set lease_expires_at = now() - interval '1 second'
where attempt_id = 'recovery-metadata-o3';
select * from qb3.recover_expired_provider_attempts('recovery-contract-test');

do $$
begin
  assert (select status = 'released' from qb3.provider_attempts
          where attempt_id = 'recovery-metadata-o3'),
    'an expired pre-send reservation must be released';
  assert (select unknown_spend_usd = 0.040000 and reserved_usd = 0
          from qb3.campaigns where campaign_id = 'recovery-contract-test'),
    'pre-send recovery must not increase unknown spend';
  assert (select count(*) = 4 from qb3.candidate_stage_work w
          join qb3.candidates c using (candidate_id)
          where c.campaign_id = 'recovery-contract-test'
            and w.stage = 'metadata' and w.status = 'needs_attention'
            and w.attempt_count = 3),
    'three failed attempts must exhaust retry allowance per question';
end;
$$;

-- An authoritative response can arrive after an unknown-spend lease was
-- settled. Its exact attempt is reconciled, then its still-unfinished members
-- can be applied without buying or admitting them again.
select * from qb3.reconcile_provider_attempt(
  'recovery-metadata-o2', 0.015000, 'test-model', '{}'::jsonb
);

do $$
declare
  v_items jsonb;
  v_applied jsonb;
  v_pending jsonb;
begin
  select jsonb_agg(jsonb_build_object(
    'candidate_id', candidate_id,
    'themes', jsonb_build_array('yourself'),
    'question_form', 'direct',
    'scenario_present', false,
    'contrast_present', false,
    'aspect', 'routine',
    'scenario', null,
    'perspective', 'habit',
    'answer_space', 'activities',
    'contrast', null
  ) order by candidate_index) into v_items
  from qb3.candidates
  where campaign_id = 'recovery-contract-test' and candidate_index > 8;

  select applied_ids, pending_ids into v_applied, v_pending
  from qb3.apply_metadata_group_partial(
    (select work_group_id from qb3.provider_attempts
     where attempt_id = 'recovery-metadata-o2'), v_items
  );
  assert jsonb_array_length(v_applied) = 4
    and jsonb_array_length(v_pending) = 0,
    'late authoritative result must finish only the missing four';
  assert (select unknown_spend_usd = 0 and spent_usd = 0.025000
          from qb3.campaigns where campaign_id = 'recovery-contract-test'),
    'late reconciliation must release the unknown-spend hold exactly once';
  assert (select count(*) = 12 from qb3.ready_questions q
          join qb3.candidates c using (candidate_id)
          where c.campaign_id = 'recovery-contract-test'),
    'all twelve accepted questions should now be ready';
end;
$$;

-- Every non-metadata stage must claim exact members, consume a fresh tracked
-- attempt on retry, and preserve the candidate's admission decision.
do $$
declare
  v_batch uuid;
  v_mission uuid;
  v_candidate uuid;
  v_group text;
  v_items jsonb;
  v_reserved boolean;
begin
  insert into qb3.campaigns (
    campaign_id, campaign_name, raw_input, level_mode, accepted_target,
    shallow_target, deep_target, authorized_budget_usd,
    prompt_snapshot_id, emergency_batch_ceiling
  ) values (
    'stage-contract-test', 'Stage contract test', '{}'::jsonb,
    'shallow', 1, 1, 0, 1.000000,
    (select prompt_snapshot_id from qb3.campaigns
     where campaign_id = 'recovery-contract-test'), 4
  );
  select batch_id into v_batch
  from qb3.begin_next_batch('stage-contract-test');
  insert into qb3.missions (
    campaign_id, batch_id, mission_slot, level, observation_report, mission
  ) values (
    'stage-contract-test', v_batch, 1, 'shallow', '{}'::jsonb, '{}'::jsonb
  ) returning mission_id into v_mission;
  insert into qb3.candidates (
    campaign_id, batch_id, mission_id, candidate_index,
    question_text, normalized_text, level
  ) values (
    'stage-contract-test', v_batch, v_mission, 1,
    'Which breakfast do I usually choose?', 'which breakfast do i usually choose',
    'shallow'
  ) returning candidate_id into v_candidate;

  assert qb3.stage_due_count(v_batch, 'quality') = 1,
    'unjudged question must be due for quality';
  select work_group_id, candidates into v_group, v_items
  from qb3.claim_candidate_stage_group(v_batch, 'quality', 10);
  assert jsonb_array_length(v_items) = 1,
    'quality claim must contain only the due candidate';
  assert qb3.stage_due_count(v_batch, 'quality') = 0,
    'a claimed question cannot be claimed twice';
  select reserved into v_reserved from qb3.reserve_provider_budget_dispatch(
    'stage-quality-o1', 'stage-contract-test', v_batch, null::uuid,
    null, 'quality_judge', 'openai', 'test-model', 'medium', 0.020000,
    v_group
  );
  assert v_reserved, 'quality reservation must attach its group';
  assert (select attempt_count = 1 from qb3.candidate_stage_work
          where candidate_id = v_candidate and stage = 'quality'),
    'one reserved quality attempt must count exactly once';
  assert (select count(*) = 1 from qb3.provider_attempt_candidates
          where attempt_id = 'stage-quality-o1' and candidate_id = v_candidate),
    'the group membership must identify the exact question';
  perform qb3.mark_provider_attempt_sending('stage-quality-o1');
  perform * from qb3.release_provider_attempt(
    'stage-quality-o1', '{"status_code":503}'::jsonb
  );
  perform * from qb3.finish_candidate_stage_group_failure(
    v_group, 'quality', 'provider_http_503', true
  );
  assert (select status = 'retry_wait' and attempt_count = 1
          from qb3.candidate_stage_work
          where candidate_id = v_candidate and stage = 'quality'),
    'confirmed 503 must wait with one counted attempt';
  assert (select state = 'operationally_unresolved'
          from qb3.candidates where candidate_id = v_candidate),
    'technical failure must not become an admission verdict';

  update qb3.candidate_stage_work
  set next_retry_at = now() - interval '1 second'
  where candidate_id = v_candidate and stage = 'quality';
  select work_group_id into v_group
  from qb3.claim_candidate_stage_group(v_batch, 'quality', 10);
  assert v_group is not null,
    'the same technical candidate must re-enter its quality stage';
  assert (select state = 'proposed' from qb3.candidates
          where candidate_id = v_candidate),
    're-entering a technical stage must not alter a final admission outcome';
  select reserved into v_reserved from qb3.reserve_provider_budget_dispatch(
    'stage-quality-o2', 'stage-contract-test', v_batch, null::uuid,
    'stage-quality-o1', 'quality_judge', 'openai', 'test-model',
    'medium', 0.020000, v_group
  );
  assert v_reserved, 'retry must use a new provider attempt id';
  perform qb3.mark_provider_attempt_sending('stage-quality-o2');
  perform * from qb3.reconcile_provider_attempt(
    'stage-quality-o2', 0.010000, 'test-model', '{}'::jsonb
  );
  perform * from qb3.apply_quality_results(v_batch, jsonb_build_array(
    jsonb_build_object('candidate_id', v_candidate, 'verdict', 'pass')
  ), false);
  assert (select status = 'complete' and attempt_count = 2
          from qb3.candidate_stage_work
          where candidate_id = v_candidate and stage = 'quality'),
    'successful retry completes quality after exactly two attempts';

  select work_group_id into v_group
  from qb3.claim_candidate_stage_group(v_batch, 'embedding', 1);
  assert v_group is not null, 'quality pass must unlock embedding';
  select reserved into v_reserved from qb3.reserve_provider_budget_dispatch(
    'stage-embedding-o1', 'stage-contract-test', v_batch, v_candidate,
    null, 'embedding', 'openai', 'text-embedding-3-small',
    'none', 0.001000, v_group
  );
  assert v_reserved, 'embedding reservation must be candidate-scoped';
  perform qb3.mark_provider_attempt_sending('stage-embedding-o1');
  perform * from qb3.reconcile_provider_attempt(
    'stage-embedding-o1', 0.000100, 'text-embedding-3-small', '{}'::jsonb
  );
  perform * from qb3.store_candidate_embedding_and_find(
    v_candidate, array_fill(0.01::real, array[1536])::vector
  );
  assert (select status = 'complete' from qb3.candidate_stage_work
          where candidate_id = v_candidate and stage = 'embedding'),
    'stored vector must complete embedding';

  select work_group_id into v_group
  from qb3.claim_candidate_stage_group(v_batch, 'semantic', 1);
  assert v_group is not null, 'embedding must unlock semantic work';
  select reserved into v_reserved from qb3.reserve_provider_budget_dispatch(
    'stage-semantic-o1', 'stage-contract-test', v_batch, v_candidate,
    null, 'semantic_judge', 'openai', 'test-model',
    'medium', 0.020000, v_group
  );
  assert v_reserved, 'semantic decision must have exact membership';
  perform qb3.mark_provider_attempt_sending('stage-semantic-o1');
  perform * from qb3.reconcile_provider_attempt(
    'stage-semantic-o1', 0.010000, 'test-model', '{}'::jsonb
  );
  perform * from qb3.apply_semantic_results(v_batch, jsonb_build_array(
    jsonb_build_object('candidate_id', v_candidate, 'verdict', 'distinct')
  ));
  assert (select status = 'complete' from qb3.candidate_stage_work
          where candidate_id = v_candidate and stage = 'semantic'),
    'semantic decision must complete its stage';
  assert (select state = 'accepted' from qb3.candidates
          where candidate_id = v_candidate),
    'only the semantic verdict may admit the question';

  -- An uncertain quality verdict is a successful first-stage result. Its
  -- escalation gets a separate three-attempt allowance even when the first
  -- judge consumed retries.
  insert into qb3.candidates (
    campaign_id, batch_id, mission_id, candidate_index,
    question_text, normalized_text, level
  ) values (
    'stage-contract-test', v_batch, v_mission, 2,
    'Which snack do I take on a trip?', 'which snack do i take on a trip',
    'shallow'
  ) returning candidate_id into v_candidate;
  for i in 1..3 loop
    select work_group_id into v_group
    from qb3.claim_candidate_stage_group(v_batch, 'quality', 10);
    assert v_group is not null, 'quality retries must remain claimable';
    select reserved into v_reserved from qb3.reserve_provider_budget_dispatch(
      'uncertain-quality-' || i, 'stage-contract-test', v_batch,
      null::uuid, null, 'quality_judge', 'openai', 'test-model',
      'medium', 0.010000, v_group
    );
    assert v_reserved, 'each retry must reserve its own attempt';
    perform qb3.mark_provider_attempt_sending('uncertain-quality-' || i);
    if i < 3 then
      perform * from qb3.release_provider_attempt(
        'uncertain-quality-' || i, '{"status_code":503}'::jsonb
      );
      perform * from qb3.finish_candidate_stage_group_failure(
        v_group, 'quality', 'provider_http_503', true
      );
      update qb3.candidate_stage_work
      set next_retry_at = now() - interval '1 second'
      where candidate_id = v_candidate and stage = 'quality';
    else
      perform * from qb3.reconcile_provider_attempt(
        'uncertain-quality-' || i, 0.005000, 'test-model', '{}'::jsonb
      );
      perform * from qb3.apply_quality_results(v_batch, jsonb_build_array(
        jsonb_build_object('candidate_id', v_candidate, 'verdict', 'uncertain')
      ), false);
    end if;
  end loop;
  assert (select status = 'complete' and attempt_count = 3
          from qb3.candidate_stage_work
          where candidate_id = v_candidate and stage = 'quality'),
    'successful uncertain verdict completes the initial judge';
  assert (select status = 'pending' and attempt_count = 0
          from qb3.candidate_stage_work
          where candidate_id = v_candidate and stage = 'quality_escalation'),
    'escalation must have its own unspent retry allowance';
  select work_group_id into v_group
  from qb3.claim_candidate_stage_group(v_batch, 'quality', 10, true);
  assert v_group is not null, 'uncertain quality needs escalation';
  select reserved into v_reserved from qb3.reserve_provider_budget_dispatch(
    'quality-escalation-o1', 'stage-contract-test', v_batch,
    null::uuid, null, 'quality_escalation', 'openai', 'test-model',
    'high', 0.010000, v_group
  );
  assert v_reserved, 'escalation reservation must have exact membership';
  assert (select count(*) = 1 from qb3.provider_attempt_candidates
          where attempt_id = 'quality-escalation-o1'
            and candidate_id = v_candidate and stage = 'quality_escalation'),
    'escalation attempt must name its candidate and stage';
  perform qb3.mark_provider_attempt_sending('quality-escalation-o1');
  perform * from qb3.reconcile_provider_attempt(
    'quality-escalation-o1', 0.005000, 'test-model', '{}'::jsonb
  );
  perform * from qb3.apply_quality_results(v_batch, jsonb_build_array(
    jsonb_build_object('candidate_id', v_candidate, 'verdict', 'uncertain')
  ), true);
  assert (select status = 'complete'
          from qb3.candidate_stage_work
          where candidate_id = v_candidate and stage = 'quality_escalation'),
    'escalated uncertainty must end in human review, not an endless retry';

  -- Six recent definite 503s across the campaign are a provider-wide
  -- outage, not six unrelated questions to keep buying replacements for.
  for i in 1..3 loop
    select reserved into v_reserved from qb3.reserve_provider_budget_dispatch(
      'outage-baseline-' || i, 'stage-contract-test', v_batch,
      null::uuid, null, 'creative', 'openai', 'test-model',
      'high', 0.001000
    );
    assert v_reserved, 'outage test setup must reserve a tracked attempt';
    perform * from qb3.release_provider_attempt(
      'outage-baseline-' || i, '{"status_code":503}'::jsonb
    );
  end loop;
  insert into qb3.candidates (
    campaign_id, batch_id, mission_id, candidate_index,
    question_text, normalized_text, level
  ) values (
    'stage-contract-test', v_batch, v_mission, 3,
    'What is my usual weekend drink?', 'what is my usual weekend drink',
    'shallow'
  ) returning candidate_id into v_candidate;
  select work_group_id into v_group
  from qb3.claim_candidate_stage_group(v_batch, 'quality', 10);
  select reserved into v_reserved from qb3.reserve_provider_budget_dispatch(
    'outage-quality-o1', 'stage-contract-test', v_batch,
    null::uuid, null, 'quality_judge', 'openai', 'test-model',
    'medium', 0.010000, v_group
  );
  assert v_reserved, 'outage candidate attempt must reserve';
  perform qb3.mark_provider_attempt_sending('outage-quality-o1');
  perform * from qb3.release_provider_attempt(
    'outage-quality-o1', '{"status_code":503}'::jsonb
  );
  perform * from qb3.finish_candidate_stage_group_failure(
    v_group, 'quality', 'openai_http_503', true
  );
  assert (select status = 'provider_outage' from qb3.campaigns
          where campaign_id = 'stage-contract-test'),
    'persistent 503s must pause the whole campaign';
  perform * from qb3.complete_batch(v_batch);
  assert (select status = 'provider_outage' from qb3.campaigns
          where campaign_id = 'stage-contract-test'),
    'batch completion must preserve the provider-outage pause';
end;
$$;

rollback;
