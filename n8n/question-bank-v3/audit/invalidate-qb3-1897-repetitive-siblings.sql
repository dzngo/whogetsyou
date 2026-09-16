\set ON_ERROR_STOP on

begin;

create temporary table qb3_qualification_anchors (
  candidate_id uuid primary key
) on commit drop;

insert into qb3_qualification_anchors (candidate_id) values
  ('9cbb9411-0ae7-4c26-a236-44f5b9975ed0'),
  ('c254ab72-2fd9-46e9-908b-0eecc8af09fb'),
  ('c90a2ce2-be8c-43d6-b9e9-9003880d7b1a'),
  ('b4f7c577-0b29-46e2-888e-5b2f6915fadb'),
  ('a0bd8da7-b981-4259-bdf6-ce3ff3da0628');

create temporary table qb3_repetitive_siblings on commit drop as
select c.candidate_id
from qb3.questions q
join qb3.candidates c on c.candidate_id = q.candidate_id
where c.campaign_id = 'qb3-1897'
  and not exists (
    select 1
    from qb3_qualification_anchors anchor
    where anchor.candidate_id = c.candidate_id
  );

do $$
declare
  v_questions integer;
  v_anchors integer;
  v_siblings integer;
begin
  select count(*) into v_questions
  from qb3.questions q
  join qb3.candidates c on c.candidate_id = q.candidate_id
  where c.campaign_id = 'qb3-1897';

  select count(*) into v_anchors
  from qb3.questions q
  join qb3_qualification_anchors anchor on anchor.candidate_id = q.candidate_id;

  select count(*) into v_siblings from qb3_repetitive_siblings;

  if v_questions <> 20 or v_anchors <> 5 or v_siblings <> 15 then
    raise exception
      'Refusing sibling invalidation: expected questions/anchors/siblings 20/5/15, found %/%/%',
      v_questions,
      v_anchors,
      v_siblings;
  end if;
end;
$$;

delete from qb3.questions q
using qb3_repetitive_siblings sibling
where q.candidate_id = sibling.candidate_id;

update qb3.candidates c
set state = 'awaiting_human_review',
    semantic_result = coalesce(c.semantic_result, '{}'::jsonb) || jsonb_build_object(
      'qualification_invalidated', true,
      'qualification_invalidation_code', 'failed_qualification_repetitive_sibling',
      'qualification_invalidation_note',
        'Manual qualification review found that this question repeated the same mission territory, situation, or conversational reveal as a retained representative.'
    ),
    rejection_reason_codes = case
      when coalesce(c.rejection_reason_codes, '[]'::jsonb)
        @> '["failed_qualification_repetitive_sibling"]'::jsonb
        then coalesce(c.rejection_reason_codes, '[]'::jsonb)
      else coalesce(c.rejection_reason_codes, '[]'::jsonb)
        || '["failed_qualification_repetitive_sibling"]'::jsonb
    end,
    feedback_note =
      'Qualification invalidated: repetitive sibling within the same creative mission territory.',
    updated_at = now()
from qb3_repetitive_siblings sibling
where c.candidate_id = sibling.candidate_id;

insert into qb3.review_queue (candidate_id, review_type, status, evidence)
select
  sibling.candidate_id,
  'semantic',
  'open',
  jsonb_build_object(
    'reason_code', 'failed_qualification_repetitive_sibling',
    'reason', 'Repeated the same mission territory, situation, perspective, or conversational reveal as a retained representative.',
    'source_campaign_id', 'qb3-1897',
    'requires', 'human_review_or_future_campaign_requalification'
  )
from qb3_repetitive_siblings sibling
on conflict (candidate_id, review_type) do update
set status = 'open',
    evidence = excluded.evidence,
    resolution = null,
    resolved_at = null;

update qb3.campaigns campaign
set accepted_shallow = counts.accepted_shallow,
    accepted_deep = counts.accepted_deep,
    status = 'cancelled_partial',
    cancel_requested = true,
    notes = concat_ws(
      E'\n',
      nullif(campaign.notes, ''),
      'Qualification content review invalidated 15 repetitive sibling admissions; five representative anchors retained. Traces preserved.'
    ),
    completed_at = now(),
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
  v_campaign record;
  v_questions integer;
  v_reviews integer;
begin
  select status, accepted_shallow, accepted_deep
  into v_campaign
  from qb3.campaigns
  where campaign_id = 'qb3-1897';

  select count(*) into v_questions
  from qb3.questions q
  join qb3.candidates c on c.candidate_id = q.candidate_id
  where c.campaign_id = 'qb3-1897';

  select count(*) into v_reviews
  from qb3.review_queue r
  join qb3.candidates c on c.candidate_id = r.candidate_id
  where c.campaign_id = 'qb3-1897'
    and r.status = 'open'
    and r.evidence ->> 'reason_code' = 'failed_qualification_repetitive_sibling';

  if v_campaign.status <> 'cancelled_partial'
     or v_campaign.accepted_shallow <> 3
     or v_campaign.accepted_deep <> 2
     or v_questions <> 5
     or v_reviews <> 15 then
    raise exception
      'Sibling invalidation verification failed: status %, shallow %, deep %, questions %, reviews %',
      v_campaign.status,
      v_campaign.accepted_shallow,
      v_campaign.accepted_deep,
      v_questions,
      v_reviews;
  end if;
end;
$$;

commit;

select * from qb3.campaign_status where campaign_id = 'qb3-1897';

select c.level, c.question_text
from qb3.questions q
join qb3.candidates c on c.candidate_id = q.candidate_id
where c.campaign_id = 'qb3-1897'
order by c.level, c.question_text;
