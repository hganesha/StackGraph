-- Phase 2D foundations: richer change events, actor taxonomy, and recomputable windows.

ALTER TABLE repository_activity_event
  DROP CONSTRAINT IF EXISTS repository_activity_event_event_type_check;
ALTER TABLE repository_activity_event
  ADD CONSTRAINT repository_activity_event_event_type_check CHECK(event_type IN (
    'COMMIT','PULL_REQUEST_OPENED','PULL_REQUEST_MERGED','RELEASE','DEPLOYMENT',
    'DEPENDENCY_CHANGE','ARCHITECTURE_CHANGE','INCIDENT','INTERVENTION','ROLLBACK'
  ));

ALTER TABLE repository_activity_event
  ADD COLUMN actor_classification text NOT NULL DEFAULT 'UNKNOWN' CHECK(actor_classification IN (
    'HUMAN','BOT','DEPENDENCY_BOT','CI_AUTOMATION','AI_AGENT','AI_ASSISTED_HUMAN','UNKNOWN'
  )),
  ADD COLUMN actor_classification_confidence numeric(5,4) NOT NULL DEFAULT 0
    CHECK(actor_classification_confidence BETWEEN 0 AND 1),
  ADD COLUMN actor_classification_basis text,
  ADD COLUMN retention_class text NOT NULL DEFAULT 'BOUNDED_ACTIVITY_120D'
    CHECK(retention_class IN ('BOUNDED_ACTIVITY_120D','GOVERNANCE_EVENT','SECURITY_EVENT'));

ALTER TABLE repository_activity_collection
  ADD COLUMN releases_status text NOT NULL DEFAULT 'NOT_COLLECTED' CHECK(releases_status IN (
    'AVAILABLE','PARTIAL','NOT_COLLECTED','PERMISSION_REQUIRED','ERROR'
  )),
  ADD COLUMN deployments_status text NOT NULL DEFAULT 'NOT_COLLECTED' CHECK(deployments_status IN (
    'AVAILABLE','PARTIAL','NOT_COLLECTED','PERMISSION_REQUIRED','ERROR'
  ));

CREATE TABLE repository_activity_aggregate (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES tenant(id),
  repository_entity_id uuid NOT NULL REFERENCES entity(id) ON DELETE CASCADE,
  window_key text NOT NULL CHECK(window_key IN ('7d','30d','90d')),
  window_started_at timestamptz NOT NULL,
  window_ended_at timestamptz NOT NULL,
  metrics_version text NOT NULL DEFAULT 'repository-activity/1.0.0',
  metrics jsonb NOT NULL CHECK(jsonb_typeof(metrics)='object'),
  coverage jsonb NOT NULL CHECK(jsonb_typeof(coverage)='object'),
  limitations jsonb NOT NULL DEFAULT '[]' CHECK(jsonb_typeof(limitations)='array'),
  input_fingerprint text NOT NULL CHECK(input_fingerprint ~ '^sha256:[a-f0-9]{64}$'),
  computed_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(tenant_id,repository_entity_id,window_key,window_ended_at)
);
CREATE INDEX idx_repository_activity_aggregate_history
  ON repository_activity_aggregate(tenant_id,repository_entity_id,window_key,window_ended_at DESC);
ALTER TABLE repository_activity_aggregate ENABLE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON repository_activity_aggregate
  USING(tenant_id=stackgraph_current_tenant_id())
  WITH CHECK(tenant_id=stackgraph_current_tenant_id());
