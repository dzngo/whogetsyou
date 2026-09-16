\set ON_ERROR_STOP on

begin;

do $$
begin
  if not exists (
    select 1 from qb3.campaigns
    where campaign_id = 'qb3-repair-qualification'
  ) then
    raise exception 'repair qualification campaign is missing';
  end if;

  if not exists (
    select 1
    from qb3.provider_attempts
    where attempt_id = 'qb3-repair-qualification-source-repair'
      and campaign_id = 'qb3-repair-qualification'
      and agent_role = 'structured_output_repair'
      and provider = 'gemini'
      and status = 'reconciled'
      and actual_cost_usd = 0.001468
      and (parent_attempt_id is null or parent_attempt_id = 'qb3-repair-qualification-source')
  ) then
    raise exception 'preserved first repair attempt does not match the audited execution';
  end if;

  if exists (
    select 1 from qb3.provider_attempts
    where attempt_id = 'qb3-repair-qualification-source'
      and (campaign_id <> 'qb3-repair-qualification' or agent_role <> 'semantic_judge')
  ) then
    raise exception 'source attempt id already belongs to different evidence';
  end if;
end;
$$;

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
  'qb3-repair-qualification-source',
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
  'qb3-repair-qualification-source',
  'qb3-repair-qualification-source',
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
  repair_of_invocation_id,
  completed_at
) values (
  'qb3-repair-qualification-source-repair',
  'qb3-repair-qualification-source-repair',
  'qb3-repair-qualification',
  'structured_output_repair',
  'repair_structured_output',
  'v1',
  $prompt$You are the Structured Output Repair Agent for Question Bank v3. Convert the supplied malformed model response into data that satisfies the supplied JSON Schema. Preserve the original meaning and identifiers. Do not add substantive judgments or creative content. If repair is impossible, return repairable false and a concise error. Return only the required JSON schema. INPUT: <<REPAIR_INPUT_JSON>>

CONTEXT:
{"malformed_response":"{\"decision\":\"distinct\",}","validation_error":"Expected double-quoted property name in JSON at position 23 (line 1 column 24)","required_output_schema":{"type":"object","required":["decision"],"properties":{"decision":{"type":"string","enum":["duplicate","distinct","uncertain"]}},"additionalProperties":false},"original_agent_role":"semantic_judge","original_prompt_key":"judge_semantic_duplication"}$prompt$,
  '{"repairable":true,"repaired_output":{"decision":"distinct"},"error":null}',
  '{"repairable":true,"repaired_output":{"decision":"distinct"},"error":null}'::jsonb,
  'succeeded',
  'qb3-repair-qualification-source',
  now()
)
on conflict (invocation_id) do nothing;

do $$
declare
  v_attempts integer;
  v_runs integer;
begin
  select count(*) into v_attempts
  from qb3.provider_attempts
  where campaign_id = 'qb3-repair-qualification';

  select count(*) into v_runs
  from qb3.agent_runs
  where campaign_id = 'qb3-repair-qualification';

  if v_attempts <> 4 or v_runs <> 4 then
    raise exception 'expected four qualification attempts and four traces, got % and %',
      v_attempts, v_runs;
  end if;
end;
$$;

commit;
