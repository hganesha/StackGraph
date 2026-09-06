-- §36: generate adversarial scenarios from the real estate, and evaluate harnesses against them.
--
-- The plan is precise about what this is and what it is not. It asks StackGraph to "use the
-- estate and Change Compiler to generate adversarial scenarios", to "evaluate harnesses against
-- these scenarios", and to feed failures into the Harness Factory. It then says the champion/
-- challenger loop must "remain disabled until offline evaluation, rollback, and governance are
-- proven", and A1's exit gate repeats it.
--
-- So this migration builds the evaluation half and makes the promotion half structurally
-- impossible rather than merely switched off. There is no table a promotion could be written
-- into and no column a challenger could be marked champion in. When the governance to promote
-- safely exists, adding that is a deliberate migration somebody has to write and review — which
-- is the point.

CREATE TABLE adversarial_scenario (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES tenant(id),
  scenario_key text NOT NULL CHECK(scenario_key<>''),
  -- The eight failure modes §36 enumerates. A closed set, because a scenario class nobody named
  -- is a scenario nobody agreed was worth testing against.
  scenario_class text NOT NULL CHECK(scenario_class IN (
    'STALE_CONTEXT','CONFLICTING_DOCUMENTATION','PARTIAL_TOOL_OUTAGE','MALFORMED_API_RESPONSE',
    'UNEXPECTED_SCHEMA_CHANGE','MALICIOUS_REPOSITORY_CONTENT','CONCURRENT_AGENT_ACTIONS',
    'TOPOLOGY_DOCUMENTATION_MISMATCH'
  )),
  title text NOT NULL CHECK(title<>''),
  description text NOT NULL CHECK(description<>''),
  -- What the harness is given, and what a correct harness must do with it. Separating them is
  -- what makes an evaluation checkable rather than a matter of opinion.
  stimulus jsonb NOT NULL CHECK(jsonb_typeof(stimulus)='object'),
  expected_behaviour jsonb NOT NULL CHECK(jsonb_typeof(expected_behaviour)='object'),
  -- Scenarios are derived from real estate facts, so a failure points at something that exists.
  -- A scenario with no evidence is a hypothetical, and is recorded as such rather than being
  -- presented as a property of this estate.
  derived_from_entity_id uuid,
  evidence_fact_ids uuid[] NOT NULL DEFAULT '{}',
  severity text NOT NULL DEFAULT 'MEDIUM' CHECK(severity IN ('LOW','MEDIUM','HIGH','CRITICAL')),
  generator_version text NOT NULL CHECK(generator_version<>''),
  estate_watermark text NOT NULL CHECK(estate_watermark<>''),
  input_fingerprint text NOT NULL CHECK(input_fingerprint ~ '^sha256:[a-f0-9]{64}$'),
  created_at timestamptz NOT NULL DEFAULT now(),
  FOREIGN KEY(derived_from_entity_id,tenant_id) REFERENCES entity(id,tenant_id),
  UNIQUE(tenant_id,id),
  -- Identity is the fingerprint, not the key. `scenario_key` names the finding ("stale context
  -- on this repository") and stays stable while the finding does; the fingerprint covers the
  -- stimulus, so a re-derivation that genuinely changed what the harness is given becomes a new
  -- row rather than editing one that evaluations already point at.
  UNIQUE(tenant_id,input_fingerprint)
);

CREATE INDEX adversarial_scenario_key ON adversarial_scenario(tenant_id,scenario_key,created_at DESC);

ALTER TABLE adversarial_scenario ENABLE ROW LEVEL SECURITY;
ALTER TABLE adversarial_scenario FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON adversarial_scenario
  USING(tenant_id=stackgraph_current_tenant_id())
  WITH CHECK(tenant_id=stackgraph_current_tenant_id());

CREATE TABLE harness_evaluation (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES tenant(id),
  harness_key text NOT NULL CHECK(harness_key<>''),
  harness_version text NOT NULL CHECK(harness_version<>''),
  -- OFFLINE only. An evaluation that could run against production would be the execution
  -- surface A1 forbids until its security review passes, so the column admits one value and
  -- widening it is a migration somebody has to write.
  execution_mode text NOT NULL DEFAULT 'OFFLINE' CHECK(execution_mode='OFFLINE'),
  status text NOT NULL DEFAULT 'RUNNING'
    CHECK(status IN ('RUNNING','COMPLETED','ABANDONED')),
  -- The scenarios the evaluation set out to run, not only the ones it got around to answering.
  -- Without this an abandoned evaluation could not say what went unanswered, and silence about
  -- a scenario would be indistinguishable from never having selected it.
  selected_scenario_ids uuid[] NOT NULL CHECK(cardinality(selected_scenario_ids)>0),
  scenario_count integer NOT NULL DEFAULT 0 CHECK(scenario_count>=0),
  passed_count integer NOT NULL DEFAULT 0 CHECK(passed_count>=0),
  failed_count integer NOT NULL DEFAULT 0 CHECK(failed_count>=0),
  inconclusive_count integer NOT NULL DEFAULT 0 CHECK(inconclusive_count>=0),
  estate_watermark text NOT NULL CHECK(estate_watermark<>''),
  created_by text NOT NULL CHECK(created_by<>''),
  started_at timestamptz NOT NULL DEFAULT now(),
  completed_at timestamptz,
  UNIQUE(tenant_id,id),
  CHECK(scenario_count=cardinality(selected_scenario_ids)),
  CHECK(passed_count+failed_count+inconclusive_count<=scenario_count),
  CHECK((status='RUNNING')=(completed_at IS NULL))
);

ALTER TABLE harness_evaluation ENABLE ROW LEVEL SECURITY;
ALTER TABLE harness_evaluation FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON harness_evaluation
  USING(tenant_id=stackgraph_current_tenant_id())
  WITH CHECK(tenant_id=stackgraph_current_tenant_id());

CREATE TABLE harness_evaluation_result (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES tenant(id),
  evaluation_id uuid NOT NULL,
  scenario_id uuid NOT NULL,
  -- INCONCLUSIVE is a first-class outcome, not a rounding of PASSED. A harness that did not
  -- answer has not demonstrated safety, and counting silence as a pass is the exact failure
  -- §36 exists to catch.
  outcome text NOT NULL CHECK(outcome IN ('PASSED','FAILED','INCONCLUSIVE')),
  observed_behaviour jsonb NOT NULL DEFAULT '{}' CHECK(jsonb_typeof(observed_behaviour)='object'),
  diagnosis text,
  recorded_at timestamptz NOT NULL DEFAULT now(),
  FOREIGN KEY(evaluation_id,tenant_id) REFERENCES harness_evaluation(id,tenant_id) ON DELETE RESTRICT,
  FOREIGN KEY(scenario_id,tenant_id) REFERENCES adversarial_scenario(id,tenant_id) ON DELETE RESTRICT,
  UNIQUE(evaluation_id,scenario_id)
);

ALTER TABLE harness_evaluation_result ENABLE ROW LEVEL SECURITY;
ALTER TABLE harness_evaluation_result FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON harness_evaluation_result
  USING(tenant_id=stackgraph_current_tenant_id())
  WITH CHECK(tenant_id=stackgraph_current_tenant_id());

-- A finished evaluation is evidence and must not be edited afterwards; rerunning produces a
-- new evaluation. Without this, a failing result could be quietly turned into a passing one.
CREATE FUNCTION stackgraph_prevent_completed_evaluation_change()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF OLD.status IN ('COMPLETED','ABANDONED') THEN
    RAISE EXCEPTION 'a finished harness evaluation is immutable; run a new evaluation instead';
  END IF;
  -- COALESCE, not NEW: NEW is NULL on DELETE, and returning it from a BEFORE DELETE trigger
  -- cancels the delete without saying so. A running evaluation stays deletable.
  RETURN coalesce(NEW,OLD);
END $$;

CREATE TRIGGER trg_harness_evaluation_immutable
  BEFORE UPDATE OR DELETE ON harness_evaluation
  FOR EACH ROW EXECUTE FUNCTION stackgraph_prevent_completed_evaluation_change();

CREATE FUNCTION stackgraph_prevent_evaluation_result_change()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  RAISE EXCEPTION 'harness evaluation results are immutable';
END $$;

CREATE TRIGGER trg_harness_evaluation_result_immutable
  BEFORE UPDATE OR DELETE ON harness_evaluation_result
  FOR EACH ROW EXECUTE FUNCTION stackgraph_prevent_evaluation_result_change();

-- Generation and evaluation are off by default. §36 is a later-stage capability and this is the
-- switch that keeps it that way until somebody decides otherwise.
ALTER TABLE phase2_feature_flag DROP CONSTRAINT IF EXISTS phase2_feature_flag_flag_key_check;
ALTER TABLE phase2_feature_flag ADD CONSTRAINT phase2_feature_flag_flag_key_check
  CHECK(flag_key IN (
    'SCANNER_PROFILES','CHANGE_COMPILER','CHANGE_SIMULATION','AI_INTERPRETATION',
    'CHANGE_EXECUTION','REGISTRY_ENRICHMENT','ADVERSARIAL_EVALUATION'
  ));

INSERT INTO phase2_feature_flag(tenant_id,flag_key,enabled,updated_by) VALUES
  (NULL,'ADVERSARIAL_EVALUATION',false,'migration:059')
ON CONFLICT DO NOTHING;

COMMENT ON TABLE harness_evaluation IS
  'Offline evaluation of a harness against adversarial scenarios. There is deliberately no '
  'promotion table and no champion column: §36 and A1 both require the champion/challenger '
  'loop to stay disabled until offline evaluation, rollback, and governance are proven, and a '
  'capability that cannot be represented cannot be enabled by a configuration mistake.';
