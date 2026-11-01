-- Persist one route-controlled candidate at its durable slot (one through five)
-- instead of requiring a Creative invocation to return a five-question bundle.
create or replace function qb3.persist_mission_and_route_candidate(
  p_campaign_id text,
  p_batch_id uuid,
  p_mission_slot integer,
  p_level text,
  p_observation_report jsonb,
  p_mission jsonb,
  p_route_slot integer,
  p_question text
)
returns table (mission_id uuid, candidate_id uuid, candidate_index smallint, question_text text)
language plpgsql
as $$
declare
  v_mission_id uuid;
  v_requested_mix jsonb;
  v_expected_level text;
begin
  if p_mission_slot not between 1 and 4 or p_route_slot not between 1 and 5 then
    raise exception 'mission slot must be one through four and route slot one through five';
  end if;
  if length(btrim(p_question)) < 3 then
    raise exception 'route candidate question is required';
  end if;

  select b.requested_level_mix into v_requested_mix
  from qb3.batches b
  where b.batch_id = p_batch_id and b.campaign_id = p_campaign_id;
  if not found then
    raise exception 'batch % does not belong to campaign %', p_batch_id, p_campaign_id;
  end if;

  v_expected_level := case
    when p_mission_slot <= coalesce((v_requested_mix ->> 'shallow')::integer, 0) / 5
      then 'shallow' else 'deep' end;
  if p_level <> v_expected_level
     or (p_mission ->> 'mission_slot')::integer <> p_mission_slot
     or p_mission ->> 'level' <> p_level then
    raise exception 'mission slot %, level %, and requested level mix are inconsistent', p_mission_slot, p_level;
  end if;

  insert into qb3.missions (
    campaign_id, batch_id, mission_slot, level, observation_report, mission
  ) values (
    p_campaign_id, p_batch_id, p_mission_slot, p_level,
    p_observation_report, p_mission
  ) on conflict (batch_id, mission_slot) do update
    set observation_report = excluded.observation_report,
        mission = excluded.mission
  returning qb3.missions.mission_id into v_mission_id;

  insert into qb3.candidates (
    campaign_id, batch_id, mission_id, candidate_index,
    question_text, normalized_text, level
  ) values (
    p_campaign_id, p_batch_id, v_mission_id,
    (((p_mission_slot - 1) * 5) + p_route_slot)::smallint,
    btrim(p_question), qb3.normalize_question(p_question), p_level
  ) on conflict on constraint candidates_batch_id_candidate_index_key do nothing;

  return query
  select c.mission_id, c.candidate_id, c.candidate_index, c.question_text
  from qb3.candidates c
  where c.batch_id = p_batch_id
    and c.candidate_index = (((p_mission_slot - 1) * 5) + p_route_slot)::smallint;
end;
$$;
