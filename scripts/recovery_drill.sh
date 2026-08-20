#!/usr/bin/env bash
set -Eeuo pipefail

drill_id="$(date -u +%Y%m%d%H%M%S)"
source_db="stackgraph_drill_source_${drill_id}"
restore_db="stackgraph_drill_restore_${drill_id}"
dump_path="/tmp/${source_db}.dump"
admin_user="${STACKGRAPH_DB_ADMIN_USER:-stackgraph_admin}"
admin_password="${STACKGRAPH_DB_ADMIN_PASSWORD:-stackgraph_admin}"
artifact_dir="${STACKGRAPH_RECOVERY_ARTIFACT_DIR:-artifacts/recovery}"
artifact_path="${artifact_dir}/recovery-${drill_id}.json"

mkdir -p "${artifact_dir}"

cleanup() {
  docker compose exec -T database psql -v ON_ERROR_STOP=1 -U "${admin_user}" -d postgres \
    -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname IN ('${source_db}','${restore_db}') AND pid<>pg_backend_pid()" >/dev/null 2>&1 || true
  docker compose exec -T database dropdb -U "${admin_user}" --if-exists "${source_db}" >/dev/null 2>&1 || true
  docker compose exec -T database dropdb -U "${admin_user}" --if-exists "${restore_db}" >/dev/null 2>&1 || true
  docker compose exec -T database rm -f "${dump_path}" >/dev/null 2>&1 || true
}
trap cleanup EXIT

started_epoch="$(date +%s)"
docker compose up --wait -d database >/dev/null
docker compose exec -T database createdb -U "${admin_user}" "${source_db}"
docker compose exec -T database psql -v ON_ERROR_STOP=1 -U "${admin_user}" -d "${source_db}" \
  -f /docker-entrypoint-initdb.d/010-schema.sql >/dev/null
docker compose exec -T database psql -v ON_ERROR_STOP=1 -U "${admin_user}" -d "${source_db}" \
  -f /docker-entrypoint-initdb.d/020-create-graph.sql >/dev/null
docker compose run --rm --no-deps \
  -e STACKGRAPH_DATABASE_URL="postgresql://${admin_user}:${admin_password}@database:5432/${source_db}" \
  seed >/dev/null
docker compose exec -T database psql -v ON_ERROR_STOP=1 -U "${admin_user}" -d "${source_db}" \
  -c "INSERT INTO tenant(id,tenant_key,name) VALUES ('00000000-0000-0000-0000-000000000099','recovery-drill','Recovery drill sentinel')" >/dev/null

source_counts="$(docker compose exec -T database psql -At -v ON_ERROR_STOP=1 -U "${admin_user}" -d "${source_db}" \
  -c "SELECT json_build_object('tenant',count(*),'entity',(SELECT count(*) FROM entity),'fact',(SELECT count(*) FROM fact_assertion),'migration',(SELECT count(*) FROM schema_migration)) FROM tenant")"

docker compose exec -T database pg_dump -U "${admin_user}" -d "${source_db}" -Fc -f "${dump_path}"
docker compose exec -T database createdb -U "${admin_user}" "${restore_db}"
docker compose exec -T database pg_restore -U "${admin_user}" -d "${restore_db}" --no-owner --exit-on-error "${dump_path}" >/dev/null

restore_counts="$(docker compose exec -T database psql -At -v ON_ERROR_STOP=1 -U "${admin_user}" -d "${restore_db}" \
  -c "SELECT json_build_object('tenant',count(*),'entity',(SELECT count(*) FROM entity),'fact',(SELECT count(*) FROM fact_assertion),'migration',(SELECT count(*) FROM schema_migration)) FROM tenant")"
test "${source_counts}" = "${restore_counts}"

docker compose exec -T database psql -v ON_ERROR_STOP=1 -U "${admin_user}" -d "${restore_db}" >/dev/null <<'SQL'
LOAD 'age';
SET search_path = ag_catalog, "$user", public;
SELECT drop_graph('stackgraph', true) WHERE EXISTS (
  SELECT 1 FROM ag_catalog.ag_graph WHERE name='stackgraph'
);
SELECT create_graph('stackgraph');
UPDATE projection_outbox SET processed_at=NULL,leased_by=NULL,leased_until=NULL,last_error=NULL;
SQL
docker compose run --rm --no-deps \
  -e STACKGRAPH_DATABASE_URL="postgresql://${admin_user}:${admin_password}@database:5432/${restore_db}" \
  projection >/dev/null

remaining_projection="$(docker compose exec -T database psql -At -v ON_ERROR_STOP=1 -U "${admin_user}" -d "${restore_db}" \
  -c "SELECT count(*) FROM projection_outbox WHERE processed_at IS NULL")"
test "${remaining_projection}" = "0"

cleanup
remaining_databases="$(docker compose exec -T database psql -At -v ON_ERROR_STOP=1 -U "${admin_user}" -d postgres \
  -c "SELECT count(*) FROM pg_database WHERE datname IN ('${source_db}','${restore_db}')")"
test "${remaining_databases}" = "0"
trap - EXIT

completed_epoch="$(date +%s)"
duration_seconds="$((completed_epoch-started_epoch))"
cat >"${artifact_path}" <<JSON
{
  "schema_version": "1.0.0",
  "generated_at": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "duration_seconds": ${duration_seconds},
  "source_counts": ${source_counts},
  "restore_counts": ${restore_counts},
  "pending_projection_events_after_rebuild": ${remaining_projection},
  "database_restore_passed": true,
  "projection_rebuild_passed": true,
  "ephemeral_databases_removed": $([ "${remaining_databases}" = "0" ] && printf true || printf false)
}
JSON
printf '%s\n' "${artifact_path}"
