\set ON_ERROR_STOP on

begin;

-- Admission is an immutable decision. This table records recoverable work,
-- never a second copy of the candidate's quality or metadata evidence.
create table if not exists qb3.candidate_stage_work (
  candidate_id uuid not null references qb3.candidates(candidate_id) on delete restrict,
  stage text not null check (stage in ('quality', 'quality_escalation', 'embedding', 'semantic', 'metadata')),
  status text not null check (
    status in ('pending', 'running', 'retry_wait', 'needs_attention', 'complete')
  ),
  attempt_count integer not null default 0 check (attempt_count >= 0),
  current_group_id text,
  lease_expires_at timestamptz,
  next_retry_at timestamptz,
  last_error_code text,
  updated_at timestamptz not null default now(),
  primary key (candidate_id, stage),
  check ((status = 'running') = (current_group_id is not null and lease_expires_at is not null))
);

create index if not exists candidate_stage_work_due_idx
  on qb3.candidate_stage_work (stage, status, next_retry_at, lease_expires_at);

create table if not exists qb3.campaign_worker_leases (
  campaign_id text primary key references qb3.campaigns(campaign_id) on delete restrict,
  execution_id text not null,
  lease_expires_at timestamptz not null,
  updated_at timestamptz not null default now()
);

create or replace function qb3.claim_campaign_worker(
  p_campaign_id text, p_execution_id text
)
returns boolean
language plpgsql
as $$
declare
  v_claimed text;
begin
  if nullif(p_execution_id, '') is null then
    raise exception 'campaign worker execution id is required';
  end if;
  if not exists (select 1 from qb3.campaigns
                 where campaign_id = p_campaign_id) then
    raise exception 'campaign % not found', p_campaign_id;
  end if;

  insert into qb3.campaign_worker_leases (
    campaign_id, execution_id, lease_expires_at
  ) values (p_campaign_id, p_execution_id, now() + interval '2 hours')
  on conflict (campaign_id) do update
  set execution_id = excluded.execution_id,
      lease_expires_at = excluded.lease_expires_at,
      updated_at = now()
  where qb3.campaign_worker_leases.execution_id = excluded.execution_id
     or qb3.campaign_worker_leases.lease_expires_at <= now()
  returning execution_id into v_claimed;

  return coalesce(v_claimed = p_execution_id, false);
end;
$$;

create or replace function qb3.release_campaign_worker(
  p_campaign_id text, p_execution_id text
)
returns boolean
language plpgsql
as $$
declare
  v_deleted integer;
begin
  delete from qb3.campaign_worker_leases
  where campaign_id = p_campaign_id and execution_id = p_execution_id;
  get diagnostics v_deleted = row_count;
  return v_deleted = 1;
end;
$$;

create or replace function qb3.renew_campaign_worker(
  p_campaign_id text, p_execution_id text
)
returns boolean
language plpgsql
as $$
declare
  v_updated integer;
begin
  update qb3.campaign_worker_leases
  set lease_expires_at = now() + interval '2 hours', updated_at = now()
  where campaign_id = p_campaign_id
    and execution_id = p_execution_id
    and lease_expires_at > now();
  get diagnostics v_updated = row_count;
  if v_updated <> 1 then
    raise exception 'campaign % worker lease was lost', p_campaign_id;
  end if;
  return true;
end;
$$;

-- A grouped paid attempt has an exact, durable membership. This is also the
-- source for per-question retry counts when the provider call covers a group.
create table if not exists qb3.provider_attempt_candidates (
  attempt_id text not null references qb3.provider_attempts(attempt_id) on delete restrict,
  candidate_id uuid not null references qb3.candidates(candidate_id) on delete restrict,
  stage text not null check (stage in ('quality', 'quality_escalation', 'embedding', 'semantic', 'metadata')),
  primary key (attempt_id, candidate_id, stage)
);

create index if not exists provider_attempt_candidates_candidate_idx
  on qb3.provider_attempt_candidates (candidate_id, stage, attempt_id);

alter table qb3.provider_attempts
  add column if not exists work_group_id text,
  add column if not exists sent_at timestamptz;

-- Every historical reservation may already have reached its provider. A null
-- sent_at is safe to interpret as pre-send only for attempts created after
-- this migration and the matching workflow change.
update qb3.provider_attempts
set sent_at = started_at
where sent_at is null;

-- Existing candidate evidence determines the initial checkpoint. A terminal
-- admission outcome does not mean metadata is complete.
insert into qb3.candidate_stage_work (candidate_id, stage, status)
select c.candidate_id, 'quality',
  case when (c.quality_result is not null
              and c.quality_result ->> 'verdict' is not null)
              or c.state in ('quality_rejected', 'accepted',
                             'semantic_duplicate', 'exact_duplicate',
                             'awaiting_human_review')
       then 'complete'
       when c.state = 'operationally_unresolved'
         and (c.rejection_reason_codes ? 'provider_failure_quality'
           or c.rejection_reason_codes ? 'provider_failure_quality_escalation')
       then 'needs_attention'
       else 'pending' end
from qb3.candidates c
on conflict (candidate_id, stage) do nothing;

insert into qb3.candidate_stage_work (candidate_id, stage, status)
select c.candidate_id, 'quality_escalation',
  case when c.quality_result ->> 'escalated' = 'true'
         or c.state = 'awaiting_human_review' then 'complete'
       when c.state = 'operationally_unresolved'
         and c.rejection_reason_codes ? 'provider_failure_quality_escalation'
       then 'needs_attention'
       else 'pending' end
from qb3.candidates c
where c.quality_result ->> 'verdict' = 'uncertain'
on conflict (candidate_id, stage) do nothing;

insert into qb3.candidate_stage_work (candidate_id, stage, status)
select c.candidate_id, 'embedding',
  case when c.embedding is not null or c.state = 'exact_duplicate'
       then 'complete'
       when c.state = 'operationally_unresolved'
         and c.rejection_reason_codes ? 'provider_failure_embedding'
       then 'needs_attention'
       else 'pending' end
from qb3.candidates c
where c.state not in ('quality_rejected', 'awaiting_human_review')
on conflict (candidate_id, stage) do nothing;

insert into qb3.candidate_stage_work (candidate_id, stage, status)
select c.candidate_id, 'semantic',
  case when c.semantic_result is not null
            or c.state in ('accepted', 'semantic_duplicate', 'exact_duplicate')
       then 'complete'
       when c.state = 'operationally_unresolved'
         and c.rejection_reason_codes ? 'provider_failure_semantic'
       then 'needs_attention'
       else 'pending' end
from qb3.candidates c
where c.state not in ('quality_rejected', 'awaiting_human_review')
on conflict (candidate_id, stage) do nothing;

update qb3.candidate_stage_work w
set last_error_code = 'legacy_untracked_attempts', updated_at = now()
where w.status = 'needs_attention' and w.last_error_code is null;

insert into qb3.candidate_stage_work (candidate_id, stage, status)
select c.candidate_id, 'metadata',
  case when c.metadata_result is not null and q.metadata_updated_at is not null
       then 'complete' else 'pending' end
from qb3.candidates c
join qb3.questions q using (candidate_id)
where c.state = 'accepted'
on conflict (candidate_id, stage) do nothing;

-- Before grouped membership was recorded, metadata requests were exactly the
-- accepted questions in their batch. Preserve this ancestry for old attempts.
insert into qb3.provider_attempt_candidates (attempt_id, candidate_id, stage)
select a.attempt_id, c.candidate_id, 'metadata'
from qb3.provider_attempts a
join qb3.candidates c on c.batch_id = a.batch_id
where a.agent_role = 'theme_metadata' and c.state = 'accepted'
on conflict do nothing;

update qb3.candidate_stage_work w
set attempt_count = greatest(w.attempt_count, counts.attempt_count),
    updated_at = now()
from (
  select candidate_id, stage, count(*)::integer as attempt_count
  from qb3.provider_attempt_candidates
  group by candidate_id, stage
) counts
where w.candidate_id = counts.candidate_id and w.stage = counts.stage;

create or replace function qb3.sync_candidate_stage_work()
returns trigger
language plpgsql
as $$
declare
  v_stage text;
