-- Phase 2 evidence integrity: keep compact API arrays while enforcing relational citations.

ALTER TABLE fact_assertion
  ADD CONSTRAINT uq_fact_assertion_id_tenant UNIQUE(id,tenant_id);
ALTER TABLE simulation_finding
  ADD CONSTRAINT uq_simulation_finding_id_tenant UNIQUE(id,tenant_id);
ALTER TABLE observed_mutation
  ADD CONSTRAINT uq_observed_mutation_id_tenant UNIQUE(id,tenant_id);

CREATE TABLE simulation_finding_evidence (
  tenant_id uuid NOT NULL REFERENCES tenant(id),
  simulation_finding_id uuid NOT NULL,
  fact_assertion_id uuid NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY(simulation_finding_id,fact_assertion_id),
  FOREIGN KEY(simulation_finding_id,tenant_id)
    REFERENCES simulation_finding(id,tenant_id) ON DELETE RESTRICT,
  FOREIGN KEY(fact_assertion_id,tenant_id)
    REFERENCES fact_assertion(id,tenant_id) ON DELETE RESTRICT
);

CREATE TABLE observed_mutation_evidence (
  tenant_id uuid NOT NULL REFERENCES tenant(id),
  observed_mutation_id uuid NOT NULL,
  fact_assertion_id uuid NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY(observed_mutation_id,fact_assertion_id),
  FOREIGN KEY(observed_mutation_id,tenant_id)
    REFERENCES observed_mutation(id,tenant_id) ON DELETE RESTRICT,
  FOREIGN KEY(fact_assertion_id,tenant_id)
    REFERENCES fact_assertion(id,tenant_id) ON DELETE RESTRICT
);

INSERT INTO simulation_finding_evidence(
  tenant_id,simulation_finding_id,fact_assertion_id
)
SELECT finding.tenant_id,finding.id,evidence_id
FROM simulation_finding finding
CROSS JOIN LATERAL unnest(finding.evidence_fact_ids) evidence_id;

INSERT INTO observed_mutation_evidence(
  tenant_id,observed_mutation_id,fact_assertion_id
)
SELECT outcome.tenant_id,outcome.id,evidence_id
FROM observed_mutation outcome
CROSS JOIN LATERAL unnest(outcome.evidence_fact_ids) evidence_id;

CREATE FUNCTION stackgraph_sync_simulation_finding_evidence()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  DELETE FROM simulation_finding_evidence WHERE simulation_finding_id=NEW.id;
  INSERT INTO simulation_finding_evidence(
    tenant_id,simulation_finding_id,fact_assertion_id
  )
  SELECT NEW.tenant_id,NEW.id,evidence_id
  FROM unnest(NEW.evidence_fact_ids) evidence_id;
  RETURN NEW;
END $$;

CREATE TRIGGER trg_sync_simulation_finding_evidence
  AFTER INSERT OR UPDATE OF evidence_fact_ids ON simulation_finding
  FOR EACH ROW EXECUTE FUNCTION stackgraph_sync_simulation_finding_evidence();

CREATE FUNCTION stackgraph_sync_observed_mutation_evidence()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  INSERT INTO observed_mutation_evidence(
    tenant_id,observed_mutation_id,fact_assertion_id
  )
  SELECT NEW.tenant_id,NEW.id,evidence_id
  FROM unnest(NEW.evidence_fact_ids) evidence_id;
  RETURN NEW;
END $$;

CREATE TRIGGER trg_sync_observed_mutation_evidence
  AFTER INSERT ON observed_mutation
  FOR EACH ROW EXECUTE FUNCTION stackgraph_sync_observed_mutation_evidence();

ALTER TABLE simulation_finding_evidence ENABLE ROW LEVEL SECURITY;
ALTER TABLE simulation_finding_evidence FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON simulation_finding_evidence
  USING(tenant_id=stackgraph_current_tenant_id())
  WITH CHECK(tenant_id=stackgraph_current_tenant_id());

ALTER TABLE observed_mutation_evidence ENABLE ROW LEVEL SECURITY;
ALTER TABLE observed_mutation_evidence FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON observed_mutation_evidence
  USING(tenant_id=stackgraph_current_tenant_id())
  WITH CHECK(tenant_id=stackgraph_current_tenant_id());

CREATE FUNCTION stackgraph_prevent_terminal_simulation_evidence_mutation()
RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE parent_status text;
BEGIN
  SELECT run.status INTO parent_status
  FROM simulation_finding finding
  JOIN simulation_run run ON run.id=finding.simulation_run_id
  WHERE finding.id=coalesce(OLD.simulation_finding_id,NEW.simulation_finding_id);
  IF parent_status IN ('SUCCEEDED','LIMITED','NOT_SIMULATABLE','FAILED','CANCELLED') THEN
    RAISE EXCEPTION 'terminal SimulationRun evidence is immutable';
  END IF;
  RETURN coalesce(NEW,OLD);
END $$;

CREATE TRIGGER trg_simulation_finding_evidence_immutable
  BEFORE UPDATE OR DELETE ON simulation_finding_evidence
  FOR EACH ROW EXECUTE FUNCTION stackgraph_prevent_terminal_simulation_evidence_mutation();

CREATE FUNCTION stackgraph_prevent_observed_mutation_evidence_change()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  RAISE EXCEPTION 'ObservedMutation evidence is immutable';
END $$;

CREATE TRIGGER trg_observed_mutation_evidence_immutable
  BEFORE UPDATE OR DELETE ON observed_mutation_evidence
  FOR EACH ROW EXECUTE FUNCTION stackgraph_prevent_observed_mutation_evidence_change();
