#!/usr/bin/env bash
set -euo pipefail

dry_run=false
if [[ "${1:-}" == "--dry-run" ]]; then
  dry_run=true
elif [[ -n "${1:-}" ]]; then
  echo "usage: $0 [--dry-run]" >&2
  exit 64
fi

project_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
compose_file="${QB3_COMPOSE_FILE:-$project_dir/compose.yaml}"
postgres_service="${QB3_POSTGRES_SERVICE:-question-bank-postgres}"

container_env() {
  docker compose -f "$compose_file" exec -T "$postgres_service" \
    printenv "$1" | tr -d '\r'
}

postgres_user="${QB3_POSTGRES_USER:-$(container_env POSTGRES_USER)}"
postgres_database="${QB3_POSTGRES_DB:-$(container_env POSTGRES_DB)}"

psql_compose() {
  docker compose -f "$compose_file" exec -T "$postgres_service" \
    psql -v ON_ERROR_STOP=1 -U "$postgres_user" -d "$postgres_database" "$@"
}

if ! psql_compose -tAc "select to_regclass('qb3.schema_migrations') is not null;" \
  | grep -qx 't'; then
  if [[ "$dry_run" == true ]]; then
    echo "pending bootstrap: qb3.schema_migrations table"
  else
    psql_compose -c "create table qb3.schema_migrations (
      migration_name text primary key,
      applied_at timestamptz not null default now()
    );" >/dev/null
  fi
fi

shopt -s nullglob
migrations=("$project_dir"/sql/[0-8][0-9][0-9]_*.sql)

for migration in "${migrations[@]}"; do
  migration_name="$(basename "$migration")"
  if [[ "$migration_name" == 001_* ]]; then
    continue
  fi

  already_applied=""
  if psql_compose -tAc "select to_regclass('qb3.schema_migrations') is not null;" | grep -qx 't'; then
    already_applied="$(psql_compose -tAc "select 1 from qb3.schema_migrations where migration_name = '$migration_name';")"
  fi
  if [[ "$already_applied" == "1" ]]; then
    printf 'already applied: %s\n' "$migration_name"
    continue
  fi

  if [[ "$dry_run" == true ]]; then
    printf 'pending: %s\n' "$migration_name"
  else
    psql_compose < "$migration"
    psql_compose -c "insert into qb3.schema_migrations (migration_name) values ('$migration_name');" >/dev/null
    printf 'applied: %s\n' "$migration_name"
  fi
done