begin
  insert into qb3.candidate_stage_work (candidate_id, stage, status)
  values (new.candidate_id, 'quality', 'pending'),
         (new.candidate_id, 'embedding', 'pending'),
         (new.candidate_id, 'semantic', 'pending')
  on conflict do nothing;

  if new.quality_result is not null then
    update qb3.candidate_stage_work
    set status = 'complete', current_group_id = null,
        lease_expires_at = null, next_retry_at = null, updated_at = now()
    where candidate_id = new.candidate_id and stage = 'quality';

    if new.quality_result ->> 'verdict' = 'uncertain'
       and new.quality_result ->> 'escalated' = 'false' then
      insert into qb3.candidate_stage_work (candidate_id, stage, status)
      values (new.candidate_id, 'quality_escalation', 'pending')
      on conflict do nothing;
    elsif new.quality_result ->> 'escalated' = 'true' then
      update qb3.candidate_stage_work
      set status = 'complete', current_group_id = null,
          lease_expires_at = null, next_retry_at = null, updated_at = now()
      where candidate_id = new.candidate_id and stage = 'quality_escalation';
    end if;
  end if;

  if new.embedding is not null or new.state = 'exact_duplicate' then
    update qb3.candidate_stage_work
    set status = 'complete', current_group_id = null,
        lease_expires_at = null, next_retry_at = null, updated_at = now()
    where candidate_id = new.candidate_id and stage = 'embedding';
  end if;

  if new.semantic_result is not null or new.state in
      ('accepted', 'semantic_duplicate', 'exact_duplicate') then
    update qb3.candidate_stage_work
    set status = 'complete', current_group_id = null,
        lease_expires_at = null, next_retry_at = null, updated_at = now()
    where candidate_id = new.candidate_id and stage = 'semantic';
  end if;

  if new.state = 'accepted' then
    insert into qb3.candidate_stage_work (candidate_id, stage, status)
    values (new.candidate_id, 'metadata',
      case when new.metadata_result is null then 'pending' else 'complete' end)
    on conflict do nothing;
  end if;

  -- Old published workflow versions can still run during a rolling deploy.
  -- Their technical failures have no exact attempt membership, so they must
  -- not be retried automatically as if they had zero prior attempts.
  if new.state = 'operationally_unresolved' then
    foreach v_stage in array array['quality', 'quality_escalation',
                                  'embedding', 'semantic'] loop
      if new.rejection_reason_codes ? ('provider_failure_' || v_stage) then
        update qb3.candidate_stage_work w
        set status = 'needs_attention', next_retry_at = null,
            last_error_code = 'legacy_untracked_attempts', updated_at = now()
        where w.candidate_id = new.candidate_id and w.stage = v_stage
          and w.status = 'pending' and w.current_group_id is null
          and not exists (
            select 1 from qb3.provider_attempt_candidates m
            where m.candidate_id = w.candidate_id and m.stage = v_stage
          );
      end if;
    end loop;
  end if;

  return new;
end;
$$;

drop trigger if exists sync_candidate_stage_work on qb3.candidates;
create trigger sync_candidate_stage_work
after insert or update of state, quality_result, semantic_result, embedding
on qb3.candidates
for each row execute function qb3.sync_candidate_stage_work();

create or replace view qb3.ready_questions as
select q.*
from qb3.questions q
join qb3.candidates c using (candidate_id)
where c.state = 'accepted'
  and c.metadata_result is not null
  and q.metadata_updated_at is not null;

alter table qb3.campaigns drop constraint if exists campaigns_status_check;
alter table qb3.campaigns add constraint campaigns_status_check check (
  status in (
    'running', 'waiting_recovery', 'completed', 'cancelled_partial',
    'budget_exhausted_partial', 'unknown_spend', 'configuration_error',
    'database_error', 'safety_ceiling_reached', 'provider_outage'
  )
);

create or replace view qb3.campaign_question_progress as
select campaign.campaign_id,
  count(*) filter (where c.state = 'accepted' and c.level = 'shallow')::integer
    as accepted_shallow,
  count(*) filter (where c.state = 'accepted' and c.level = 'deep')::integer
    as accepted_deep,
  count(*) filter (where ready.question_id is not null and c.level = 'shallow')::integer
    as ready_shallow,
  count(*) filter (where ready.question_id is not null and c.level = 'deep')::integer
    as ready_deep,
  count(*) filter (where c.state = 'accepted' and ready.question_id is null
    and w.status in ('pending', 'running', 'retry_wait')
    and c.level = 'shallow')::integer as recoverable_shallow,
  count(*) filter (where c.state = 'accepted' and ready.question_id is null
    and w.status in ('pending', 'running', 'retry_wait')
    and c.level = 'deep')::integer as recoverable_deep,
  count(*) filter (where c.state = 'accepted' and ready.question_id is null)::integer
    as accepted_unready,
  count(*) filter (where w.stage = 'metadata' and w.status = 'retry_wait')::integer
    as metadata_retry_wait,
  count(*) filter (where w.stage = 'metadata' and w.status = 'needs_attention')::integer
    as metadata_needs_attention,
  count(*) filter (where c.level = 'shallow'
    and c.state in ('proposed', 'operationally_unresolved')
    and exists (select 1 from qb3.candidate_stage_work stage_work
      where stage_work.candidate_id = c.candidate_id
        and stage_work.stage in ('quality', 'quality_escalation', 'embedding', 'semantic')
        and stage_work.status in ('pending', 'running', 'retry_wait')
        and (c.state = 'proposed' or c.rejection_reason_codes
             ? ('provider_failure_' || stage_work.stage))))::integer
    as recoverable_candidate_shallow,
  count(*) filter (where c.level = 'deep'
    and c.state in ('proposed', 'operationally_unresolved')
    and exists (select 1 from qb3.candidate_stage_work stage_work
      where stage_work.candidate_id = c.candidate_id
        and stage_work.stage in ('quality', 'quality_escalation', 'embedding', 'semantic')
        and stage_work.status in ('pending', 'running', 'retry_wait')
        and (c.state = 'proposed' or c.rejection_reason_codes
             ? ('provider_failure_' || stage_work.stage))))::integer
    as recoverable_candidate_deep
from qb3.campaigns campaign
left join qb3.candidates c on c.campaign_id = campaign.campaign_id
left join qb3.questions q on q.candidate_id = c.candidate_id
left join qb3.ready_questions ready on ready.question_id = q.question_id
left join qb3.candidate_stage_work w
  on w.candidate_id = c.candidate_id and w.stage = 'metadata'
group by campaign.campaign_id;

create or replace view qb3.campaign_status as
select
  c.campaign_id, c.campaign_name, c.level_mode, c.status,
  c.accepted_target, c.accepted_shallow, c.accepted_deep,
  c.accepted_shallow + c.accepted_deep as accepted_total,
  c.authorized_budget_usd, c.spent_usd, c.reserved_usd,
  c.unknown_spend_usd,
  c.authorized_budget_usd - c.spent_usd - c.reserved_usd
    - c.unknown_spend_usd as remaining_usd,
  c.cancel_requested, c.next_batch_index, c.emergency_batch_ceiling,
  c.started_at, c.updated_at, c.completed_at,
  p.ready_shallow, p.ready_deep,
  p.ready_shallow + p.ready_deep as ready_total,
  p.accepted_unready, p.recoverable_shallow, p.recoverable_deep,
  p.metadata_retry_wait, p.metadata_needs_attention,
  coalesce((select jsonb_agg(jsonb_build_object(
      'candidate_id', w.candidate_id, 'stage', w.stage,
      'status', w.status, 'attempt_count', w.attempt_count,
      'reason', w.last_error_code, 'next_retry_at', w.next_retry_at
    ) order by w.updated_at, w.candidate_id)
    from qb3.candidate_stage_work w
    join qb3.candidates candidate using (candidate_id)
    where candidate.campaign_id = c.campaign_id
      and w.status in ('retry_wait', 'needs_attention')), '[]'::jsonb)
    as blocked_work,
  coalesce((select jsonb_agg(jsonb_build_object(
      'attempt_id', a.attempt_id, 'agent_role', a.agent_role,
      'reservation_usd', a.reservation_usd
    ) order by a.started_at)
    from qb3.provider_attempts a
    where a.campaign_id = c.campaign_id
      and a.status = 'unknown_spend'), '[]'::jsonb)
    as unknown_attempts,
  p.recoverable_candidate_shallow, p.recoverable_candidate_deep
from qb3.campaigns c
join qb3.campaign_question_progress p using (campaign_id);

create or replace function qb3.resume_campaign(
  p_campaign_id text,
  p_additional_budget_usd numeric default 0
)
returns setof qb3.campaigns
language plpgsql
as $$
declare
  v_campaign qb3.campaigns%rowtype;
  v_progress qb3.campaign_question_progress%rowtype;
begin
  if coalesce(p_additional_budget_usd, 0) < 0 then
    raise exception 'additional spending authorization cannot be negative';
  end if;

  -- Expired reservations are settled before checking whether another worker
  -- still owns a live paid call. Unknown Spend remains inside the budget cap.
  perform * from qb3.recover_expired_provider_attempts(p_campaign_id);

  select * into v_campaign from qb3.campaigns
  where campaign_id = p_campaign_id for update;
  if not found then
    raise exception 'campaign % not found', p_campaign_id;
  end if;
  select * into v_progress from qb3.campaign_question_progress
  where campaign_id = p_campaign_id;

  if v_campaign.status = 'safety_ceiling_reached' then
    raise exception 'campaign % needs a reviewed ceiling change', p_campaign_id;
  end if;
  if v_campaign.status = 'completed'
     and v_progress.ready_shallow >= v_campaign.shallow_target
     and v_progress.ready_deep >= v_campaign.deep_target then
    raise exception 'campaign % already reached its ready target', p_campaign_id;
  end if;
  if v_campaign.reserved_usd <> 0 then
    raise exception 'campaign % still has in-flight provider attempts', p_campaign_id;
  end if;
  if v_campaign.authorized_budget_usd + coalesce(p_additional_budget_usd, 0)
     <= v_campaign.spent_usd + v_campaign.reserved_usd
        + v_campaign.unknown_spend_usd
     and (v_progress.ready_shallow < v_campaign.shallow_target
          or v_progress.ready_deep < v_campaign.deep_target) then
    raise exception 'campaign % has no remaining authorized budget', p_campaign_id;
  end if;

  update qb3.campaigns
  set authorized_budget_usd = authorized_budget_usd
        + coalesce(p_additional_budget_usd, 0),
      status = 'running', cancel_requested = false,
      completed_at = null, updated_at = now()
  where campaign_id = p_campaign_id;

  return query select c.* from qb3.campaigns c
  where c.campaign_id = p_campaign_id;
