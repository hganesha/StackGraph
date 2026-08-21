-- Durable many-to-many links between business capabilities and estate applications.

CREATE TABLE business_map_application_assignment (
  tenant_id uuid NOT NULL REFERENCES tenant(id),
  business_map_id uuid NOT NULL REFERENCES business_map(id) ON DELETE CASCADE,
  business_map_capability_id uuid NOT NULL
    REFERENCES business_map_capability(id) ON DELETE CASCADE,
  application_entity_id uuid NOT NULL REFERENCES entity(id) ON DELETE CASCADE,
  created_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY(business_map_id,business_map_capability_id,application_entity_id)
);

CREATE INDEX idx_business_map_application_assignment_capability
  ON business_map_application_assignment(tenant_id,business_map_capability_id);
CREATE INDEX idx_business_map_application_assignment_application
  ON business_map_application_assignment(tenant_id,application_entity_id);

ALTER TABLE business_map_application_assignment ENABLE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON business_map_application_assignment
  USING(tenant_id=stackgraph_current_tenant_id())
  WITH CHECK(tenant_id=stackgraph_current_tenant_id());
