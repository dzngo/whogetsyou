\set ON_ERROR_STOP on

begin;

create or replace function qb3.complete_batch(p_batch_id uuid)
returns table (campaign_status text, distribution_snapshot_id uuid)
language plpgsql
as $$
declare
  v_campaign_id text;
  v_snapshot_id uuid;
begin
  update qb3.batches b
  set status = 'completed', completed_at = coalesce(completed_at, now())
  where b.batch_id = p_batch_id
  returning b.campaign_id into v_campaign_id;

  if not found then
    raise exception 'batch % not found', p_batch_id;
  end if;

  update qb3.campaigns c
  set status = case
        when c.accepted_shallow >= c.shallow_target
          and c.accepted_deep >= c.deep_target then 'completed'
        when c.cancel_requested then 'cancelled_partial'
        when c.spent_usd + c.reserved_usd + c.unknown_spend_usd
          >= c.authorized_budget_usd then 'budget_exhausted_partial'
        else c.status
      end,
      completed_at = case
        when (c.accepted_shallow >= c.shallow_target and c.accepted_deep >= c.deep_target)
          or c.cancel_requested
          or c.spent_usd + c.reserved_usd + c.unknown_spend_usd >= c.authorized_budget_usd
        then now() else c.completed_at end
  where c.campaign_id = v_campaign_id;

  update qb3.candidates candidate
  set state = 'operationally_unresolved',
      rejection_reason_codes = jsonb_build_array(
        case
          when campaign.status = 'running' then 'level_target_reached'
          else case campaign.status
          when 'completed' then 'campaign_target_reached'
          when 'cancelled_partial' then 'campaign_cancelled_before_candidate'
          when 'budget_exhausted_partial' then 'campaign_budget_exhausted_before_candidate'
          when 'unknown_spend' then 'campaign_stopped_for_unknown_spend'
          when 'configuration_error' then 'campaign_configuration_error'
          when 'database_error' then 'campaign_database_error'
          when 'safety_ceiling_reached' then 'campaign_safety_ceiling_reached'
          else 'campaign_stopped_before_candidate'
          end
        end
      ),
      feedback_note = case
        when campaign.status = 'running' then 'The campaign target for this question level was reached before this candidate was needed.'
        else case campaign.status
        when 'completed' then 'Campaign target was reached before this candidate was needed.'
        when 'cancelled_partial' then 'Campaign was cancelled before this candidate was processed.'
        when 'budget_exhausted_partial' then 'Campaign budget was exhausted before this candidate was processed.'
        else 'Campaign stopped before this candidate was processed.'
        end
      end,
      updated_at = now()
  from qb3.campaigns campaign
  where candidate.campaign_id = v_campaign_id
    and campaign.campaign_id = candidate.campaign_id
    and (
      campaign.status <> 'running'
      or (candidate.level = 'shallow' and campaign.accepted_shallow >= campaign.shallow_target)
      or (candidate.level = 'deep' and campaign.accepted_deep >= campaign.deep_target)
    )
    and candidate.state = 'proposed';

  v_snapshot_id := qb3.refresh_distribution_snapshot(v_campaign_id, p_batch_id);

  return query
  select c.status, v_snapshot_id
  from qb3.campaigns c where c.campaign_id = v_campaign_id;
end;
$$;

commit;
