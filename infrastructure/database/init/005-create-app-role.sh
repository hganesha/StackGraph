#!/usr/bin/env bash
set -Eeuo pipefail

: "${STACKGRAPH_DB_APP_USER:=stackgraph_app}"
: "${STACKGRAPH_DB_APP_PASSWORD:=stackgraph_app}"

psql \
  --username "$POSTGRES_USER" \
  --dbname "$POSTGRES_DB" \
  --set ON_ERROR_STOP=1 \
  --set app_user="$STACKGRAPH_DB_APP_USER" \
  --set app_password="$STACKGRAPH_DB_APP_PASSWORD" <<-'SQL'
SELECT format('CREATE ROLE %I LOGIN PASSWORD %L', :'app_user', :'app_password')
WHERE NOT EXISTS (
  SELECT 1 FROM pg_roles WHERE rolname = :'app_user'
) \gexec

SELECT format('ALTER ROLE %I PASSWORD %L', :'app_user', :'app_password') \gexec
SQL
