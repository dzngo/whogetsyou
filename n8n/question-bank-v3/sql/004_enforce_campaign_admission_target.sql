\set ON_ERROR_STOP on

begin;

create or replace function qb3.accept_candidate(p_candidate_id uuid)
returns table (accepted boolean, question_id uuid, reason text)
language plpgsql
as $$
declare
  v_candidate qb3.candidates%rowtype;
  v_campaign qb3.campaigns%rowtype;
  v_question_id uuid;
begin
  select * into v_candidate
  from qb3.candidates
  where candidate_id = p_candidate_id
  for update;

  if not found then
    raise exception 'candidate % not found', p_candidate_id;
  end if;

  select q.question_id into v_question_id
  from qb3.questions q
  where q.candidate_id = p_candidate_id;

  if found then
    return query select true, v_question_id, 'idempotent_accepted';
    return;
  end if;

  if v_candidate.state <> 'proposed' then
    return query select false, null::uuid, 'candidate_not_proposed';
    return;
  end if;

  if v_candidate.embedding is null then
    return query select false, null::uuid, 'embedding_missing';
    return;
  end if;

  select * into v_campaign
  from qb3.campaigns
  where campaign_id = v_candidate.campaign_id
  for update;

  if v_campaign.status <> 'running' or v_campaign.cancel_requested then
    return query select false, null::uuid, 'campaign_not_accepting';
    return;
  end if;

  if (v_candidate.level = 'shallow'
      and v_campaign.accepted_shallow >= v_campaign.shallow_target)
     or (v_candidate.level = 'deep'
      and v_campaign.accepted_deep >= v_campaign.deep_target) then
    return query select false, null::uuid, 'level_target_reached';
    return;
  end if;

  if exists (
    select 1 from qb3.questions q
    where q.normalized_text = v_candidate.normalized_text
  ) then
    update qb3.candidates
    set state = 'exact_duplicate', feedback_note = 'Exact normalized duplicate'
    where candidate_id = p_candidate_id;
    return query select false, null::uuid, 'exact_duplicate';
    return;
  end if;

  insert into qb3.questions (
    candidate_id, question_text, normalized_text, level, embedding
  ) values (
    v_candidate.candidate_id, v_candidate.question_text,
    v_candidate.normalized_text, v_candidate.level, v_candidate.embedding
  ) returning qb3.questions.question_id into v_question_id;

  update qb3.candidates
  set state = 'accepted'
  where candidate_id = p_candidate_id;

  update qb3.campaigns
  set accepted_shallow = accepted_shallow
        + case when v_candidate.level = 'shallow' then 1 else 0 end,
      accepted_deep = accepted_deep
        + case when v_candidate.level = 'deep' then 1 else 0 end
  where campaign_id = v_candidate.campaign_id;

  return query select true, v_question_id, 'accepted';
exception
  when unique_violation then
    update qb3.candidates
    set state = 'exact_duplicate', feedback_note = 'Exact normalized duplicate'
    where candidate_id = p_candidate_id;
    return query select false, null::uuid, 'exact_duplicate';
end;
$$;

create or replace function qb3.get_metadata_group(p_batch_id uuid)
returns table (questions jsonb, themes jsonb)
language sql
stable
as $$
  select coalesce(jsonb_agg(jsonb_build_object(
           'candidate_id', c.candidate_id,
           'question', c.question_text,
           'level', c.level
         ) order by c.candidate_index) filter (where c.candidate_id is not null), '[]'::jsonb),
         (select coalesce(jsonb_agg(jsonb_build_object(
            'theme_code', t.theme_code,
            'display_name', t.display_name,
            'description', t.description
          ) order by t.display_name), '[]'::jsonb)
          from qb3.themes t where t.active)
  from qb3.candidates c
  join qb3.questions q using (candidate_id)
  join qb3.batches b on b.batch_id = c.batch_id
  join qb3.campaigns campaign on campaign.campaign_id = c.campaign_id
  where c.batch_id = p_batch_id
    and c.metadata_result is null
    and campaign.status = 'running'
    and not campaign.cancel_requested;
$$;

commit;
