\set ON_ERROR_STOP on

begin;

do $$
declare
  v_unlinked integer;
  v_parents integer;
begin
  select count(*) into v_unlinked
  from qb3.provider_attempts
  where campaign_id = 'qb3-repair-qualification'
    and agent_role = 'structured_output_repair'
    and parent_attempt_id is null;

  select count(*) into v_parents
  from qb3.provider_attempts
  where attempt_id in (
    'qb3-repair-qualification-source',
    'qb3-repair-qualification-source-2'
  );

  if v_unlinked <> 2 or v_parents <> 2 then
    raise exception 'expected two unlinked repairs and two parent attempts';
  end if;
end;
$$;

update qb3.provider_attempts
set parent_attempt_id = regexp_replace(attempt_id, '-repair$', '')
where campaign_id = 'qb3-repair-qualification'
  and agent_role = 'structured_output_repair'
  and parent_attempt_id is null;

do $$
declare
  v_linked integer;
begin
  select count(*) into v_linked
  from qb3.provider_attempts child
  join qb3.provider_attempts parent
    on parent.attempt_id = child.parent_attempt_id
  where child.campaign_id = 'qb3-repair-qualification'
    and child.agent_role = 'structured_output_repair';

  if v_linked <> 2 then
    raise exception 'repair qualification provider-attempt links are incomplete';
  end if;
end;
$$;

commit;