end;
$$;

create or replace function qb3.resume_recoverable_campaign(p_campaign_id text)
returns boolean
language plpgsql
as $$
declare
  v_campaign qb3.campaigns%rowtype;
begin
  select * into v_campaign from qb3.campaigns
  where campaign_id = p_campaign_id for update;
  if not found or v_campaign.cancel_requested then
    return false;
  end if;
  if v_campaign.status = 'waiting_recovery' then
    if v_campaign.reserved_usd <> 0
       or v_campaign.authorized_budget_usd <=
          v_campaign.spent_usd + v_campaign.unknown_spend_usd then
      return false;
    end if;
    perform * from qb3.resume_campaign(p_campaign_id, 0);
    return true;
  end if;
  return v_campaign.status = 'running';
end;
$$;

create or replace function qb3.accept_candidate(p_candidate_id uuid)
returns table (accepted boolean, question_id uuid, reason text)
language plpgsql
as $$
declare
  v_candidate qb3.candidates%rowtype;
  v_campaign qb3.campaigns%rowtype;
  v_progress qb3.campaign_question_progress%rowtype;
  v_question_id uuid;
begin
  select * into v_candidate from qb3.candidates
  where candidate_id = p_candidate_id for update;
  if not found then
    raise exception 'candidate % not found', p_candidate_id;
  end if;

  select q.question_id into v_question_id from qb3.questions q
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

  select * into v_campaign from qb3.campaigns
  where campaign_id = v_candidate.campaign_id for update;
  if v_campaign.status <> 'running' or v_campaign.cancel_requested then
    return query select false, null::uuid, 'campaign_not_accepting';
    return;
  end if;
  select * into v_progress from qb3.campaign_question_progress
  where campaign_id = v_candidate.campaign_id;

  if (v_candidate.level = 'shallow'
      and v_progress.ready_shallow + v_progress.recoverable_shallow
          >= v_campaign.shallow_target)
     or (v_candidate.level = 'deep'
      and v_progress.ready_deep + v_progress.recoverable_deep
          >= v_campaign.deep_target) then
    return query select false, null::uuid, 'level_target_held_by_ready_or_pending';
    return;
  end if;

  if exists (select 1 from qb3.questions q
             where q.normalized_text = v_candidate.normalized_text) then
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

  update qb3.candidates set state = 'accepted'
  where candidate_id = p_candidate_id;
  update qb3.campaigns
  set accepted_shallow = accepted_shallow
        + case when v_candidate.level = 'shallow' then 1 else 0 end,
      accepted_deep = accepted_deep
        + case when v_candidate.level = 'deep' then 1 else 0 end
  where campaign_id = v_candidate.campaign_id;

  return query select true, v_question_id, 'accepted';
exception when unique_violation then
  update qb3.candidates
  set state = 'exact_duplicate', feedback_note = 'Exact normalized duplicate'
  where candidate_id = p_candidate_id;
  return query select false, null::uuid, 'exact_duplicate';
end;
$$;

create or replace function qb3.begin_next_batch(p_campaign_id text)
returns setof qb3.batches
language plpgsql
as $$
declare
  v_campaign qb3.campaigns%rowtype;
  v_progress qb3.campaign_question_progress%rowtype;
  v_mix jsonb;
  v_batch_id uuid;
  v_shallow_held integer;
  v_deep_held integer;
begin
  select * into v_campaign from qb3.campaigns
  where campaign_id = p_campaign_id for update;
  if not found then
    raise exception 'campaign % not found', p_campaign_id;
  end if;
  if v_campaign.status <> 'running' or v_campaign.cancel_requested then
    return;
  end if;

  -- A worker may crash after claiming but before reserving. Reclaim only
  -- expired work with no live paid attempt attached to its group.
  update qb3.candidate_stage_work w
  set status = case when w.attempt_count < 3 then 'pending'
                    else 'needs_attention' end,
      current_group_id = null, lease_expires_at = null,
      last_error_code = 'expired_metadata_claim', updated_at = now()
  from qb3.candidates c
  where c.candidate_id = w.candidate_id
    and c.campaign_id = p_campaign_id
    and w.stage = 'metadata' and w.status = 'running'
    and w.lease_expires_at <= now()
    and not exists (
      select 1 from qb3.provider_attempts a
      where a.work_group_id = w.current_group_id
        and a.status = 'reserved'
    );

  return query
  select b.* from qb3.batches b
  where b.campaign_id = p_campaign_id and b.status = 'running'
  order by b.batch_index desc limit 1;
  if found then
    return;
  end if;

  select * into v_progress from qb3.campaign_question_progress
  where campaign_id = p_campaign_id;
  if v_progress.ready_shallow >= v_campaign.shallow_target
     and v_progress.ready_deep >= v_campaign.deep_target then
    if v_campaign.reserved_usd = 0 then
      update qb3.campaigns
      set status = 'completed', completed_at = now(), updated_at = now()
      where campaign_id = p_campaign_id;
    end if;
    return;
  end if;

  v_shallow_held := v_progress.ready_shallow + v_progress.recoverable_shallow
    + v_progress.recoverable_candidate_shallow;
  v_deep_held := v_progress.ready_deep + v_progress.recoverable_deep
    + v_progress.recoverable_candidate_deep;
  if v_shallow_held >= v_campaign.shallow_target
     and v_deep_held >= v_campaign.deep_target then
    update qb3.campaigns
    set status = 'waiting_recovery', updated_at = now()
    where campaign_id = p_campaign_id;
    return;
  end if;

  if v_campaign.next_batch_index > v_campaign.emergency_batch_ceiling then
    update qb3.campaigns
    set status = 'safety_ceiling_reached', completed_at = now(), updated_at = now()
    where campaign_id = p_campaign_id;
    return;
  end if;

  if v_shallow_held >= v_campaign.shallow_target then
    v_mix := '{"shallow":0,"deep":20}'::jsonb;
  elsif v_deep_held >= v_campaign.deep_target then
    v_mix := '{"shallow":20,"deep":0}'::jsonb;
  elsif v_campaign.level_mode = 'mixed' then
    v_mix := '{"shallow":10,"deep":10}'::jsonb;
  elsif v_campaign.level_mode = 'shallow' then
    v_mix := '{"shallow":20,"deep":0}'::jsonb;
  else
    v_mix := '{"shallow":0,"deep":20}'::jsonb;
  end if;

  insert into qb3.batches (campaign_id, batch_index, requested_level_mix)
  values (p_campaign_id, v_campaign.next_batch_index, v_mix)
  returning batch_id into v_batch_id;
  update qb3.campaigns
  set next_batch_index = next_batch_index + 1, updated_at = now()
  where campaign_id = p_campaign_id;
  return query select b.* from qb3.batches b where b.batch_id = v_batch_id;
end;
$$;

create or replace function qb3.complete_batch(p_batch_id uuid)
returns table (campaign_status text, distribution_snapshot_id uuid)
language plpgsql
as $$
declare
  v_campaign_id text;
  v_snapshot_id uuid;
  v_progress qb3.campaign_question_progress%rowtype;
begin
  update qb3.batches b
  set status = 'completed', completed_at = coalesce(completed_at, now())
  where b.batch_id = p_batch_id
  returning b.campaign_id into v_campaign_id;
  if not found then
    raise exception 'batch % not found', p_batch_id;
  end if;

  select * into v_progress from qb3.campaign_question_progress
  where campaign_id = v_campaign_id;
  update qb3.campaigns c
  set status = case
        when c.status in ('configuration_error', 'database_error',
                          'provider_outage', 'safety_ceiling_reached')
          then c.status
        when v_progress.ready_shallow >= c.shallow_target
          and v_progress.ready_deep >= c.deep_target
          and c.reserved_usd = 0 then 'completed'
        when c.cancel_requested then 'cancelled_partial'
        when c.spent_usd + c.reserved_usd + c.unknown_spend_usd
          >= c.authorized_budget_usd then 'budget_exhausted_partial'
        when v_progress.ready_shallow + v_progress.recoverable_shallow
               + v_progress.recoverable_candidate_shallow
               >= c.shallow_target
          and v_progress.ready_deep + v_progress.recoverable_deep
               + v_progress.recoverable_candidate_deep
               >= c.deep_target then 'waiting_recovery'
        else 'running'
      end,
      completed_at = case
        when (v_progress.ready_shallow >= c.shallow_target
              and v_progress.ready_deep >= c.deep_target
              and c.reserved_usd = 0)
          or c.cancel_requested
          or c.spent_usd + c.reserved_usd + c.unknown_spend_usd
             >= c.authorized_budget_usd
        then now() else c.completed_at end,
      updated_at = now()
  where c.campaign_id = v_campaign_id;

  -- Proposed questions remain available if held metadata later fails. Only
  -- genuinely stopped campaigns finalize those unprocessed candidates.
  update qb3.candidates candidate
  set state = 'operationally_unresolved',
      rejection_reason_codes = jsonb_build_array(
        'campaign_' || replace(campaign.status, '_partial', '')
      ),
      feedback_note = 'Campaign stopped before this candidate was processed.',
      updated_at = now()
  from qb3.campaigns campaign
  where candidate.campaign_id = v_campaign_id
    and campaign.campaign_id = candidate.campaign_id
    and campaign.status in (
      'completed', 'cancelled_partial', 'budget_exhausted_partial',
      'configuration_error', 'database_error', 'safety_ceiling_reached'
    )
    and candidate.state = 'proposed';

  v_snapshot_id := qb3.refresh_distribution_snapshot(v_campaign_id, p_batch_id);
  return query
  select c.status, v_snapshot_id from qb3.campaigns c
  where c.campaign_id = v_campaign_id;
