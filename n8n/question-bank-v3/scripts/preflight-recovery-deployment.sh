#!/usr/bin/env bash
set -euo pipefail

# Read-only evidence for the recovery rollout. This script deliberately does
# not apply a migration, resume a campaign, or call any model provider.
project_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
compose_file="${QB3_COMPOSE_FILE:-$project_dir/compose.yaml}"
postgres_service="${QB3_POSTGRES_SERVICE:-question-bank-postgres}"
campaign_id="${1:-qb3-2871}"

container_env() {
  docker compose -f "$compose_file" exec -T "$postgres_service" \
    printenv "$1" | tr -d '\r'
}

postgres_user="${QB3_POSTGRES_USER:-$(container_env POSTGRES_USER)}"
postgres_database="${QB3_POSTGRES_DB:-$(container_env POSTGRES_DB)}"

docker compose -f "$compose_file" exec -T "$postgres_service" \
  psql -v ON_ERROR_STOP=1 -P pager=off -U "$postgres_user" -d "$postgres_database" \
  -v campaign_id="$campaign_id" <<'SQL'
select 'migration_010_applied' as check_name,
       exists (
         select 1 from qb3.schema_migrations
         where migration_name = '010_question_stage_progress.sql'
       ) as value;

select 'stage_work_table_present' as check_name,
       to_regclass('qb3.candidate_stage_work') is not null as value;

select campaign_id, status, authorized_budget_usd, spent_usd, reserved_usd,
       unknown_spend_usd
from qb3.campaigns
where campaign_id = :'campaign_id';

select count(*) filter (where c.state = 'accepted') as accepted,
       count(*) filter (where c.state = 'accepted' and c.metadata_result is null)
         as metadata_missing,
       count(*) filter (where c.state = 'accepted' and c.metadata_result is not null)
         as metadata_complete
from qb3.candidates c
where c.campaign_id = :'campaign_id';

select attempt_id, agent_role, status, reservation_usd, started_at,
       lease_expires_at, lease_expires_at <= now() as lease_expired
from qb3.provider_attempts
where campaign_id = :'campaign_id' and status = 'reserved'
order by started_at;
SQL
