-- Observable blue/green rebuild state. The candidate database is disposable;
-- PostgreSQL remains authoritative and the active database_name pointer changes
-- only after UUID inventory parity is proven at a recorded outbox watermark.
ALTER TABLE tenant_graph_deployment
  ADD COLUMN rebuild_state text NOT NULL DEFAULT 'IDLE'
    CHECK(rebuild_state IN ('IDLE','RUNNING','FAILED')),
  ADD COLUMN candidate_database_name text
    CHECK(candidate_database_name IS NULL OR candidate_database_name ~ '^[A-Za-z0-9][A-Za-z0-9._-]{0,62}$'),
  ADD COLUMN prior_database_name text
    CHECK(prior_database_name IS NULL OR prior_database_name ~ '^[A-Za-z0-9][A-Za-z0-9._-]{0,62}$'),
  ADD COLUMN rebuild_started_outbox_id bigint CHECK(rebuild_started_outbox_id>=0),
  ADD COLUMN candidate_projected_outbox_id bigint CHECK(candidate_projected_outbox_id>=0),
  ADD COLUMN rebuild_started_at timestamptz,
  ADD COLUMN last_rebuild_at timestamptz,
  ADD COLUMN rebuild_metadata jsonb NOT NULL DEFAULT '{}' CHECK(jsonb_typeof(rebuild_metadata)='object'),
  ADD CONSTRAINT tenant_graph_deployment_rebuild_state_shape CHECK(
    (rebuild_state='RUNNING' AND candidate_database_name IS NOT NULL AND rebuild_started_at IS NOT NULL)
    OR rebuild_state IN ('IDLE','FAILED')
  );
