-- Tenant-scoped desired state for workspace-owned pipeline services.

CREATE TABLE IF NOT EXISTS tenant_service_control (
  tenant_id uuid NOT NULL REFERENCES tenant(id) ON DELETE CASCADE,
  service_key text NOT NULL CHECK(service_key IN (
    'github-webhook','github-control-loop','projection','intelligence'
  )),
  desired_state text NOT NULL DEFAULT 'RUNNING'
    CHECK(desired_state IN ('RUNNING','STOPPED')),
  updated_by text NOT NULL CHECK(updated_by<>''),
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY(tenant_id,service_key)
);

ALTER TABLE tenant_service_control ENABLE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON tenant_service_control
  USING(tenant_id=stackgraph_current_tenant_id())
  WITH CHECK(tenant_id=stackgraph_current_tenant_id());

-- Workers connect outside a tenant session and use this predicate in their claim queries.
-- Missing rows intentionally mean RUNNING, preserving behavior during rolling upgrades.
CREATE OR REPLACE FUNCTION stackgraph_tenant_service_running(
  requested_tenant_id uuid,
  requested_service_key text
) RETURNS boolean
LANGUAGE sql
STABLE
PARALLEL SAFE
AS $$
  SELECT requested_tenant_id IS NULL OR NOT EXISTS (
    SELECT 1
    FROM tenant_service_control control
    WHERE control.tenant_id=requested_tenant_id
      AND control.service_key=requested_service_key
      AND control.desired_state='STOPPED'
  )
$$;
