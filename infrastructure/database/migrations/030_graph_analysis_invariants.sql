-- Cross-table invariants for graph analysis snapshots.

ALTER TABLE graph_analysis_policy
  DROP CONSTRAINT graph_analysis_policy_check,
  DROP CONSTRAINT graph_analysis_policy_check1,
  ADD CONSTRAINT graph_analysis_policy_active_timestamp
    CHECK(status<>'ACTIVE' OR activated_at IS NOT NULL),
  ADD CONSTRAINT graph_analysis_policy_retired_timestamp
    CHECK(status<>'RETIRED' OR retired_at IS NOT NULL),
  ADD CONSTRAINT graph_analysis_policy_retirement_order
    CHECK(retired_at IS NULL OR activated_at IS NOT NULL);

ALTER TABLE graph_analysis_request
  ADD CONSTRAINT uq_graph_analysis_request_run_scope
    UNIQUE(id,tenant_id,policy_id,policy_key);

ALTER TABLE graph_analysis_run
  ADD CONSTRAINT uq_graph_analysis_run_tenant UNIQUE(id,tenant_id),
  ADD CONSTRAINT graph_analysis_run_request_scope
    FOREIGN KEY(request_id,tenant_id,policy_id,policy_key)
    REFERENCES graph_analysis_request(id,tenant_id,policy_id,policy_key)
    ON DELETE RESTRICT;

ALTER TABLE graph_entity_metric
  ADD CONSTRAINT graph_entity_metric_run_tenant
    FOREIGN KEY(run_id,tenant_id)
    REFERENCES graph_analysis_run(id,tenant_id) ON DELETE CASCADE;

ALTER TABLE graph_edge_metric
  ADD CONSTRAINT graph_edge_metric_run_tenant
    FOREIGN KEY(run_id,tenant_id)
    REFERENCES graph_analysis_run(id,tenant_id) ON DELETE CASCADE;

ALTER TABLE graph_community_membership
  ADD CONSTRAINT graph_community_membership_run_tenant
    FOREIGN KEY(run_id,tenant_id)
    REFERENCES graph_analysis_run(id,tenant_id) ON DELETE CASCADE;

CREATE FUNCTION stackgraph_validate_active_graph_analysis_run()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
  run_status text;
BEGIN
  SELECT status INTO run_status
  FROM graph_analysis_run
  WHERE id=NEW.run_id
    AND tenant_id=NEW.tenant_id
    AND policy_key=NEW.policy_key;

  IF run_status IS NULL THEN
    RAISE EXCEPTION 'graph analysis run % does not match active snapshot scope',NEW.run_id
      USING ERRCODE='23503';
  END IF;
  IF run_status NOT IN ('SUCCEEDED','SUCCEEDED_WITH_LIMITATIONS') THEN
    RAISE EXCEPTION 'graph analysis run % is not a successful terminal run',NEW.run_id
      USING ERRCODE='23514';
  END IF;
  RETURN NEW;
END
$$;

CREATE TRIGGER active_graph_analysis_run_complete
BEFORE INSERT OR UPDATE ON active_graph_analysis_run
FOR EACH ROW EXECUTE FUNCTION stackgraph_validate_active_graph_analysis_run();
