-- Phase 2 safety hardening: immutable terminal artifacts and active scanner profiles.

UPDATE phase2_feature_flag
SET enabled=true,updated_by='migration:051',updated_at=now()
WHERE tenant_id IS NULL AND flag_key='SCANNER_PROFILES';

CREATE TRIGGER trg_change_set_immutable
  BEFORE UPDATE OR DELETE ON change_set
  FOR EACH ROW EXECUTE FUNCTION stackgraph_prevent_terminal_change_mutation();

CREATE FUNCTION stackgraph_prevent_terminal_simulation_child_mutation()
RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE parent_status text;
BEGIN
  SELECT status INTO parent_status FROM simulation_run
  WHERE id=coalesce(OLD.simulation_run_id,NEW.simulation_run_id);
  IF parent_status IN ('SUCCEEDED','LIMITED','NOT_SIMULATABLE','FAILED','CANCELLED') THEN
    RAISE EXCEPTION 'terminal SimulationRun results are immutable';
  END IF;
  RETURN coalesce(NEW,OLD);
END $$;

CREATE TRIGGER trg_simulation_finding_immutable
  BEFORE INSERT OR UPDATE OR DELETE ON simulation_finding
  FOR EACH ROW EXECUTE FUNCTION stackgraph_prevent_terminal_simulation_child_mutation();

CREATE TRIGGER trg_simulation_interpretation_immutable
  BEFORE INSERT OR UPDATE OR DELETE ON simulation_interpretation
  FOR EACH ROW EXECUTE FUNCTION stackgraph_prevent_terminal_simulation_child_mutation();
