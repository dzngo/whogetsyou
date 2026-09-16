\set ON_ERROR_STOP on

begin;

do $$
begin
  if not exists (
    select 1
    from qb3.candidates c
    join qb3.questions q using (candidate_id)
    where c.candidate_id = 'a0bd8da7-b981-4259-bdf6-ce3ff3da0628'
      and c.campaign_id = 'qb3-1897'
      and c.state = 'accepted'
      and c.metadata_result is null
  ) then
    raise exception 'Expected retained qb3-1897 travel candidate with missing metadata';
  end if;
end;
$$;

select *
from qb3.apply_metadata_results(
  '6a7d65e1-2697-4370-b5e4-30dacb58e643'::uuid,
  jsonb_build_array(jsonb_build_object(
    'candidate_id', 'a0bd8da7-b981-4259-bdf6-ce3ff3da0628',
    'themes', jsonb_build_array('travel'),
    'question_form', 'choice',
    'scenario_present', true,
    'contrast_present', true,
    'aspect', 'Travel seating preference',
    'scenario', 'Choosing a seat on a train or plane',
    'perspective', 'Habitual comfort preference',
    'answer_space', 'Window seat or aisle seat',
    'contrast', 'View and enclosure versus mobility and access'
  ))
);

do $$
begin
  if exists (
    select 1
    from qb3.questions q
    join qb3.candidates c using (candidate_id)
    where c.campaign_id in ('qb3-1897', 'qb3-2434')
      and c.state = 'accepted'
      and c.metadata_result is null
  ) then
    raise exception 'Qualification bank still has accepted questions missing metadata';
  end if;
end;
$$;

commit;