end;
$$;

create or replace function qb3.refresh_campaign_recovery_status(p_campaign_id text)
returns text
language plpgsql
as $$
declare
  v_campaign qb3.campaigns%rowtype;
  v_progress qb3.campaign_question_progress%rowtype;
begin
  select * into v_campaign from qb3.campaigns
  where campaign_id = p_campaign_id for update;
  if not found then
    raise exception 'campaign % not found', p_campaign_id;
  end if;
  if v_campaign.status <> 'running' or v_campaign.cancel_requested then
    return v_campaign.status;
  end if;
  if exists (select 1 from qb3.batches
             where campaign_id = p_campaign_id and status = 'running') then
    return v_campaign.status;
  end if;

  select * into v_progress from qb3.campaign_question_progress
  where campaign_id = p_campaign_id;
  if v_progress.ready_shallow >= v_campaign.shallow_target
     and v_progress.ready_deep >= v_campaign.deep_target
     and v_campaign.reserved_usd = 0 then
    update qb3.campaigns
    set status = 'completed', completed_at = now(), updated_at = now()
    where campaign_id = p_campaign_id;
  elsif v_progress.ready_shallow + v_progress.recoverable_shallow
            + v_progress.recoverable_candidate_shallow
            >= v_campaign.shallow_target
     and v_progress.ready_deep + v_progress.recoverable_deep
            + v_progress.recoverable_candidate_deep
            >= v_campaign.deep_target then
    update qb3.campaigns
    set status = 'waiting_recovery', updated_at = now()
    where campaign_id = p_campaign_id;
  end if;

  return (select status from qb3.campaigns
          where campaign_id = p_campaign_id);
end;
$$;

create or replace function qb3.claim_metadata_group(
  p_campaign_id text,
  p_batch_id uuid default null,
  p_limit integer default 20
)
returns table (work_group_id text, batch_id uuid, questions jsonb, themes jsonb)
language plpgsql
as $$
declare
  v_campaign qb3.campaigns%rowtype;
  v_batch_id uuid;
  v_candidate_ids uuid[];
  v_group_id text := gen_random_uuid()::text;
begin
  if p_limit < 1 or p_limit > 20 then
    raise exception 'metadata group size must be between 1 and 20';
  end if;

  select * into v_campaign from qb3.campaigns
  where campaign_id = p_campaign_id for update;
  if not found then
    raise exception 'campaign % not found', p_campaign_id;
  end if;
  if v_campaign.status <> 'running' or v_campaign.cancel_requested then
    return;
  end if;

  update qb3.candidate_stage_work w
  set status = case when w.attempt_count < 3 then 'pending'
                    else 'needs_attention' end,
      current_group_id = null, lease_expires_at = null,
      last_error_code = 'expired_metadata_claim', updated_at = now()
  from qb3.candidates c
  where c.candidate_id = w.candidate_id
    and c.campaign_id = p_campaign_id
    and w.stage = 'metadata' and w.status = 'running'
    and w.lease_expires_at <= now()
    and not exists (
      select 1 from qb3.provider_attempts a
      where a.work_group_id = w.current_group_id
        and a.status = 'reserved'
    );

  select c.batch_id into v_batch_id
  from qb3.candidates c
  join qb3.candidate_stage_work w
    on w.candidate_id = c.candidate_id and w.stage = 'metadata'
  join qb3.batches b on b.batch_id = c.batch_id
  where c.campaign_id = p_campaign_id
    and (p_batch_id is null or c.batch_id = p_batch_id)
    and c.state = 'accepted' and c.metadata_result is null
    and w.status in ('pending', 'retry_wait')
    and (w.next_retry_at is null or w.next_retry_at <= now())
    and w.attempt_count < 3
  order by b.batch_index, c.candidate_index
  limit 1;

  if v_batch_id is null then
    return;
  end if;

  select array_agg(candidate_id) into v_candidate_ids
  from (
    select w.candidate_id
    from qb3.candidate_stage_work w
    join qb3.candidates c using (candidate_id)
    where c.campaign_id = p_campaign_id and c.batch_id = v_batch_id
      and c.state = 'accepted' and c.metadata_result is null
      and w.stage = 'metadata'
      and w.status in ('pending', 'retry_wait')
      and (w.next_retry_at is null or w.next_retry_at <= now())
      and w.attempt_count < 3
    order by c.candidate_index
    limit p_limit
    for update of w skip locked
  ) due;

  if v_candidate_ids is null then
    return;
  end if;

  update qb3.candidate_stage_work w
  set status = 'running', current_group_id = v_group_id,
      lease_expires_at = now() + interval '30 minutes',
      next_retry_at = null, last_error_code = null, updated_at = now()
  where w.candidate_id = any(v_candidate_ids) and w.stage = 'metadata';

  return query
  select v_group_id, v_batch_id,
    (select jsonb_agg(jsonb_build_object(
       'candidate_id', c.candidate_id, 'question', c.question_text,
       'level', c.level) order by c.candidate_index)
     from qb3.candidates c where c.candidate_id = any(v_candidate_ids)),
    (select coalesce(jsonb_agg(jsonb_build_object(
       'theme_code', t.theme_code, 'display_name', t.display_name,
       'description', t.description) order by t.display_name), '[]'::jsonb)
     from qb3.themes t where t.active);
end;
$$;

create or replace function qb3.attach_metadata_attempt(
  p_attempt_id text,
  p_work_group_id text
)
returns integer
language plpgsql
as $$
declare
  v_attempt qb3.provider_attempts%rowtype;
  v_expected integer;
  v_new integer;
begin
  select * into v_attempt from qb3.provider_attempts
  where attempt_id = p_attempt_id for update;
  if not found or v_attempt.status <> 'reserved'
     or v_attempt.agent_role <> 'theme_metadata' then
    raise exception 'metadata attempt % is not reserved', p_attempt_id;
  end if;
  if v_attempt.work_group_id is not null
     and v_attempt.work_group_id <> p_work_group_id then
    raise exception 'attempt % already belongs to another work group', p_attempt_id;
  end if;

  select count(*) into v_expected
  from qb3.candidate_stage_work w
  join qb3.candidates c using (candidate_id)
  where w.stage = 'metadata' and w.status = 'running'
    and w.current_group_id = p_work_group_id
    and w.lease_expires_at > now()
    and c.campaign_id = v_attempt.campaign_id
    and c.batch_id = v_attempt.batch_id
    and c.state = 'accepted' and c.metadata_result is null
    and w.attempt_count < 3;

  if v_expected = 0 then
    raise exception 'metadata work group % has no claimable questions', p_work_group_id;
  end if;

  update qb3.provider_attempts
  set work_group_id = p_work_group_id
  where attempt_id = p_attempt_id;

  with members as (
    insert into qb3.provider_attempt_candidates (attempt_id, candidate_id, stage)
    select p_attempt_id, w.candidate_id, 'metadata'
    from qb3.candidate_stage_work w
    join qb3.candidates c using (candidate_id)
    where w.stage = 'metadata' and w.status = 'running'
      and w.current_group_id = p_work_group_id
      and w.lease_expires_at > now()
      and c.campaign_id = v_attempt.campaign_id
      and c.batch_id = v_attempt.batch_id
      and c.state = 'accepted' and c.metadata_result is null
      and w.attempt_count < 3
    on conflict do nothing
    returning candidate_id
  )
  update qb3.candidate_stage_work w
  set attempt_count = w.attempt_count + 1, updated_at = now()
  where w.stage = 'metadata'
    and w.candidate_id in (select candidate_id from members);

  get diagnostics v_new = row_count;
  if v_new = 0 and not exists (
    select 1 from qb3.provider_attempt_candidates
    where attempt_id = p_attempt_id and stage = 'metadata'
  ) then
    raise exception 'metadata attempt % has no members', p_attempt_id;
  end if;

  return (select count(*)::integer from qb3.provider_attempt_candidates
          where attempt_id = p_attempt_id and stage = 'metadata');
end;
$$;

create or replace function qb3.reserve_metadata_attempt(
  p_attempt_id text,
  p_campaign_id text,
  p_batch_id uuid,
  p_parent_attempt_id text,
  p_requested_model text,
  p_reasoning_setting text,
  p_reservation_usd numeric,
  p_work_group_id text
)
returns table (
  reserved boolean, reason text, remaining_usd numeric, cached_result jsonb
)
language plpgsql
as $$
declare
  v_result record;
begin
  perform * from qb3.recover_expired_provider_attempts(p_campaign_id);
  select * into v_result from qb3.reserve_provider_budget(
    p_attempt_id, p_campaign_id, p_batch_id, null::uuid,
    p_parent_attempt_id, 'theme_metadata', 'openai',
    p_requested_model, p_reasoning_setting, p_reservation_usd
  );

  if v_result.reserved then
    -- One transaction contains both the budget reservation and exact question
    -- membership. Failure here rolls back the reservation before any send.
    perform qb3.attach_metadata_attempt(p_attempt_id, p_work_group_id);
  elsif v_result.reason in ('insufficient_budget', 'campaign_not_running') then
    update qb3.candidate_stage_work
    set status = 'pending', current_group_id = null,
        lease_expires_at = null, next_retry_at = null,
        last_error_code = v_result.reason, updated_at = now()
    where stage = 'metadata' and status = 'running'
      and current_group_id = p_work_group_id;
  end if;

  return query select v_result.reserved, v_result.reason,
    v_result.remaining_usd, v_result.cached_result;
