\set ON_ERROR_STOP on

begin;

create or replace function qb3.campaign_command(
  p_campaign_id text,
  p_action text,
  p_additional_budget_usd numeric default 0
)
returns table (result jsonb)
language plpgsql
as $$
begin
  if p_action = 'cancel' then
    perform * from qb3.request_campaign_cancel(p_campaign_id);
  elsif p_action = 'resume' then
    perform * from qb3.resume_campaign(p_campaign_id, p_additional_budget_usd);
  elsif p_action <> 'status' then
    raise exception 'unsupported campaign action %', p_action;
  end if;

  return query
  select to_jsonb(s) from qb3.campaign_status s
  where s.campaign_id = p_campaign_id;

  if not found then
    raise exception 'campaign % not found', p_campaign_id;
  end if;
end;
$$;

drop function if exists qb3.continue_campaign(text);

commit;
