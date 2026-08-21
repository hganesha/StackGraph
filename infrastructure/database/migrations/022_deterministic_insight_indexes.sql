-- Current-fact access paths used by deterministic impact scoping and deps.dev graph lookup.

CREATE INDEX idx_fact_object_predicate_current
  ON fact_assertion(object_entity_id,predicate)
  WHERE system_to IS NULL AND object_entity_id IS NOT NULL;

CREATE INDEX idx_fact_tenant_predicate_current
  ON fact_assertion(tenant_id,predicate,subject_entity_id)
  WHERE system_to IS NULL;

CREATE INDEX idx_fact_depsdev_graph_root_current
  ON fact_assertion((properties->>'graph_root_purl'),object_entity_id)
  WHERE system_to IS NULL AND predicate='DEPENDS_ON'
    AND properties->>'provider'='deps.dev';
