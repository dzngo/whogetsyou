\set ON_ERROR_STOP on

begin;

do $$
declare
  v_question_count integer;
  v_accepted_count integer;
begin
  select count(*)
  into v_question_count
  from qb3.questions q
  join qb3.candidates c on c.candidate_id = q.candidate_id
  where c.campaign_id = 'qb3-300';

  select count(*)
  into v_accepted_count
  from qb3.candidates c
  where c.campaign_id = 'qb3-300'
    and c.state = 'accepted';

  if v_question_count <> 27 or v_accepted_count <> 27 then
    raise exception
      'Refusing invalidation: expected 27 question rows and 27 accepted candidates, found % and %',
      v_question_count,
      v_accepted_count;
  end if;
end;
$$;

delete from qb3.questions q
using qb3.candidates c
where q.candidate_id = c.candidate_id
  and c.campaign_id = 'qb3-300'
  and c.state = 'accepted';

update qb3.candidates c
set state = 'awaiting_human_review',
    semantic_result = coalesce(c.semantic_result, '{}'::jsonb) || jsonb_build_object(
      'qualification_invalidated', true,
      'qualification_invalidation_code', 'failed_qualification_stale_same_batch_neighbours',
      'qualification_invalidation_note',
        'Admission was produced before sequential fresh-neighbour semantic checks were enabled.'
    ),
    rejection_reason_codes = case
      when coalesce(c.rejection_reason_codes, '[]'::jsonb)
        @> '["failed_qualification_stale_same_batch_neighbours"]'::jsonb
        then coalesce(c.rejection_reason_codes, '[]'::jsonb)
      else coalesce(c.rejection_reason_codes, '[]'::jsonb)
        || '["failed_qualification_stale_same_batch_neighbours"]'::jsonb
    end,
    feedback_note =
      'Qualification invalidated: semantic admission used stale same-batch neighbours; clean sequential requalification required.',
    updated_at = now()
where c.campaign_id = 'qb3-300'
  and c.state = 'accepted';

insert into qb3.review_queue (
  candidate_id,
  review_type,
  status,
  evidence
)
select
  c.candidate_id,
  'semantic',
  'open',
  jsonb_build_object(
    'reason_code', 'failed_qualification_stale_same_batch_neighbours',
    'reason', 'Admission was invalidated after repeated same-batch semantic clusters were found.',
    'preserved_original_semantic_result', c.semantic_result,
    'source_campaign_id', c.campaign_id,
    'requires', 'human_review_or_clean_sequential_requalification'
  )
from qb3.candidates c
where c.campaign_id = 'qb3-300'
  and c.state = 'awaiting_human_review'
  and c.rejection_reason_codes
    @> '["failed_qualification_stale_same_batch_neighbours"]'::jsonb
on conflict (candidate_id, review_type) do update
set status = 'open',
    evidence = excluded.evidence,
    resolution = null,
    resolved_at = null;

update qb3.campaigns c
set accepted_shallow = 0,
    accepted_deep = 0,
    status = 'cancelled_partial',
    cancel_requested = true,
    notes = concat_ws(
      E'\n',
      nullif(c.notes, ''),
      'Qualification invalidated: 27 admissions removed because semantic checks used stale same-batch neighbours. Provider and prompt traces preserved.'
    ),
    updated_at = now()
where c.campaign_id = 'qb3-300';

do $$
declare
  v_question_count integer;
  v_review_count integer;
  v_campaign record;
begin
  select count(*)
  into v_question_count
  from qb3.questions q
  join qb3.candidates c on c.candidate_id = q.candidate_id
  where c.campaign_id = 'qb3-300';

  select count(*)
  into v_review_count
  from qb3.candidates c
  join qb3.review_queue r on r.candidate_id = c.candidate_id
  where c.campaign_id = 'qb3-300'
    and c.state = 'awaiting_human_review'
    and c.rejection_reason_codes
      @> '["failed_qualification_stale_same_batch_neighbours"]'::jsonb
    and r.review_type = 'semantic'
    and r.status = 'open';

  select status, accepted_shallow, accepted_deep
  into v_campaign
  from qb3.campaigns
  where campaign_id = 'qb3-300';

  if v_question_count <> 0
     or v_review_count <> 27
     or v_campaign.status <> 'cancelled_partial'
     or v_campaign.accepted_shallow <> 0
     or v_campaign.accepted_deep <> 0 then
    raise exception
      'Invalidation verification failed: questions %, reviews %, status %, accepted shallow %, deep %',
      v_question_count,
      v_review_count,
      v_campaign.status,
      v_campaign.accepted_shallow,
      v_campaign.accepted_deep;
  end if;
end;
$$;

commit;

select
  c.campaign_id,
  c.status,
  c.accepted_shallow,
  c.accepted_deep,
  c.spent_usd,
  c.reserved_usd,
  c.unknown_spend_usd
from qb3.campaigns c
where c.campaign_id = 'qb3-300';

select c.state, count(*)
from qb3.candidates c
where c.campaign_id = 'qb3-300'
group by c.state
order by c.state;

select
  count(*) as invalidated_open_reviews
from qb3.review_queue r
join qb3.candidates c on c.candidate_id = r.candidate_id
where c.campaign_id = 'qb3-300'
  and r.review_type = 'semantic'
  and r.status = 'open'
  and r.evidence ->> 'reason_code' = 'failed_qualification_stale_same_batch_neighbours';

select
  count(*) as agent_runs,
  count(*) filter (
    where ar.rendered_prompt is null or btrim(ar.rendered_prompt) = ''
  ) as missing_prompt,
  count(*) filter (where ar.raw_response is null) as missing_raw
from qb3.agent_runs ar
where ar.campaign_id = 'qb3-300';