end;
$$;

-- The other paid decision stages use the same claim and exact membership
-- contract as metadata. A group is deliberately small (at most ten) so its
-- members can be checked and retried independently of the rest of a batch.
create or replace function qb3.stage_due_count(
  p_batch_id uuid, p_stage text, p_escalation boolean default false
)
returns integer
language sql
stable
as $$
  select count(*)::integer
  from qb3.candidates c
  join qb3.candidate_stage_work w
    on w.candidate_id = c.candidate_id
   and w.stage = case when p_stage = 'quality' and p_escalation
     then 'quality_escalation' else p_stage end
  join qb3.campaigns campaign using (campaign_id)
  where c.batch_id = p_batch_id
    and p_stage in ('quality', 'embedding', 'semantic')
    and campaign.status in ('running', 'waiting_recovery')
    and not campaign.cancel_requested
    and w.status in ('pending', 'retry_wait')
    and (w.next_retry_at is null or w.next_retry_at <= now())
    and w.attempt_count < 3
    and (
      c.state = 'proposed'
      or (c.state = 'operationally_unresolved'
          and c.rejection_reason_codes ? ('provider_failure_' || w.stage))
    )
    and case p_stage
      when 'quality' then
        (not p_escalation and c.quality_result is null)
        or (p_escalation and c.quality_result ->> 'verdict' = 'uncertain'
            and c.quality_result ->> 'escalated' = 'false')
      when 'embedding' then c.quality_result ->> 'verdict' = 'pass'
        and c.embedding is null
      when 'semantic' then c.quality_result ->> 'verdict' = 'pass'
        and c.embedding is not null and c.semantic_result is null
        and ((c.level = 'shallow'
              and campaign.accepted_shallow < campaign.shallow_target)
          or (c.level = 'deep'
              and campaign.accepted_deep < campaign.deep_target))
      else false
    end;
$$;

create or replace function qb3.claim_candidate_stage_group(
  p_batch_id uuid, p_stage text, p_limit integer,
  p_escalation boolean default false
)
returns table (work_group_id text, candidates jsonb)
language plpgsql
as $$
declare
  v_campaign qb3.campaigns%rowtype;
  v_ids uuid[];
  v_group_id text := gen_random_uuid()::text;
  v_work_stage text := case when p_stage = 'quality' and p_escalation
    then 'quality_escalation' else p_stage end;
begin
  if p_stage not in ('quality', 'embedding', 'semantic')
     or p_limit < 1 or p_limit > 10
     or (p_escalation and p_stage <> 'quality') then
    raise exception 'unsupported stage claim';
  end if;

  select campaign.* into v_campaign
  from qb3.batches b
  join qb3.campaigns campaign using (campaign_id)
  where b.batch_id = p_batch_id
  for update of campaign;
  if not found or v_campaign.status <> 'running'
     or v_campaign.cancel_requested then
    return;
  end if;

  select array_agg(candidate_id) into v_ids from (
    select w.candidate_id
    from qb3.candidate_stage_work w
    join qb3.candidates c using (candidate_id)
    where c.batch_id = p_batch_id and w.stage = v_work_stage
      and w.status in ('pending', 'retry_wait')
      and (w.next_retry_at is null or w.next_retry_at <= now())
      and w.attempt_count < 3
      and (c.state = 'proposed'
        or (c.state = 'operationally_unresolved'
          and c.rejection_reason_codes ? ('provider_failure_' || v_work_stage)))
      and case p_stage
        when 'quality' then
          (not p_escalation and c.quality_result is null)
          or (p_escalation and c.quality_result ->> 'verdict' = 'uncertain'
              and c.quality_result ->> 'escalated' = 'false')
        when 'embedding' then c.quality_result ->> 'verdict' = 'pass'
          and c.embedding is null
        when 'semantic' then c.quality_result ->> 'verdict' = 'pass'
          and c.embedding is not null and c.semantic_result is null
          and ((c.level = 'shallow'
                and v_campaign.accepted_shallow < v_campaign.shallow_target)
            or (c.level = 'deep'
                and v_campaign.accepted_deep < v_campaign.deep_target))
        else false
      end
    order by c.candidate_index
    limit p_limit
    for update of w skip locked
  ) due;
  if v_ids is null then
    return;
  end if;

  update qb3.candidate_stage_work w
  set status = 'running', current_group_id = v_group_id,
      lease_expires_at = now() + interval '2 hours',
      next_retry_at = null, last_error_code = null, updated_at = now()
  where w.candidate_id = any(v_ids) and w.stage = v_work_stage;

  update qb3.candidates c
  set state = 'proposed', rejection_reason_codes = '[]'::jsonb,
      feedback_note = null, updated_at = now()
  where c.candidate_id = any(v_ids)
    and c.state = 'operationally_unresolved';

  return query select v_group_id,
    (select jsonb_agg(jsonb_build_object(
       'candidate_id', c.candidate_id, 'question', c.question_text,
       'level', c.level, 'previous_quality_result', c.quality_result
     ) order by c.candidate_index)
     from qb3.candidates c where c.candidate_id = any(v_ids));
end;
$$;

create or replace function qb3.claim_candidate_stage_groups(
  p_batch_id uuid, p_stage text, p_limit integer,
  p_escalation boolean default false
)
returns table (group_index integer, work_group_id text, candidates jsonb)
language plpgsql
as $$
declare
  v_due integer;
  v_group record;
begin
  v_due := qb3.stage_due_count(p_batch_id, p_stage, p_escalation);
  for group_index in 1..ceil(v_due::numeric / p_limit)::integer loop
    select * into v_group from qb3.claim_candidate_stage_group(
      p_batch_id, p_stage, p_limit, p_escalation
    );
    exit when not found;
    work_group_id := v_group.work_group_id;
    candidates := v_group.candidates;
    return next;
  end loop;
end;
$$;

create or replace function qb3.attach_candidate_stage_attempt(
  p_attempt_id text, p_work_group_id text, p_stage text
)
returns integer
language plpgsql
as $$
declare
  v_attempt qb3.provider_attempts%rowtype;
  v_count integer;
begin
  select * into v_attempt from qb3.provider_attempts
  where attempt_id = p_attempt_id for update;
  if not found or v_attempt.status <> 'reserved' then
    raise exception 'stage attempt % is not reserved', p_attempt_id;
  end if;
  if v_attempt.work_group_id is not null
     and v_attempt.work_group_id <> p_work_group_id then
    raise exception 'attempt % belongs to a different stage group', p_attempt_id;
  end if;
  if p_stage not in ('quality', 'quality_escalation', 'embedding', 'semantic')
     or (p_stage = 'quality' and v_attempt.agent_role <> 'quality_judge')
     or (p_stage = 'quality_escalation'
         and v_attempt.agent_role <> 'quality_escalation')
     or (p_stage = 'embedding' and v_attempt.agent_role <> 'embedding')
     or (p_stage = 'semantic' and v_attempt.agent_role <> 'semantic_judge') then
    raise exception 'attempt % has an incompatible stage role', p_attempt_id;
  end if;

  select count(*)::integer into v_count
  from qb3.candidate_stage_work w
  join qb3.candidates c using (candidate_id)
  where w.stage = p_stage and w.status = 'running'
    and w.current_group_id = p_work_group_id
    and w.lease_expires_at > now() and w.attempt_count < 3
    and c.campaign_id = v_attempt.campaign_id
    and c.batch_id = v_attempt.batch_id
    and (v_attempt.candidate_id is null
         or c.candidate_id = v_attempt.candidate_id);
  if v_count = 0 or (p_stage = 'embedding' and v_count <> 1) then
    raise exception 'stage group % has no claimable questions', p_work_group_id;
  end if;

  update qb3.provider_attempts
  set work_group_id = p_work_group_id
  where attempt_id = p_attempt_id;

  with members as (
    insert into qb3.provider_attempt_candidates (attempt_id, candidate_id, stage)
    select p_attempt_id, w.candidate_id, p_stage
    from qb3.candidate_stage_work w
    join qb3.candidates c using (candidate_id)
    where w.stage = p_stage and w.status = 'running'
      and w.current_group_id = p_work_group_id
      and w.lease_expires_at > now() and w.attempt_count < 3
      and c.campaign_id = v_attempt.campaign_id
      and c.batch_id = v_attempt.batch_id
      and (v_attempt.candidate_id is null
           or c.candidate_id = v_attempt.candidate_id)
    on conflict do nothing returning candidate_id
  )
  update qb3.candidate_stage_work w
  set attempt_count = w.attempt_count + 1, updated_at = now()
  where w.stage = p_stage
    and w.candidate_id in (select candidate_id from members);

  return (select count(*)::integer from qb3.provider_attempt_candidates
          where attempt_id = p_attempt_id and stage = p_stage);
end;
$$;

