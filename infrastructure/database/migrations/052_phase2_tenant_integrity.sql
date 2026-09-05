-- Phase 2 tenant integrity: make cross-tenant references structurally impossible.

ALTER TABLE change_set ADD CONSTRAINT uq_change_set_id_tenant UNIQUE(id,tenant_id);
ALTER TABLE simulation_run ADD CONSTRAINT uq_simulation_run_id_tenant UNIQUE(id,tenant_id);

ALTER TABLE mutation
  ADD CONSTRAINT fk_mutation_change_set_tenant
  FOREIGN KEY(change_set_id,tenant_id) REFERENCES change_set(id,tenant_id);
ALTER TABLE simulation_run
  ADD CONSTRAINT fk_simulation_change_set_tenant
  FOREIGN KEY(change_set_id,tenant_id) REFERENCES change_set(id,tenant_id);
ALTER TABLE simulation_finding
  ADD CONSTRAINT fk_simulation_finding_run_tenant
  FOREIGN KEY(simulation_run_id,tenant_id) REFERENCES simulation_run(id,tenant_id);
ALTER TABLE simulation_interpretation
  ADD CONSTRAINT fk_simulation_interpretation_run_tenant
  FOREIGN KEY(simulation_run_id,tenant_id) REFERENCES simulation_run(id,tenant_id);
ALTER TABLE modernization_recommendation
  ADD CONSTRAINT fk_modernization_proposed_change_set_tenant
  FOREIGN KEY(proposed_change_set_id,tenant_id) REFERENCES change_set(id,tenant_id);

ALTER TABLE phase2_feature_flag FORCE ROW LEVEL SECURITY;
ALTER TABLE action_capability FORCE ROW LEVEL SECURITY;
ALTER TABLE impact_policy FORCE ROW LEVEL SECURITY;
ALTER TABLE change_set FORCE ROW LEVEL SECURITY;
ALTER TABLE mutation FORCE ROW LEVEL SECURITY;
ALTER TABLE simulation_run FORCE ROW LEVEL SECURITY;
ALTER TABLE simulation_finding FORCE ROW LEVEL SECURITY;
ALTER TABLE simulation_interpretation FORCE ROW LEVEL SECURITY;
ALTER TABLE repository_activity_aggregate FORCE ROW LEVEL SECURITY;
