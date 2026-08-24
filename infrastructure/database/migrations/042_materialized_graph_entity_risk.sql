-- Immutable, indexed risk scores attached to a graph-analysis snapshot.

CREATE TABLE graph_entity_risk (
  run_id uuid NOT NULL REFERENCES graph_analysis_run(id) ON DELETE CASCADE,
  tenant_id uuid NOT NULL REFERENCES tenant(id) ON DELETE CASCADE,
  entity_id uuid NOT NULL,
  systemic_risk double precision NOT NULL CHECK(systemic_risk BETWEEN 0 AND 1),
  contributions jsonb NOT NULL DEFAULT '{}' CHECK(jsonb_typeof(contributions)='object'),
  renormalized_families text[] NOT NULL DEFAULT '{}',
  method_version text NOT NULL DEFAULT 'graph-systemic-risk/v2' CHECK(method_version<>''),
  created_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY(run_id,entity_id),
  FOREIGN KEY(entity_id) REFERENCES entity(id) ON DELETE CASCADE
);

CREATE TRIGGER graph_entity_risk_visible_entity
BEFORE INSERT OR UPDATE OF tenant_id,entity_id ON graph_entity_risk
FOR EACH ROW EXECUTE FUNCTION stackgraph_validate_visible_entity_reference('entity_id');

CREATE INDEX idx_graph_entity_risk_ranking
  ON graph_entity_risk(tenant_id,run_id,systemic_risk DESC,entity_id);
CREATE INDEX idx_graph_entity_risk_entity
  ON graph_entity_risk(tenant_id,entity_id,run_id);

ALTER TABLE graph_entity_risk ENABLE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON graph_entity_risk
  USING(tenant_id=stackgraph_current_tenant_id())
  WITH CHECK(tenant_id=stackgraph_current_tenant_id());

-- Generalize the existing governed candidate/feedback history without discarding it.
ALTER TABLE application_similarity_candidate
  RENAME COLUMN left_application_id TO left_entity_id;
ALTER TABLE application_similarity_candidate
  RENAME COLUMN right_application_id TO right_entity_id;
ALTER TABLE application_similarity_candidate
  ADD COLUMN entity_kind text NOT NULL DEFAULT 'Application' CHECK(entity_kind IN (
    'Application','Technology','BusinessCapability'
  ));

ALTER TABLE application_similarity_candidate
  DROP CONSTRAINT application_similarity_candidate_check;
ALTER TABLE application_similarity_candidate
  ADD CONSTRAINT application_similarity_candidate_ordered_pair CHECK(left_entity_id<right_entity_id);

ALTER TABLE application_similarity_feedback
  DROP CONSTRAINT application_similarity_feedback_decision_check;
ALTER TABLE application_similarity_feedback
  ADD CONSTRAINT application_similarity_feedback_decision_check CHECK(decision IN (
    'CONFIRMED_SIMILAR','CONFIRMED_DISTINCT','CONSOLIDATION_CANDIDATE','DISMISSED','REOPENED'
  ));
