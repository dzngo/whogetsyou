\set ON_ERROR_STOP on

begin;

create table if not exists qb3.workflow_execution_context (
  execution_id text primary key,
  workflow_id text not null,
  campaign_id text not null references qb3.campaigns(campaign_id) on delete restrict,
  created_at timestamptz not null default now()
);

create index if not exists workflow_execution_context_campaign_idx
  on qb3.workflow_execution_context (campaign_id, created_at desc);

commit;
