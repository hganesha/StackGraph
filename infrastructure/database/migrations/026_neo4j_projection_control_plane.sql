-- Tenant-scoped Neo4j projection control plane.
-- PostgreSQL remains authoritative; every Neo4j graph is disposable and rebuildable.

ALTER TABLE tenant_secret
  DROP CONSTRAINT tenant_secret_secret_kind_check;

ALTER TABLE tenant_secret
  ADD CONSTRAINT tenant_secret_secret_kind_check
  CHECK(secret_kind IN ('AI_PROVIDER_KEY','GITHUB_TOKEN','NEO4J_PASSWORD'));

ALTER TABLE tenant_secret
  ADD CONSTRAINT uq_tenant_secret_id_tenant UNIQUE(id,tenant_id);

CREATE TABLE tenant_graph_deployment (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES tenant(id) ON DELETE CASCADE,
  backend_kind text NOT NULL DEFAULT 'NEO4J' CHECK(backend_kind='NEO4J'),
  endpoint text NOT NULL CHECK(endpoint ~ '^neo4j(\+s|\+ssc)?://' AND endpoint !~ '@'),
  database_name text NOT NULL DEFAULT 'neo4j'
    CHECK(database_name ~ '^[A-Za-z0-9][A-Za-z0-9._-]{0,62}$'),
  username text NOT NULL CHECK(username<>''),
  credential_secret_id uuid,
  credential_reference text,
  deployment_state text NOT NULL DEFAULT 'PROVISIONING'
    CHECK(deployment_state IN ('PROVISIONING','ACTIVE','SUSPENDED','ERROR')),
  schema_version integer NOT NULL DEFAULT 1 CHECK(schema_version>0),
  desired_outbox_id bigint NOT NULL DEFAULT 0 CHECK(desired_outbox_id>=0),
  projected_outbox_id bigint NOT NULL DEFAULT 0 CHECK(projected_outbox_id>=0),
  projection_leased_by text,
  projection_leased_until timestamptz,
  last_reconciled_at timestamptz,
  last_error jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(tenant_id),
  UNIQUE(id,tenant_id),
  FOREIGN KEY(credential_secret_id,tenant_id)
    REFERENCES tenant_secret(id,tenant_id) ON DELETE RESTRICT,
  CHECK((credential_secret_id IS NOT NULL) <> (credential_reference IS NOT NULL)),
  CHECK(credential_reference IS NULL OR credential_reference ~ '^(env|vault|secret)://[A-Za-z0-9_./-]+$')
);

CREATE TABLE graph_projection_delivery (
  outbox_id bigint NOT NULL REFERENCES projection_outbox(id) ON DELETE CASCADE,
  tenant_id uuid NOT NULL REFERENCES tenant(id) ON DELETE CASCADE,
  deployment_id uuid NOT NULL,
  status text NOT NULL DEFAULT 'PENDING'
    CHECK(status IN ('PENDING','PROCESSING','PROCESSED','DEAD_LETTER')),
  available_at timestamptz NOT NULL DEFAULT now(),
  leased_by text,
  leased_until timestamptz,
  attempt integer NOT NULL DEFAULT 0 CHECK(attempt>=0),
  last_error jsonb,
  processed_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY(outbox_id,tenant_id),
  FOREIGN KEY(deployment_id,tenant_id)
    REFERENCES tenant_graph_deployment(id,tenant_id) ON DELETE CASCADE
);

CREATE INDEX idx_graph_projection_delivery_claim
  ON graph_projection_delivery(deployment_id,status,outbox_id,available_at);
CREATE INDEX idx_graph_projection_delivery_lag
  ON graph_projection_delivery(tenant_id,outbox_id)
  WHERE status<>'PROCESSED';

CREATE OR REPLACE FUNCTION stackgraph_enqueue_graph_projection_deliveries()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
  IF NEW.aggregate_type<>'FACT' THEN
    RETURN NEW;
  END IF;

  INSERT INTO graph_projection_delivery(outbox_id,tenant_id,deployment_id)
  SELECT NEW.id,deployment.tenant_id,deployment.id
  FROM tenant_graph_deployment deployment
  WHERE deployment.deployment_state='ACTIVE'
    AND (NEW.tenant_id IS NULL OR NEW.tenant_id=deployment.tenant_id)
  ON CONFLICT(outbox_id,tenant_id) DO NOTHING;

  UPDATE tenant_graph_deployment deployment
  SET desired_outbox_id=greatest(deployment.desired_outbox_id,NEW.id),
      updated_at=now()
  WHERE deployment.deployment_state='ACTIVE'
    AND (NEW.tenant_id IS NULL OR NEW.tenant_id=deployment.tenant_id);

  RETURN NEW;
END
$$;

CREATE TRIGGER projection_outbox_graph_delivery
AFTER INSERT ON projection_outbox
FOR EACH ROW EXECUTE FUNCTION stackgraph_enqueue_graph_projection_deliveries();

CREATE OR REPLACE FUNCTION stackgraph_backfill_graph_projection_deployment()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
  maximum_outbox_id bigint;
BEGIN
  IF NEW.deployment_state<>'ACTIVE'
     OR (TG_OP='UPDATE' AND OLD.deployment_state='ACTIVE') THEN
    RETURN NEW;
  END IF;

  INSERT INTO graph_projection_delivery(outbox_id,tenant_id,deployment_id)
  SELECT outbox.id,NEW.tenant_id,NEW.id
  FROM projection_outbox outbox
  WHERE outbox.aggregate_type='FACT'
    AND (outbox.tenant_id IS NULL OR outbox.tenant_id=NEW.tenant_id)
  ON CONFLICT(outbox_id,tenant_id) DO NOTHING;

  SELECT coalesce(max(outbox.id),0)
  INTO maximum_outbox_id
  FROM projection_outbox outbox
  WHERE outbox.aggregate_type='FACT'
    AND (outbox.tenant_id IS NULL OR outbox.tenant_id=NEW.tenant_id);

  UPDATE tenant_graph_deployment
  SET desired_outbox_id=greatest(desired_outbox_id,maximum_outbox_id),
      updated_at=now()
  WHERE id=NEW.id;

  RETURN NEW;
END
$$;

CREATE TRIGGER tenant_graph_deployment_backfill
AFTER INSERT OR UPDATE OF deployment_state ON tenant_graph_deployment
FOR EACH ROW EXECUTE FUNCTION stackgraph_backfill_graph_projection_deployment();

ALTER TABLE tenant_graph_deployment ENABLE ROW LEVEL SECURITY;
ALTER TABLE graph_projection_delivery ENABLE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation ON tenant_graph_deployment
  USING(tenant_id=stackgraph_current_tenant_id())
  WITH CHECK(tenant_id=stackgraph_current_tenant_id());
CREATE POLICY tenant_isolation ON graph_projection_delivery
  USING(tenant_id=stackgraph_current_tenant_id())
  WITH CHECK(tenant_id=stackgraph_current_tenant_id());
