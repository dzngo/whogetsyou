\set ON_ERROR_STOP on

begin;

create or replace function qb3.get_preflight_candidates(p_batch_id uuid)
returns table (candidate_id uuid, question_text text, level text)
language sql
stable
as $$
  select c.candidate_id, c.question_text, c.level
  from qb3.candidates c
  where c.batch_id = p_batch_id
    and c.state = 'proposed'
    and c.quality_result ->> 'verdict' = 'pass'
    and c.embedding is null
  order by c.candidate_index;
$$;

commit;
