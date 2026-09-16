#!/usr/bin/env bash
set -euo pipefail

container_name="question-bank-v3-sql-test"
image="${QB3_TEST_POSTGRES_IMAGE:-ghcr.io/supabase/postgres:17.6.1.159}"

cleanup() {
  docker rm -f "$container_name" >/dev/null 2>&1 || true
}
trap cleanup EXIT

cleanup
docker run --name "$container_name" \
  -e POSTGRES_PASSWORD=test-only-password \
  -d "$image" >/dev/null

ready_streak=0
for _ in $(seq 1 80); do
  if docker exec "$container_name" pg_isready -U supabase_admin -d postgres >/dev/null 2>&1; then
    ready_streak=$((ready_streak + 1))
    if [[ "$ready_streak" -ge 3 ]]; then
      break
    fi
  else
    ready_streak=0
  fi
  sleep 0.5
done

if [[ "$ready_streak" -lt 3 ]]; then
  docker logs "$container_name"
  echo "PostgreSQL did not become stably ready" >&2
  exit 1
fi

docker exec -i "$container_name" psql -v ON_ERROR_STOP=1 \
  -U supabase_admin -d postgres \
  < "$(dirname "$0")/sql/001_question_bank_v3.sql"

docker exec -i "$container_name" psql -v ON_ERROR_STOP=1 \
  -U supabase_admin -d postgres \
  < "$(dirname "$0")/sql/002_continue_cancelled_campaign.sql"

docker exec -i "$container_name" psql -v ON_ERROR_STOP=1 \
  -U supabase_admin -d postgres \
  < "$(dirname "$0")/sql/003_skip_existing_candidate_embeddings.sql"

docker exec -i "$container_name" psql -v ON_ERROR_STOP=1 \
  -U supabase_admin -d postgres \
  < "$(dirname "$0")/sql/004_enforce_campaign_admission_target.sql"

docker exec -i "$container_name" psql -v ON_ERROR_STOP=1 \
  -U supabase_admin -d postgres \
  < "$(dirname "$0")/sql/005_finalize_unprocessed_candidates.sql"

docker exec -i "$container_name" psql -v ON_ERROR_STOP=1 \
  -U supabase_admin -d postgres \
  < "$(dirname "$0")/sql/006_resume_successful_repair.sql"

docker exec -i "$container_name" psql -v ON_ERROR_STOP=1 \
  -U supabase_admin -d postgres \
  < "$(dirname "$0")/sql/007_track_workflow_execution_context.sql"

docker exec -i "$container_name" psql -v ON_ERROR_STOP=1 \
  -U supabase_admin -d postgres \
  < "$(dirname "$0")/sql/008_harden_generation_quality_distribution.sql"

docker exec -i "$container_name" psql -v ON_ERROR_STOP=1 \
  -U supabase_admin -d postgres \
  < "$(dirname "$0")/sql/009_harden_resume_trace_and_metadata.sql"

docker exec -i "$container_name" psql -v ON_ERROR_STOP=1 \
  -U supabase_admin -d postgres \
  < "$(dirname "$0")/sql/900_test_question_bank_v3.sql"
