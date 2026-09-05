-- Phase 2B: make the deterministic simulator a first-class controllable service.

ALTER TABLE tenant_service_control
  DROP CONSTRAINT IF EXISTS tenant_service_control_service_key_check;

ALTER TABLE tenant_service_control
  ADD CONSTRAINT tenant_service_control_service_key_check CHECK(service_key IN (
    'github-webhook','github-control-loop','projection','intelligence',
    'graph-intelligence','embeddings','change-simulator','mcp'
  ));

CREATE INDEX idx_simulation_run_queue_health
  ON simulation_run(status,available_at,leased_until,created_at);

CREATE INDEX idx_simulation_run_tenant_completed
  ON simulation_run(tenant_id,completed_at DESC)
  WHERE completed_at IS NOT NULL;
