\set ON_ERROR_STOP on

begin;

insert into qb3.provider_attempts (
  attempt_id,
  campaign_id,
  agent_role,
  provider,
  requested_model,
  reported_model,
  reasoning_setting,
  reservation_usd,
  actual_cost_usd,
  status,
  usage,
  completed_at
) values (
  'qb3-repair-qualification-source-2',
  'qb3-repair-qualification',
  'semantic_judge',
  'gemini',
  'pinned-original',
  'pinned-original',
  'high',
  0.001000,
  0.000000,
  'reconciled',
  '{"qualification_fixture":true,"provider_called":false}'::jsonb,
  now()
)
on conflict (attempt_id) do nothing;

insert into qb3.agent_runs (
  invocation_id,
  attempt_id,
  campaign_id,
  agent_role,
  prompt_key,
  prompt_version,
  rendered_prompt,
  raw_response,
  structured_response,
  status,
  completed_at
) values (
  'qb3-repair-qualification-source-2',
  'qb3-repair-qualification-source-2',
  'qb3-repair-qualification',
  'semantic_judge',
  'judge_semantic_duplication',
  'qualification',
  'Qualification fixture: return a semantic decision.',
  '{"decision":"distinct",}',
  '{}'::jsonb,
  'schema_failed',
  now()
)
on conflict (invocation_id) do nothing;

do $$
declare
  v_count integer;
begin
  select count(*) into v_count
  from qb3.agent_runs
  where invocation_id = 'qb3-repair-qualification-source-2'
    and status = 'schema_failed';

  if v_count <> 1 then
    raise exception 'repair qualification parent trace was not created';
  end if;
end;
$$;

commit;
