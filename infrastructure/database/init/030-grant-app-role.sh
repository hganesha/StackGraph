#!/usr/bin/env bash
set -Eeuo pipefail

: "${STACKGRAPH_DB_APP_USER:=stackgraph_app}"

psql \
  --username "$POSTGRES_USER" \
  --dbname "$POSTGRES_DB" \
  --set ON_ERROR_STOP=1 \
  --set app_user="$STACKGRAPH_DB_APP_USER" <<-'SQL'
SELECT format('GRANT CONNECT ON DATABASE %I TO %I', current_database(), :'app_user') \gexec
SELECT format('GRANT USAGE ON SCHEMA %I TO %I',nspname,:'app_user') FROM pg_namespace WHERE nspname IN ('public','ag_catalog','stackgraph') \gexec
SELECT format('GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA %I TO %I',nspname,:'app_user') FROM pg_namespace WHERE nspname IN ('public','stackgraph') \gexec
SELECT format('GRANT USAGE, SELECT, UPDATE ON ALL SEQUENCES IN SCHEMA %I TO %I',nspname,:'app_user') FROM pg_namespace WHERE nspname IN ('public','stackgraph') \gexec
SELECT format('GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA %I TO %I',nspname,:'app_user') FROM pg_namespace WHERE nspname IN ('public','ag_catalog') \gexec
SELECT format('ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO %I', :'app_user') \gexec
SELECT format('ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT USAGE, SELECT, UPDATE ON SEQUENCES TO %I', :'app_user') \gexec
SQL
