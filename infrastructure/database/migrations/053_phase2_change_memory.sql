-- Phase 2D: immutable observed outcomes used as organization-specific change memory.

CREATE TABLE observed_mutation (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES tenant(id),
  correlation_key text NOT NULL CHECK(correlation_key<>''),
  source_kind text NOT NULL CHECK(source_kind IN (
    'PULL_REQUEST','COMMIT','DEPLOYMENT','TICKET','INCIDENT','POSTMORTEM','MANUAL'
  )),
  predicate text NOT NULL CHECK(predicate IN ('UPGRADE','REPLACE','REMOVE','DEPRECATE','MIGRATE','MOVE')),
  subject_entity_id uuid NOT NULL REFERENCES entity(id),
  before_state jsonb NOT NULL CHECK(jsonb_typeof(before_state)='object'),
  after_state jsonb NOT NULL CHECK(jsonb_typeof(after_state)='object'),
  scope jsonb NOT NULL CHECK(jsonb_typeof(scope)='object'),
  observed_impact jsonb NOT NULL CHECK(jsonb_typeof(observed_impact)='object'),
  unexpected_impact jsonb NOT NULL DEFAULT '{}' CHECK(jsonb_typeof(unexpected_impact)='object'),
  success boolean,
  intervention_required boolean NOT NULL DEFAULT false,
  rolled_back boolean NOT NULL DEFAULT false,
  evidence_fact_ids uuid[] NOT NULL CHECK(cardinality(evidence_fact_ids)>0),
  graph_watermark_before text,
  predicted_simulation_run_id uuid,
  resolution text,
  confidence numeric(5,4) NOT NULL CHECK(confidence BETWEEN 0 AND 1),
  input_fingerprint text NOT NULL CHECK(input_fingerprint ~ '^sha256:[a-f0-9]{64}$'),
  observed_at timestamptz NOT NULL,
  created_by text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(tenant_id,correlation_key),
  UNIQUE(tenant_id,input_fingerprint),
  FOREIGN KEY(predicted_simulation_run_id,tenant_id)
    REFERENCES simulation_run(id,tenant_id)
);
CREATE INDEX idx_observed_mutation_similarity
  ON observed_mutation(tenant_id,predicate,subject_entity_id,observed_at DESC);
ALTER TABLE observed_mutation ENABLE ROW LEVEL SECURITY;
ALTER TABLE observed_mutation FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON observed_mutation
  USING(tenant_id=stackgraph_current_tenant_id())
  WITH CHECK(tenant_id=stackgraph_current_tenant_id());

CREATE FUNCTION stackgraph_prevent_observed_mutation_change()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  RAISE EXCEPTION 'ObservedMutation history is immutable';
END $$;
CREATE TRIGGER trg_observed_mutation_immutable
  BEFORE UPDATE OR DELETE ON observed_mutation
  FOR EACH ROW EXECUTE FUNCTION stackgraph_prevent_observed_mutation_change();