create or replace function qb3.reserve_provider_budget_dispatch(
  p_attempt_id text,
  p_campaign_id text,
  p_batch_id uuid,
  p_candidate_id uuid,
  p_parent_attempt_id text,
  p_agent_role text,
  p_provider text,
  p_requested_model text,
  p_reasoning_setting text,
  p_reservation_usd numeric,
  p_work_group_id text default null
)
returns table (
  reserved boolean, reason text, remaining_usd numeric, cached_result jsonb
)
language plpgsql
as $$
declare
  v_result record;
begin
  perform * from qb3.recover_expired_provider_attempts(p_campaign_id);

  if p_agent_role = 'theme_metadata' then
    if p_provider <> 'openai' or p_batch_id is null
       or p_candidate_id is not null or p_work_group_id is null then
      raise exception 'metadata reservation requires an OpenAI group and batch';
    end if;
    return query select * from qb3.reserve_metadata_attempt(
      p_attempt_id, p_campaign_id, p_batch_id, p_parent_attempt_id,
      p_requested_model, p_reasoning_setting, p_reservation_usd,
      p_work_group_id
    );
  else
    if p_agent_role in ('quality_judge', 'quality_escalation',
                        'embedding', 'semantic_judge')
       and p_work_group_id is not null and p_batch_id is null then
      raise exception 'claimed stage role % requires a batch', p_agent_role;
    elsif p_agent_role not in ('quality_judge', 'quality_escalation',
                              'embedding', 'semantic_judge')
       and p_work_group_id is not null then
      raise exception 'work group is unsupported for agent role %', p_agent_role;
    end if;

    if p_work_group_id is not null
       and p_agent_role in ('quality_judge', 'quality_escalation',
                        'embedding', 'semantic_judge')
       and not exists (
         select 1 from qb3.candidate_stage_work w
         where w.current_group_id = p_work_group_id
           and w.status = 'running' and w.attempt_count < 3
       ) then
      return query select false, 'retry_limit_reached'::text,
        c.authorized_budget_usd - c.spent_usd - c.reserved_usd
          - c.unknown_spend_usd, null::jsonb
      from qb3.campaigns c where c.campaign_id = p_campaign_id;
      return;
    end if;

    -- Reservation and exact membership are one transaction. An exhausted
    -- question cannot consume a fourth tracked provider attempt.
    select * into v_result from qb3.reserve_provider_budget(
      p_attempt_id, p_campaign_id, p_batch_id, p_candidate_id,
      p_parent_attempt_id, p_agent_role, p_provider, p_requested_model,
      p_reasoning_setting, p_reservation_usd
    );
    if v_result.reserved and p_work_group_id is not null
       and p_agent_role in ('quality_judge', 'quality_escalation',
                        'embedding', 'semantic_judge') then
      perform qb3.attach_candidate_stage_attempt(
        p_attempt_id, p_work_group_id,
        case when p_agent_role = 'quality_judge' then 'quality'
          when p_agent_role = 'quality_escalation'
            then 'quality_escalation'
          when p_agent_role = 'semantic_judge' then 'semantic'
          else 'embedding' end
      );
    end if;
    return query select v_result.reserved, v_result.reason,
      v_result.remaining_usd, v_result.cached_result;
  end if;
end;
$$;

create or replace function qb3.mark_provider_attempt_unknown(
  p_attempt_id text,
  p_sanitized_error jsonb
)
returns table (status text, reserved_usd numeric, unknown_spend_usd numeric)
language plpgsql
as $$
declare
  v_attempt qb3.provider_attempts%rowtype;
begin
  select * into v_attempt from qb3.provider_attempts
  where attempt_id = p_attempt_id for update;
  if not found then
    raise exception 'attempt % not found', p_attempt_id;
  end if;

  if v_attempt.status = 'reserved' then
    update qb3.provider_attempts
    set status = 'unknown_spend', sanitized_error = p_sanitized_error,
        completed_at = now()
    where attempt_id = p_attempt_id;
    update qb3.campaigns c
    set reserved_usd = c.reserved_usd - v_attempt.reservation_usd,
        unknown_spend_usd = c.unknown_spend_usd + v_attempt.reservation_usd,
        updated_at = now()
    where c.campaign_id = v_attempt.campaign_id;
  elsif v_attempt.status <> 'unknown_spend' then
    raise exception 'attempt % cannot become unknown from status %',
      p_attempt_id, v_attempt.status;
  end if;

  return query select c.status, c.reserved_usd, c.unknown_spend_usd
  from qb3.campaigns c where c.campaign_id = v_attempt.campaign_id;
end;
$$;

create or replace function qb3.mark_provider_attempt_sending(p_attempt_id text)
returns void
language plpgsql
as $$
declare
  v_attempt qb3.provider_attempts%rowtype;
begin
  select * into v_attempt from qb3.provider_attempts
  where attempt_id = p_attempt_id for update;
  if not found or v_attempt.status <> 'reserved' then
    raise exception 'provider attempt % is not reserved', p_attempt_id;
  end if;
  if (v_attempt.agent_role = 'theme_metadata'
      or (v_attempt.work_group_id is not null
          and v_attempt.agent_role in ('quality_judge',
                              'quality_escalation', 'embedding',
                              'semantic_judge')))
     and not exists (
    select 1 from qb3.provider_attempt_candidates
    where attempt_id = p_attempt_id
  ) then
    raise exception 'stage attempt % has no recorded members', p_attempt_id;
  end if;

  update qb3.provider_attempts
  set sent_at = coalesce(sent_at, now()),
      lease_expires_at = greatest(lease_expires_at, now() + interval '30 minutes')
  where attempt_id = p_attempt_id;

  if v_attempt.work_group_id is not null then
    update qb3.candidate_stage_work
    set lease_expires_at = greatest(lease_expires_at, now() + interval '30 minutes'),
        updated_at = now()
    where current_group_id = v_attempt.work_group_id and status = 'running';
  end if;
end;
$$;

-- A delayed authoritative provider result may arrive after lease recovery has
-- conservatively moved the reservation to Unknown Spend. Reconcile it exactly
-- once and remove the held amount rather than losing a successful response.
create or replace function qb3.reconcile_provider_attempt(
  p_attempt_id text,
  p_actual_cost_usd numeric,
  p_reported_model text,
  p_usage jsonb
)
returns table (status text, spent_usd numeric, reserved_usd numeric, unknown_spend_usd numeric)
language plpgsql
as $$
declare
  v_attempt qb3.provider_attempts%rowtype;
begin
  if p_actual_cost_usd < 0 then
    raise exception 'actual cost cannot be negative';
  end if;
  select * into v_attempt from qb3.provider_attempts
  where attempt_id = p_attempt_id for update;
  if not found then
    raise exception 'attempt % not found', p_attempt_id;
  end if;

  if v_attempt.status = 'reconciled' then
    if v_attempt.actual_cost_usd <> p_actual_cost_usd then
      raise exception 'attempt % reconciled with a different cost', p_attempt_id;
    end if;
  elsif v_attempt.status not in ('reserved', 'unknown_spend') then
    raise exception 'attempt % cannot reconcile from status %',
      p_attempt_id, v_attempt.status;
  elsif p_actual_cost_usd > v_attempt.reservation_usd then
    update qb3.provider_attempts
    set status = 'reservation_exceeded', actual_cost_usd = p_actual_cost_usd,
        reported_model = p_reported_model, usage = p_usage,
        completed_at = now()
    where attempt_id = p_attempt_id;
    update qb3.campaigns c
    set reserved_usd = c.reserved_usd
          - case when v_attempt.status = 'reserved'
                 then v_attempt.reservation_usd else 0 end,
        unknown_spend_usd = c.unknown_spend_usd
          - case when v_attempt.status = 'unknown_spend'
                 then v_attempt.reservation_usd else 0 end
          + (p_actual_cost_usd - v_attempt.reservation_usd),
        spent_usd = c.spent_usd + v_attempt.reservation_usd,
        status = 'configuration_error', updated_at = now()
    where c.campaign_id = v_attempt.campaign_id;
  else
    update qb3.provider_attempts
    set status = 'reconciled', actual_cost_usd = p_actual_cost_usd,
        reported_model = p_reported_model, usage = p_usage,
        completed_at = now()
    where attempt_id = p_attempt_id;
    update qb3.campaigns c
    set reserved_usd = c.reserved_usd
          - case when v_attempt.status = 'reserved'
                 then v_attempt.reservation_usd else 0 end,
        unknown_spend_usd = c.unknown_spend_usd
          - case when v_attempt.status = 'unknown_spend'
                 then v_attempt.reservation_usd else 0 end,
        spent_usd = c.spent_usd + p_actual_cost_usd,
        updated_at = now()
    where c.campaign_id = v_attempt.campaign_id;
  end if;

  return query select c.status, c.spent_usd,
    c.reserved_usd, c.unknown_spend_usd
  from qb3.campaigns c where c.campaign_id = v_attempt.campaign_id;
end;
$$;

create or replace function qb3.finish_metadata_attempt_failure(
  p_attempt_id text,
  p_error_code text,
  p_retryable boolean
)
returns table (retry_wait_count integer, needs_attention_count integer)
language plpgsql
as $$
declare
  v_attempt qb3.provider_attempts%rowtype;
