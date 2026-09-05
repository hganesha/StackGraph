#!/usr/bin/env bash
set -Eeuo pipefail

matrix_id="$(date -u +%Y%m%d%H%M%S)"
database_name="stackgraph_verify_${matrix_id}"
admin_user="${STACKGRAPH_DB_ADMIN_USER:-stackgraph_admin}"
admin_password="${STACKGRAPH_DB_ADMIN_PASSWORD:-stackgraph_admin}"
app_user="${STACKGRAPH_DB_APP_USER:-stackgraph_app}"
app_password="${STACKGRAPH_DB_APP_PASSWORD:-stackgraph_app}"
admin_url="postgresql://${admin_user}:${admin_password}@database:5432/${database_name}"
app_url="postgresql://${app_user}:${app_password}@database:5432/${database_name}"

cleanup() {
  docker compose exec -T database psql -v ON_ERROR_STOP=1 -U "${admin_user}" -d postgres \
    -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname='${database_name}' AND pid<>pg_backend_pid()" >/dev/null 2>&1 || true
  docker compose exec -T database dropdb -U "${admin_user}" --if-exists "${database_name}" >/dev/null 2>&1 || true
}
trap cleanup EXIT

docker compose up --wait -d database >/dev/null
docker compose build -q api seed >/dev/null
docker compose exec -T database createdb -U "${admin_user}" "${database_name}"
docker compose exec -T database psql -v ON_ERROR_STOP=1 -U "${admin_user}" -d "${database_name}" \
  -f /docker-entrypoint-initdb.d/010-schema.sql >/dev/null
docker compose run --rm --no-deps -e STACKGRAPH_DATABASE_URL="${admin_url}" migrate >/dev/null
docker compose exec -T database psql -v ON_ERROR_STOP=1 -U "${admin_user}" -d "${database_name}" \
  -f /stackgraph/tests/neo4j-projection-smoke.sql >/dev/null
docker compose exec -T database psql -v ON_ERROR_STOP=1 -U "${admin_user}" -d "${database_name}" \
  -f /stackgraph/tests/graph-analysis-control-plane-smoke.sql >/dev/null
docker compose exec -T database psql -v ON_ERROR_STOP=1 -U "${admin_user}" -d "${database_name}" \
  -f /stackgraph/tests/embedding-control-plane-smoke.sql >/dev/null
docker compose exec -T database psql -v ON_ERROR_STOP=1 -U "${admin_user}" -d "${database_name}" \
  -v app_user="${app_user}" >/dev/null <<'SQL'
SELECT format('GRANT CONNECT ON DATABASE %I TO %I', current_database(), :'app_user') \gexec
SELECT format('GRANT USAGE ON SCHEMA %I TO %I',nspname,:'app_user') FROM pg_namespace WHERE nspname IN ('public','ag_catalog','stackgraph') \gexec
SELECT format('GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA %I TO %I',nspname,:'app_user') FROM pg_namespace WHERE nspname IN ('public','stackgraph') \gexec
SELECT format('GRANT USAGE, SELECT, UPDATE ON ALL SEQUENCES IN SCHEMA %I TO %I',nspname,:'app_user') FROM pg_namespace WHERE nspname IN ('public','stackgraph') \gexec
SELECT format('GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA %I TO %I',nspname,:'app_user') FROM pg_namespace WHERE nspname IN ('public','ag_catalog') \gexec
SQL

docker compose run --rm --no-deps -e STACKGRAPH_DATABASE_URL="${admin_url}" seed >/dev/null
docker compose run --rm --no-deps \
  -e STACKGRAPH_TEST_DATABASE_URL="${app_url}" \
  -e STACKGRAPH_TEST_ADMIN_DATABASE_URL="${admin_url}" \
  api python -m pytest -q
docker compose run --rm --no-deps -e STACKGRAPH_TEST_DATABASE_URL="${admin_url}" \
  seed python -m unittest discover -s tests -v
docker build -q -t stackgraph-enterprise-tests \
  -f services/enterprise-discovery/Dockerfile.test . >/dev/null
docker run --rm --network stackgraph_default -e STACKGRAPH_TEST_DATABASE_URL="${admin_url}" \
  stackgraph-enterprise-tests

cleanup
remaining_databases="$(docker compose exec -T database psql -At -v ON_ERROR_STOP=1 -U "${admin_user}" -d postgres \
  -c "SELECT count(*) FROM pg_database WHERE datname='${database_name}'")"
test "${remaining_databases}" = "0"
trap - EXIT
printf '{"database":"%s","status":"passed","removed":true}\n' "${database_name}"
