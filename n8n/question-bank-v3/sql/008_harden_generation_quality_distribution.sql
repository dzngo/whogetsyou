\set ON_ERROR_STOP on

begin;

-- Upgrade path: enforce mission/quality completeness and campaign-scoped diversity evidence.
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

  if jsonb_typeof(p_questions) <> 'array' or jsonb_array_length(p_questions) <> 5 then
    raise exception 'a Creative invocation must contain exactly five questions';
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
  v_actual_count integer;
  v_distinct_count integer;
begin
  if jsonb_typeof(p_decisions) <> 'array' then
    raise exception 'quality decisions must be an array';
  end if;

  select count(*)::integer, count(distinct d.candidate_id)::integer
  into v_actual_count, v_distinct_count
  from (select (value ->> 'candidate_id')::uuid candidate_id
        from jsonb_array_elements(p_decisions)) d;

  if v_actual_count <> v_distinct_count then
    raise exception 'quality decisions must not repeat candidate ids';
  end if;

  for v_decision in select value from jsonb_array_elements(p_decisions)
  loop
    select * into v_candidate
    from qb3.candidates c
    where c.candidate_id = (v_decision ->> 'candidate_id')::uuid
      and c.batch_id = p_batch_id
      and c.state = 'proposed'
      and ((not p_escalation and c.quality_result is null)
        or (p_escalation and c.quality_result ->> 'verdict' = 'uncertain'))
    for update;

    if not found then
      raise exception 'quality decision references an ineligible candidate in batch %', p_batch_id;
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
    where b.status = 'completed' and b.campaign_id = p_campaign_id
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
      from (select theme_codes, count(*) question_count from (
              select array_agg(qt.theme_code order by qt.theme_code) theme_codes
              from qb3.question_themes qt group by qt.question_id
            ) per_question group by theme_codes) combo), '[]'::jsonb),
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

commit;