begin
  select * into v_attempt from qb3.provider_attempts
  where attempt_id = p_attempt_id for update;
  if not found or v_attempt.agent_role <> 'theme_metadata'
     or v_attempt.status = 'reserved' then
    raise exception 'metadata attempt % has not reached a durable outcome', p_attempt_id;
  end if;

  update qb3.candidate_stage_work w
  set status = case when p_retryable and w.attempt_count < 3
                    then 'retry_wait' else 'needs_attention' end,
      next_retry_at = case when p_retryable and w.attempt_count < 3
        then now() + case when w.attempt_count <= 1
          then interval '10 seconds' else interval '30 seconds' end
        else null end,
      current_group_id = null,
      lease_expires_at = null,
      last_error_code = left(p_error_code, 100), updated_at = now()
  from qb3.provider_attempt_candidates m
  join qb3.candidates c on c.candidate_id = m.candidate_id
  where m.attempt_id = p_attempt_id and m.stage = 'metadata'
    and w.candidate_id = m.candidate_id and w.stage = 'metadata'
    and c.metadata_result is null
    and w.status <> 'complete'
    and (v_attempt.work_group_id is null
         or w.current_group_id = v_attempt.work_group_id);

  return query
  select count(*) filter (where w.status = 'retry_wait')::integer,
         count(*) filter (where w.status = 'needs_attention')::integer
  from qb3.candidate_stage_work w
  join qb3.provider_attempt_candidates m
    on m.candidate_id = w.candidate_id and m.stage = w.stage
  where m.attempt_id = p_attempt_id and w.stage = 'metadata';
end;
$$;

create or replace function qb3.finish_candidate_stage_group_failure(
  p_work_group_id text, p_stage text, p_error_code text,
  p_retryable boolean
)
returns table (retry_wait_count integer, needs_attention_count integer)
language plpgsql
as $$
declare
  v_batch_id uuid;
  v_ids uuid[];
  v_campaign_id text;
  v_503_count integer;
begin
  if p_stage not in ('quality', 'quality_escalation', 'embedding', 'semantic') then
    raise exception 'unsupported failed stage %', p_stage;
  end if;
  select c.batch_id into v_batch_id
  from qb3.candidate_stage_work w
  join qb3.candidates c using (candidate_id)
  where w.current_group_id = p_work_group_id
    and w.stage = p_stage and w.status = 'running'
  limit 1;
  if v_batch_id is null then
    return query select 0, 0;
    return;
  end if;
  select b.campaign_id into v_campaign_id
  from qb3.batches b where b.batch_id = v_batch_id;

  select array_agg(w.candidate_id) into v_ids
  from qb3.candidate_stage_work w
  where w.current_group_id = p_work_group_id
    and w.stage = p_stage and w.status = 'running';

  update qb3.candidates c
  set state = 'operationally_unresolved',
      rejection_reason_codes = jsonb_build_array('provider_failure_' || p_stage),
      feedback_note = left(p_error_code, 500), updated_at = now()
  from qb3.candidate_stage_work w
  where w.candidate_id = c.candidate_id and w.stage = p_stage
    and w.current_group_id = p_work_group_id and w.status = 'running'
    and c.batch_id = v_batch_id and c.state = 'proposed';

  update qb3.candidate_stage_work w
  set status = case
        when p_error_code in ('insufficient_budget', 'campaign_not_running')
          then 'pending'
        when p_retryable and w.attempt_count < 3 then 'retry_wait'
        else 'needs_attention' end,
      next_retry_at = case when p_retryable and w.attempt_count < 3
        then now() + case when w.attempt_count <= 1
          then interval '10 seconds' else interval '30 seconds' end
        else null end,
      current_group_id = null, lease_expires_at = null,
      last_error_code = left(p_error_code, 100), updated_at = now()
  where w.current_group_id = p_work_group_id and w.stage = p_stage
    and w.status = 'running';

  if p_error_code = 'configuration_failure'
     or p_error_code ~ '^(openai|embedding)_http_(400|401|403|404|422)$' then
    update qb3.campaigns campaign
    set status = 'configuration_error', completed_at = now(), updated_at = now()
    where campaign.campaign_id = v_campaign_id
      and campaign.status = 'running';
  elsif p_retryable then
    select count(*)::integer into v_503_count
    from qb3.provider_attempts a
    where a.campaign_id = v_campaign_id
      and a.provider = 'openai'
      and a.sanitized_error ->> 'status_code' = '503'
      and a.started_at > now() - interval '10 minutes';
    if v_503_count >= 6 then
      update qb3.campaigns
      set status = 'provider_outage', completed_at = now(), updated_at = now()
      where campaign_id = v_campaign_id and status = 'running';
    end if;
  end if;

  return query select
    count(*) filter (where w.status = 'retry_wait')::integer,
    count(*) filter (where w.status = 'needs_attention')::integer
  from qb3.candidate_stage_work w
  where w.candidate_id = any(v_ids) and w.stage = p_stage;
end;
$$;

create or replace function qb3.recover_expired_provider_attempts(p_campaign_id text)
returns table (released_before_send integer, unknown_after_send integer)
language plpgsql
as $$
declare
  v_attempt qb3.provider_attempts%rowtype;
  v_prior_status text;
  v_released integer := 0;
  v_unknown integer := 0;
begin
  select status into v_prior_status from qb3.campaigns
  where campaign_id = p_campaign_id;
  if not found then
    raise exception 'campaign % not found', p_campaign_id;
  end if;

  for v_attempt in
    select a.* from qb3.provider_attempts a
    where a.campaign_id = p_campaign_id and a.status = 'reserved'
      and a.lease_expires_at <= now()
    order by a.started_at
    for update skip locked
  loop
    if v_attempt.sent_at is null then
      perform * from qb3.release_provider_attempt(
        v_attempt.attempt_id,
        '{"reason":"recovered_before_send"}'::jsonb
      );
      v_released := v_released + 1;
    else
      perform * from qb3.mark_provider_attempt_unknown(
        v_attempt.attempt_id,
        '{"reason":"expired_after_send","billing":"unknown"}'::jsonb
      );
      v_unknown := v_unknown + 1;
    end if;

    if v_attempt.agent_role = 'theme_metadata' then
      perform * from qb3.finish_metadata_attempt_failure(
        v_attempt.attempt_id, 'provider_result_missing', true
      );
    elsif v_attempt.agent_role in ('quality_judge', 'quality_escalation',
                                    'embedding', 'semantic_judge')
          and v_attempt.work_group_id is not null then
      perform * from qb3.finish_candidate_stage_group_failure(
        v_attempt.work_group_id,
        case when v_attempt.agent_role = 'quality_judge' then 'quality'
          when v_attempt.agent_role = 'quality_escalation'
            then 'quality_escalation'
          when v_attempt.agent_role = 'semantic_judge' then 'semantic'
          else 'embedding' end,
        'provider_result_missing', true
      );
    end if;
  end loop;

  -- A crash after claim but before reservation has no billable attempt. A
  -- crash after reservation was settled above before its group is unlocked.
  update qb3.candidate_stage_work w
  set status = case when w.attempt_count < 3 then 'pending'
                    else 'needs_attention' end,
      current_group_id = null, lease_expires_at = null,
      last_error_code = 'expired_stage_claim', updated_at = now()
  from qb3.candidates c
  where c.candidate_id = w.candidate_id
    and c.campaign_id = p_campaign_id
    and w.stage in ('quality', 'quality_escalation', 'embedding', 'semantic')
    and w.status = 'running' and w.lease_expires_at <= now()
    and not exists (
      select 1 from qb3.provider_attempts a
      where a.work_group_id = w.current_group_id and a.status = 'reserved'
    );

  -- Unknown Spend remains in the ledger and budget even when safe unrelated
  -- work may continue. Do not replace an existing operator pause with it.
  update qb3.campaigns
  set status = v_prior_status
  where campaign_id = p_campaign_id and status = 'unknown_spend';

  return query select v_released, v_unknown;
end;
$$;

create or replace function qb3.apply_metadata_items_partial(
  p_attempt_id text,
  p_items jsonb
)
returns table (applied_ids jsonb, pending_ids jsonb, invalid_items jsonb)
language plpgsql
as $$
declare
  v_attempt qb3.provider_attempts%rowtype;
  v_item jsonb;
  v_id_text text;
  v_candidate_id uuid;
  v_key text;
  v_applied jsonb := '[]'::jsonb;
  v_invalid jsonb := '[]'::jsonb;
  v_pending jsonb;
  v_reason text;
