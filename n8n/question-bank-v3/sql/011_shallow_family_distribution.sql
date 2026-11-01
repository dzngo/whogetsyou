-- Future shallow questions carry a lightweight family label in metadata_result.
-- Older accepted questions deliberately remain visible as "unclassified" rather
-- than being retroactively guessed or rewritten.
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
  v_ready_total integer;
begin
  select count(*)::integer into v_accepted_total from qb3.questions;
  select count(*)::integer into v_ready_total from qb3.ready_questions;

  with recent_batches as (
    select b.batch_id from qb3.batches b
    where b.status = 'completed' and b.campaign_id = p_campaign_id
    order by b.completed_at desc nulls last limit 5
  ), recent_candidates as (
    select c.* from qb3.candidates c where c.batch_id in (select batch_id from recent_batches)
  ), recent_attempts as (
    select p.* from qb3.provider_attempts p where p.batch_id in (select batch_id from recent_batches)
  )
  select jsonb_build_object(
    'accepted_total', v_accepted_total,
    'ready_total', v_ready_total,
    'levels', (select jsonb_build_object('shallow', count(*) filter (where q.level = 'shallow'), 'deep', count(*) filter (where q.level = 'deep')) from qb3.ready_questions q),
    'forms', coalesce((select jsonb_object_agg(form_name, form_count) from (select coalesce(question_form, 'unclassified') form_name, count(*) form_count from qb3.ready_questions group by 1) f), '{}'::jsonb),
    'shallow_families', coalesce((select jsonb_object_agg(family_name, family_count) from (
      select coalesce(nullif(c.metadata_result ->> 'shallow_family', ''), 'unclassified') family_name, count(*) family_count
      from qb3.ready_questions q join qb3.candidates c using (candidate_id)
      where q.level = 'shallow' group by 1
    ) sf), '{}'::jsonb),
    'scenario_presence', (select jsonb_build_object('present', count(*) filter (where scenario_present is true), 'absent', count(*) filter (where scenario_present is false), 'unclassified', count(*) filter (where scenario_present is null)) from qb3.ready_questions),
    'contrast_presence', (select jsonb_build_object('present', count(*) filter (where contrast_present is true), 'absent', count(*) filter (where contrast_present is false), 'unclassified', count(*) filter (where contrast_present is null)) from qb3.ready_questions),
    'themes', coalesce((select jsonb_object_agg(t.theme_code, jsonb_build_object('count', coalesce(tc.question_count, 0), 'percentage', case when v_ready_total = 0 then 0 else round(100.0 * coalesce(tc.question_count, 0) / v_ready_total, 2) end)) from qb3.themes t left join (select theme_code, count(*) question_count from qb3.question_themes group by theme_code) tc using (theme_code) where t.active), '{}'::jsonb),
    'without_theme', (select count(*) from qb3.ready_questions q where not exists (select 1 from qb3.question_themes qt where qt.question_id = q.question_id)),
    'theme_combinations', coalesce((select jsonb_agg(to_jsonb(combo) order by combo.question_count desc, combo.theme_codes) from (select theme_codes, count(*) question_count from (select array_agg(qt.theme_code order by qt.theme_code) theme_codes from qb3.question_themes qt group by qt.question_id) per_question group by theme_codes) combo), '[]'::jsonb),
    'representative_recent_accepted', coalesce((select jsonb_agg(to_jsonb(r) order by r.accepted_at desc) from (select q.question_id, q.question_text, q.level, q.question_form, q.accepted_at from qb3.ready_questions q order by q.accepted_at desc limit 20) r), '[]'::jsonb),
    'recent_activity', jsonb_build_object('batch_count', (select count(*) from recent_batches), 'candidate_count', (select count(*) from recent_candidates), 'accepted_count', (select count(*) from recent_candidates where state = 'accepted'), 'acceptance_rate', (select case when count(*) = 0 then 0 else round(100.0 * count(*) filter (where state = 'accepted') / count(*), 2) end from recent_candidates), 'quality_rejected_count', (select count(*) from recent_candidates where state = 'quality_rejected'), 'quality_rejection_rate', (select case when count(*) = 0 then 0 else round(100.0 * count(*) filter (where state = 'quality_rejected') / count(*), 2) end from recent_candidates), 'semantic_duplicate_count', (select count(*) from recent_candidates where state in ('exact_duplicate', 'semantic_duplicate')), 'semantic_duplicate_rate', (select case when count(*) = 0 then 0 else round(100.0 * count(*) filter (where state in ('exact_duplicate', 'semantic_duplicate')) / count(*), 2) end from recent_candidates), 'uncertainty_count', (select count(*) from recent_candidates where state = 'awaiting_human_review'), 'uncertainty_rate', (select case when count(*) = 0 then 0 else round(100.0 * count(*) filter (where state = 'awaiting_human_review') / count(*), 2) end from recent_candidates), 'provider_failure_count', (select count(*) from recent_attempts where status in ('released', 'unknown_spend', 'reservation_exceeded')), 'provider_failure_rate', (select case when count(*) = 0 then 0 else round(100.0 * count(*) filter (where status in ('released', 'unknown_spend', 'reservation_exceeded')) / count(*), 2) end from recent_attempts)),
    'rejection_reasons', coalesce((select jsonb_agg(jsonb_build_object('reason_code', reason_code, 'count', reason_count) order by reason_count desc, reason_code) from (select reason_code, count(*) reason_count from recent_candidates c cross join lateral jsonb_array_elements_text(c.rejection_reason_codes) reason_code group by reason_code limit 30) reasons), '[]'::jsonb),
    'feedback_notes', coalesce((select jsonb_agg(feedback_note order by created_at desc) from (select feedback_note, created_at from recent_candidates where feedback_note is not null and btrim(feedback_note) <> '' order by created_at desc limit 30) notes), '[]'::jsonb),
    'recent_missions', coalesce((select jsonb_agg(jsonb_build_object('mission_id', m.mission_id, 'level', m.level, 'mission', m.mission, 'accepted_count', coalesce(mc.accepted_count, 0), 'duplicate_count', coalesce(mc.duplicate_count, 0), 'quality_rejected_count', coalesce(mc.quality_rejected_count, 0)) order by m.created_at desc) from qb3.missions m left join (select mission_id, count(*) filter (where state = 'accepted') accepted_count, count(*) filter (where state in ('exact_duplicate', 'semantic_duplicate')) duplicate_count, count(*) filter (where state = 'quality_rejected') quality_rejected_count from qb3.candidates group by mission_id) mc using (mission_id) where m.batch_id in (select batch_id from recent_batches)), '[]'::jsonb)
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
