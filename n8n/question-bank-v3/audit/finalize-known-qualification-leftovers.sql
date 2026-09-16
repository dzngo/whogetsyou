\set ON_ERROR_STOP on

begin;

do $$
declare
  v_1897 integer;
  v_2434 integer;
begin
  select count(*) into v_1897
  from qb3.candidates
  where campaign_id = 'qb3-1897' and state = 'proposed';

  select count(*) into v_2434
  from qb3.candidates
  where campaign_id = 'qb3-2434' and state = 'proposed';

  if v_1897 <> 14 or v_2434 <> 15 then
    raise exception
      'Refusing qualification leftover finalization: expected qb3-1897/qb3-2434 proposed counts 14/15, found %/%',
      v_1897,
      v_2434;
  end if;
end;
$$;

update qb3.candidates candidate
set state = 'operationally_unresolved',
    rejection_reason_codes = jsonb_build_array(
      case candidate.campaign_id
        when 'qb3-1897' then 'campaign_cancelled_before_candidate'
        when 'qb3-2434' then 'campaign_budget_exhausted_before_candidate'
      end
    ),
    feedback_note = case candidate.campaign_id
      when 'qb3-1897' then 'Campaign was cancelled before this candidate was processed.'
      when 'qb3-2434' then 'Campaign budget was exhausted before this candidate was processed.'
    end,
    updated_at = now()
where candidate.campaign_id in ('qb3-1897', 'qb3-2434')
  and candidate.state = 'proposed';

do $$
begin
  if exists (
    select 1 from qb3.candidates
    where campaign_id in ('qb3-1897', 'qb3-2434')
      and state = 'proposed'
  ) then
    raise exception 'Qualification leftover finalization left proposed candidates behind';
  end if;
end;
$$;

commit;

select campaign_id, state, count(*)
from qb3.candidates
where campaign_id in ('qb3-1897', 'qb3-2434')
group by campaign_id, state
order by campaign_id, state;
