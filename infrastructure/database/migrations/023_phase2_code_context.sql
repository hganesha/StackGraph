-- Phase 2 stays inside StackGraph's code boundary. Business impact is curated on
-- the built-in capability map; environment and exposure context is declared by
-- repository and infrastructure-as-code facts. Live deployment observation is a
-- future enrichment and is deliberately not represented here.

ALTER TABLE business_map_capability
  ADD COLUMN criticality smallint NOT NULL DEFAULT 3
  CHECK (criticality BETWEEN 1 AND 5);

CREATE INDEX idx_business_map_capability_criticality
  ON business_map_capability(tenant_id,criticality,business_map_id);

CREATE OR REPLACE VIEW current_capability_application_relationship
WITH (security_invoker=true) AS
SELECT assignment.tenant_id,capability.entity_id capability_entity_id,
 assignment.application_entity_id,assignment.business_map_id,
 revision.id evidence_revision_id,'CURATED'::text assertion_class,1.0::numeric(5,4) confidence,
 'sha256:'||encode(digest(convert_to(assignment.tenant_id::text||chr(31)||capability.entity_id::text||chr(31)||assignment.application_entity_id::text||chr(31)||capability.criticality::text||chr(31)||revision.id::text,'UTF8'),'sha256'),'hex') analysis_fingerprint,
 revision.created_at observed_at,capability.criticality
FROM business_map_application_assignment assignment
JOIN business_map_capability capability ON capability.id=assignment.business_map_capability_id
JOIN LATERAL (
 SELECT value.id,value.created_at FROM business_map_revision value
 WHERE value.business_map_id=assignment.business_map_id
 ORDER BY value.version DESC LIMIT 1
) revision ON true
WHERE capability.entity_id IS NOT NULL;