begin
  if jsonb_typeof(p_items) <> 'array' then
    raise exception 'metadata items must be an array';
  end if;

  select * into v_attempt from qb3.provider_attempts
  where attempt_id = p_attempt_id for update;
  if not found or v_attempt.agent_role <> 'theme_metadata'
     or v_attempt.status <> 'reconciled' then
    raise exception 'metadata attempt % is not reconciled', p_attempt_id;
  end if;

  for v_item in select value from jsonb_array_elements(p_items)
  loop
    v_reason := null;
    v_id_text := v_item ->> 'candidate_id';
    v_candidate_id := null;

    if jsonb_typeof(v_item) <> 'object' or v_id_text is null then
      v_reason := 'invalid_candidate_id';
    else
      begin
        v_candidate_id := v_id_text::uuid;
      exception when invalid_text_representation then
        v_reason := 'invalid_candidate_id';
      end;
    end if;

    if v_reason is null and (
      select count(*) from jsonb_array_elements(p_items) item
      where item ->> 'candidate_id' = v_id_text
    ) <> 1 then
      v_reason := 'duplicate_candidate_id';
    end if;

    if v_reason is null and not exists (
      select 1 from qb3.provider_attempt_candidates m
      where m.attempt_id = p_attempt_id and m.candidate_id = v_candidate_id
        and m.stage = 'metadata'
    ) then
      v_reason := 'candidate_not_in_attempt';
    end if;

    if v_reason is null and exists (
      select 1 from qb3.candidates c
      where c.candidate_id = v_candidate_id and c.metadata_result is not null
    ) then
      continue;
    end if;

    if v_reason is null and not exists (
      select 1 from qb3.candidates c
      join qb3.questions q using (candidate_id)
      where c.candidate_id = v_candidate_id and c.state = 'accepted'
        and c.metadata_result is null
    ) then
      v_reason := 'question_not_waiting_for_metadata';
    end if;

    if v_reason is null and not exists (
      select 1 from qb3.candidate_stage_work w
      where w.candidate_id = v_candidate_id and w.stage = 'metadata'
        and (v_attempt.work_group_id is null and w.current_group_id is null
             or v_attempt.work_group_id is not null
                and w.current_group_id = v_attempt.work_group_id
                and w.status = 'running'
             or v_attempt.work_group_id is not null
                and w.current_group_id is null
                and w.status in ('pending', 'retry_wait', 'needs_attention'))
    ) then
      v_reason := 'stale_metadata_attempt';
    end if;

    if v_reason is null and (
      jsonb_typeof(v_item -> 'themes') <> 'array'
      or jsonb_typeof(v_item -> 'question_form') <> 'string'
      or jsonb_typeof(v_item -> 'scenario_present') <> 'boolean'
      or jsonb_typeof(v_item -> 'contrast_present') <> 'boolean'
    ) then
      v_reason := 'invalid_required_metadata';
    end if;

    if v_reason is null then
      foreach v_key in array array['aspect', 'scenario', 'perspective',
                                   'answer_space', 'contrast']
      loop
        if not v_item ? v_key or jsonb_typeof(v_item -> v_key)
           not in ('string', 'null') then
          v_reason := 'invalid_' || v_key;
          exit;
        end if;
      end loop;
    end if;

    if v_reason is not null then
      v_invalid := v_invalid || jsonb_build_array(jsonb_build_object(
        'candidate_id', v_id_text, 'reason', v_reason));
      continue;
    end if;

    begin
      perform * from qb3.apply_question_metadata(v_candidate_id, v_item);
      update qb3.candidates
      set metadata_result = v_item, updated_at = now()
      where candidate_id = v_candidate_id and metadata_result is null;
      update qb3.candidate_stage_work
      set status = 'complete', current_group_id = null,
          lease_expires_at = null, next_retry_at = null,
          last_error_code = null, updated_at = now()
      where candidate_id = v_candidate_id and stage = 'metadata';
      v_applied := v_applied || jsonb_build_array(v_candidate_id);
    exception when others then
      v_invalid := v_invalid || jsonb_build_array(jsonb_build_object(
        'candidate_id', v_id_text, 'reason', 'metadata_validation_failed',
        'sqlstate', sqlstate));
    end;
  end loop;

  update qb3.candidate_stage_work w
  set status = case when w.attempt_count < 3
                    then 'retry_wait' else 'needs_attention' end,
      next_retry_at = case when w.attempt_count < 3
        then now() + case when w.attempt_count <= 1
          then interval '10 seconds' else interval '30 seconds' end
        else null end,
      current_group_id = null, lease_expires_at = null,
      last_error_code = 'metadata_item_missing_or_invalid', updated_at = now()
  from qb3.provider_attempt_candidates m
  join qb3.candidates c on c.candidate_id = m.candidate_id
  where m.attempt_id = p_attempt_id and m.stage = 'metadata'
    and w.candidate_id = m.candidate_id and w.stage = 'metadata'
    and c.metadata_result is null and w.status <> 'complete'
    and (v_attempt.work_group_id is null
         or w.current_group_id = v_attempt.work_group_id);

  select coalesce(jsonb_agg(m.candidate_id order by c.candidate_index), '[]'::jsonb)
  into v_pending
  from qb3.provider_attempt_candidates m
  join qb3.candidates c on c.candidate_id = m.candidate_id
  where m.attempt_id = p_attempt_id and m.stage = 'metadata'
    and c.metadata_result is null;

  return query select v_applied, v_pending, v_invalid;
end;
$$;

-- The agent may return a structured-output repair invocation rather than the
-- original provider attempt. Resolve membership by the durable work group,
-- never by the repair invocation's unrelated attempt ID.
create or replace function qb3.apply_metadata_group_partial(
  p_work_group_id text,
  p_items jsonb
)
returns table (applied_ids jsonb, pending_ids jsonb, invalid_items jsonb)
language plpgsql
as $$
declare
  v_attempt_id text;
begin
  select a.attempt_id into v_attempt_id
  from qb3.provider_attempts a
  where a.work_group_id = p_work_group_id
    and a.agent_role = 'theme_metadata'
    and a.status = 'reconciled'
  order by a.started_at desc, a.attempt_id desc
  limit 1;

  if v_attempt_id is null then
    raise exception 'metadata work group % has no reconciled attempt',
      p_work_group_id;
  end if;

  return query select * from qb3.apply_metadata_items_partial(
    v_attempt_id, p_items
  );
end;
$$;

create or replace function qb3.finish_metadata_group_failure(
  p_work_group_id text,
  p_error_code text,
  p_retryable boolean
)
returns table (retry_wait_count integer, needs_attention_count integer)
language plpgsql
as $$
declare
  v_attempt_id text;
  v_503_count integer;
begin
  select a.attempt_id into v_attempt_id
  from qb3.provider_attempts a
  where a.work_group_id = p_work_group_id
    and a.agent_role = 'theme_metadata'
    and a.status <> 'reserved'
  order by a.started_at desc, a.attempt_id desc
  limit 1;

  if v_attempt_id is null then
    -- Reservation failure already released the claim. A live reservation is
    -- deliberately left for lease recovery rather than being replayed.
    return query select 0, 0;
  else
    if not p_retryable then
      update qb3.campaigns c
      set status = 'configuration_error', updated_at = now()
      from qb3.provider_attempts a
      where a.attempt_id = v_attempt_id
        and c.campaign_id = a.campaign_id
        and c.status = 'running';
    else
      select count(*)::integer into v_503_count
      from qb3.provider_attempts recent
      join qb3.provider_attempts failed
        on failed.attempt_id = v_attempt_id
      where recent.campaign_id = failed.campaign_id
        and recent.provider = 'openai'
        and recent.sanitized_error ->> 'status_code' = '503'
        and recent.started_at > now() - interval '10 minutes';
      if v_503_count >= 6 then
        update qb3.campaigns c
        set status = 'provider_outage', completed_at = now(), updated_at = now()
        from qb3.provider_attempts a
        where a.attempt_id = v_attempt_id
          and c.campaign_id = a.campaign_id and c.status = 'running';
      end if;
    end if;
    return query select * from qb3.finish_metadata_attempt_failure(
      v_attempt_id, p_error_code, p_retryable
    );
  end if;
end;
$$;

-- Distribution dimensions describe questions ready for gameplay. Preserve the
-- admitted total separately for audit and expose the ready denominator.
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
    'ready_total', v_ready_total,
    'levels', (select jsonb_build_object(
      'shallow', count(*) filter (where q.level = 'shallow'),
      'deep', count(*) filter (where q.level = 'deep')
    ) from qb3.ready_questions q),
    'forms', coalesce((select jsonb_object_agg(form_name, form_count)
      from (select coalesce(question_form, 'unclassified') form_name, count(*) form_count
            from qb3.ready_questions group by 1) f), '{}'::jsonb),
    'scenario_presence', (select jsonb_build_object(
      'present', count(*) filter (where scenario_present is true),
      'absent', count(*) filter (where scenario_present is false),
      'unclassified', count(*) filter (where scenario_present is null)
    ) from qb3.ready_questions),
    'contrast_presence', (select jsonb_build_object(
      'present', count(*) filter (where contrast_present is true),
      'absent', count(*) filter (where contrast_present is false),
      'unclassified', count(*) filter (where contrast_present is null)
    ) from qb3.ready_questions),
    'themes', coalesce((select jsonb_object_agg(t.theme_code, jsonb_build_object(
        'count', coalesce(tc.question_count, 0),
        'percentage', case when v_ready_total = 0 then 0
          else round(100.0 * coalesce(tc.question_count, 0) / v_ready_total, 2) end
      ))
      from qb3.themes t
      left join (select theme_code, count(*) question_count from qb3.question_themes group by theme_code) tc using (theme_code)
      where t.active), '{}'::jsonb),
    'without_theme', (select count(*) from qb3.ready_questions q
      where not exists (select 1 from qb3.question_themes qt where qt.question_id = q.question_id)),
    'theme_combinations', coalesce((select jsonb_agg(to_jsonb(combo) order by combo.question_count desc, combo.theme_codes)
      from (select theme_codes, count(*) question_count from (
              select array_agg(qt.theme_code order by qt.theme_code) theme_codes
              from qb3.question_themes qt group by qt.question_id
            ) per_question group by theme_codes) combo), '[]'::jsonb),
    'representative_recent_accepted', coalesce((select jsonb_agg(to_jsonb(r) order by r.accepted_at desc)
      from (select q.question_id, q.question_text, q.level, q.question_form, q.accepted_at
            from qb3.ready_questions q order by q.accepted_at desc limit 20) r), '[]'::jsonb),
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
