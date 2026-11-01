-- Reject unambiguously non-light shallow candidates without paying for a model call.
-- A complete quality_result lets the existing stage-work trigger mark Quality done.
create or replace function qb3.apply_deterministic_shallow_gate(p_batch_id uuid)
returns table (rejected_count integer, rejected_candidate_ids jsonb)
language plpgsql
as $$
begin
  with flagged as (
    select c.candidate_id,
      array_remove(array[
        case when cardinality(regexp_split_to_array(btrim(c.question_text), '\s+')) > 18 then 'shallow_word_limit' end,
        case when c.question_text ~* '\m(you|your|yours|yourself)\M' then 'shallow_second_person_voice' end,
        case when c.question_text ~* '\m(either|or|versus|vs)\M' then 'shallow_forced_options' end,
        case when c.question_text ~* '[0-9]' or c.question_text ~* '\m(exact|exactly|maximum|minimum|threshold|ranking|rank|scale)\M' or c.question_text ~* 'how\s+(many|long)' or c.question_text ~* 'number\s+of' then 'shallow_precision_burden' end
      ], null) as reason_codes
    from qb3.candidates c
    where c.batch_id = p_batch_id
      and c.state = 'proposed'
      and c.level = 'shallow'
  ), rejected as (
    update qb3.candidates c
    set state = 'quality_rejected',
        quality_result = jsonb_build_object(
          'verdict', 'reject',
          'reason_codes', to_jsonb(f.reason_codes),
          'feedback_note', 'Deterministic shallow form gate',
          'escalated', false
        ),
        rejection_reason_codes = to_jsonb(f.reason_codes),
        feedback_note = 'Deterministic shallow form gate'
    from flagged f
    where c.candidate_id = f.candidate_id
      and cardinality(f.reason_codes) > 0
    returning c.candidate_id
  )
  select count(*)::integer, coalesce(jsonb_agg(candidate_id), '[]'::jsonb)
  into rejected_count, rejected_candidate_ids
  from rejected;

  return next;
end;
$$;
