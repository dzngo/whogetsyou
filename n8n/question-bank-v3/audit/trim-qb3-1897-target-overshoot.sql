\set ON_ERROR_STOP on

begin;

do $$
declare
  v_campaign record;
  v_questions integer;
begin
  select status, accepted_shallow, accepted_deep
  into v_campaign
  from qb3.campaigns
  where campaign_id = 'qb3-1897'
  for update;

  select count(*)
  into v_questions
  from qb3.questions q
  join qb3.candidates c on c.candidate_id = q.candidate_id
  where c.campaign_id = 'qb3-1897';

  if v_campaign.status <> 'running'
     or v_campaign.accepted_shallow <> 15
     or v_campaign.accepted_deep <> 10
     or v_questions <> 25 then
    raise exception
      'Refusing overshoot trim: expected running/15/10/25, found %/%/%/%',
      v_campaign.status,
      v_campaign.accepted_shallow,
      v_campaign.accepted_deep,
      v_questions;
  end if;
end;
$$;

create temporary table qb3_overshoot_candidates on commit drop as
select candidate_id
from (
  select
    c.candidate_id,
    row_number() over (order by q.accepted_at, c.candidate_index) as shallow_admission_number
  from qb3.questions q
  join qb3.candidates c on c.candidate_id = q.candidate_id
  where c.campaign_id = 'qb3-1897'
    and c.level = 'shallow'
) ranked
where shallow_admission_number > 10;

do $$
begin
  if (select count(*) from qb3_overshoot_candidates) <> 5 then
    raise exception 'Refusing overshoot trim: expected exactly 5 excess shallow admissions';
  end if;
end;
$$;

delete from qb3.questions q
using qb3_overshoot_candidates excess
where q.candidate_id = excess.candidate_id;

update qb3.candidates c
set state = 'awaiting_human_review',
    semantic_result = coalesce(c.semantic_result, '{}'::jsonb) || jsonb_build_object(
      'qualification_invalidated', true,
      'qualification_invalidation_code', 'qualification_target_overshoot',
      'qualification_invalidation_note',
        'Admission occurred after the campaign shallow target had already been reached.'
    ),
    rejection_reason_codes = case
      when coalesce(c.rejection_reason_codes, '[]'::jsonb)
        @> '["qualification_target_overshoot"]'::jsonb
        then coalesce(c.rejection_reason_codes, '[]'::jsonb)
      else coalesce(c.rejection_reason_codes, '[]'::jsonb)
        || '["qualification_target_overshoot"]'::jsonb
    end,
    feedback_note =
      'Qualification admission invalidated because it exceeded the campaign shallow target.',
    updated_at = now()
from qb3_overshoot_candidates excess
where c.candidate_id = excess.candidate_id;

insert into qb3.review_queue (candidate_id, review_type, status, evidence)
select
  excess.candidate_id,
  'semantic',
  'open',
  jsonb_build_object(
    'reason_code', 'qualification_target_overshoot',
    'reason', 'Admission occurred after the requested level target was reached.',
    'source_campaign_id', 'qb3-1897',
    'requires', 'human_review_or_future_campaign_requalification'
  )
from qb3_overshoot_candidates excess
on conflict (candidate_id, review_type) do update
set status = 'open',
    evidence = excluded.evidence,
    resolution = null,
    resolved_at = null;

update qb3.campaigns campaign
set accepted_shallow = counts.accepted_shallow,
    accepted_deep = counts.accepted_deep,
    cancel_requested = false,
    notes = concat_ws(
      E'\n',
      nullif(campaign.notes, ''),
      'Qualification target overshoot corrected: 5 surplus shallow admissions moved to review. Traces preserved.'
    ),
    updated_at = now()
from (
  select
    count(*) filter (where c.level = 'shallow')::integer as accepted_shallow,
    count(*) filter (where c.level = 'deep')::integer as accepted_deep
  from qb3.questions q
  join qb3.candidates c on c.candidate_id = q.candidate_id
  where c.campaign_id = 'qb3-1897'
) counts
where campaign.campaign_id = 'qb3-1897';

do $$
declare
  v_batch_id uuid;
begin
  select batch_id
  into v_batch_id
  from qb3.batches
  where campaign_id = 'qb3-1897'
    and status = 'running'
  order by batch_index desc
  limit 1;

  if v_batch_id is null then
    raise exception 'Expected a running qb3-1897 batch to finalize';
  end if;

  perform * from qb3.complete_batch(v_batch_id);
end;
$$;

do $$
declare
  v_campaign record;
  v_questions integer;
  v_reviews integer;
begin
  select status, accepted_shallow, accepted_deep, reserved_usd, unknown_spend_usd
  into v_campaign
  from qb3.campaigns
  where campaign_id = 'qb3-1897';

  select count(*)
  into v_questions
  from qb3.questions q
  join qb3.candidates c on c.candidate_id = q.candidate_id
  where c.campaign_id = 'qb3-1897';

  select count(*)
  into v_reviews
  from qb3.review_queue r
  join qb3.candidates c on c.candidate_id = r.candidate_id
  where c.campaign_id = 'qb3-1897'
    and r.status = 'open'
    and r.evidence ->> 'reason_code' = 'qualification_target_overshoot';

  if v_campaign.status <> 'completed'
     or v_campaign.accepted_shallow <> 10
     or v_campaign.accepted_deep <> 10
     or v_campaign.reserved_usd <> 0
     or v_campaign.unknown_spend_usd <> 0
     or v_questions <> 20
     or v_reviews <> 5 then
    raise exception
      'Overshoot correction verification failed: status %, shallow %, deep %, reserved %, unknown %, questions %, reviews %',
      v_campaign.status,
      v_campaign.accepted_shallow,
      v_campaign.accepted_deep,
      v_campaign.reserved_usd,
      v_campaign.unknown_spend_usd,
      v_questions,
      v_reviews;
  end if;
end;
$$;

commit;

select * from qb3.campaign_status where campaign_id = 'qb3-1897';

select state, count(*)
from qb3.candidates
where campaign_id = 'qb3-1897'
group by state
order by state;
