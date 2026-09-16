\set ON_ERROR_STOP on

begin;

insert into qb3.campaigns (
  campaign_id,
  campaign_name,
  raw_input,
  level_mode,
  accepted_target,
  shallow_target,
  deep_target,
  authorized_budget_usd,
  status,
  cancel_requested,
  prompt_snapshot_id,
  emergency_batch_ceiling,
  notes
)
select
  'qb3-repair-qualification',
  'Structured-output repair qualification',
  jsonb_build_object('purpose', 'exercise one guarded Gemini structured-output repair'),
  'shallow',
  1,
  1,
  0,
  0.030000,
  'running',
  false,
  prompt_snapshot_id,
  1,
  'Qualification-only campaign. It does not generate or admit questions.'
from qb3.campaigns
where campaign_id = 'qb3-2434'
on conflict (campaign_id) do nothing;

do $$
declare
  v_count integer;
begin
  select count(*) into v_count
  from qb3.campaigns
  where campaign_id = 'qb3-repair-qualification'
    and authorized_budget_usd = 0.030000
    and status = 'running';

  if v_count <> 1 then
    raise exception 'repair qualification campaign was not created in the expected state';
  end if;
end;
$$;

commit;
