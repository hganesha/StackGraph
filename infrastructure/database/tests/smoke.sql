\set ON_ERROR_STOP on

DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'age') THEN
    RAISE EXCEPTION 'Apache AGE extension is not installed';
  END IF;

  IF to_regclass('public.entity') IS NULL THEN
    RAISE EXCEPTION 'StackGraph relational schema is not installed';
  END IF;

  IF NOT EXISTS (SELECT 1 FROM ag_catalog.ag_graph WHERE name = 'stackgraph') THEN
    RAISE EXCEPTION 'StackGraph AGE graph is not initialized';
  END IF;
END
$$;

SELECT
  current_database() AS database,
  current_setting('server_version') AS postgres_version,
  (SELECT extversion FROM pg_extension WHERE extname = 'age') AS age_version,
  (SELECT count(*) FROM information_schema.tables WHERE table_schema = 'public') AS public_table_count,
  (SELECT count(*) FROM ag_catalog.ag_graph WHERE name = 'stackgraph') AS graph_count;
