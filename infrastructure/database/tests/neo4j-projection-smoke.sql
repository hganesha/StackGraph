\set ON_ERROR_STOP on

BEGIN;

INSERT INTO tenant(id,tenant_key,name)
VALUES
  ('10000000-0000-4000-8000-000000000001','neo4j-smoke-a','Neo4j smoke A'),
  ('10000000-0000-4000-8000-000000000002','neo4j-smoke-b','Neo4j smoke B');

INSERT INTO tenant_graph_deployment(
  tenant_id,endpoint,database_name,username,credential_reference,deployment_state
) VALUES
  ('10000000-0000-4000-8000-000000000001','neo4j://smoke-a:7687','neo4j','neo4j','env://SMOKE_PASSWORD','ACTIVE'),
  ('10000000-0000-4000-8000-000000000002','neo4j://smoke-b:7687','neo4j','neo4j','env://SMOKE_PASSWORD','ACTIVE');

DO $$
DECLARE
  expected_initial bigint;
  actual_initial bigint;
BEGIN
  WITH applicable AS (
    SELECT outbox.id
    FROM projection_outbox outbox
    JOIN fact_assertion fact ON fact.id=outbox.aggregate_id
    WHERE outbox.aggregate_type='FACT'
      AND outbox.operation='UPSERT'
      AND fact.system_to IS NULL
      AND (outbox.tenant_id IS NULL
        OR outbox.tenant_id='10000000-0000-4000-8000-000000000001')
    UNION
    SELECT max(outbox.id)
    FROM projection_outbox outbox
    WHERE outbox.aggregate_type='FACT'
      AND (outbox.tenant_id IS NULL
        OR outbox.tenant_id='10000000-0000-4000-8000-000000000001')
    HAVING max(outbox.id) IS NOT NULL
  )
  SELECT count(*) INTO expected_initial FROM applicable;

  SELECT count(*) INTO actual_initial
  FROM graph_projection_delivery
  WHERE tenant_id='10000000-0000-4000-8000-000000000001';

  IF actual_initial<>expected_initial THEN
    RAISE EXCEPTION 'compact initial backfill mismatch: expected %, found %',
      expected_initial,actual_initial;
  END IF;
END
$$;

INSERT INTO projection_outbox(
  tenant_id,aggregate_type,aggregate_id,operation,dedupe_key
) VALUES (
  NULL,'FACT','20000000-0000-4000-8000-000000000001','DELETE',
  'neo4j-smoke:global'
);

INSERT INTO projection_outbox(
  tenant_id,aggregate_type,aggregate_id,operation,dedupe_key
) VALUES (
  '10000000-0000-4000-8000-000000000001','FACT',
  '20000000-0000-4000-8000-000000000002','DELETE','neo4j-smoke:tenant-a'
);

DO $$
DECLARE
  global_deliveries integer;
  tenant_deliveries integer;
BEGIN
  SELECT count(*) INTO global_deliveries
  FROM graph_projection_delivery delivery
  JOIN projection_outbox outbox ON outbox.id=delivery.outbox_id
  WHERE outbox.dedupe_key='neo4j-smoke:global'
    AND delivery.tenant_id IN (
      '10000000-0000-4000-8000-000000000001',
      '10000000-0000-4000-8000-000000000002'
    );

  SELECT count(*) INTO tenant_deliveries
  FROM graph_projection_delivery delivery
  JOIN projection_outbox outbox ON outbox.id=delivery.outbox_id
  WHERE outbox.dedupe_key='neo4j-smoke:tenant-a'
    AND delivery.tenant_id IN (
      '10000000-0000-4000-8000-000000000001',
      '10000000-0000-4000-8000-000000000002'
    );

  IF global_deliveries<>2 THEN
    RAISE EXCEPTION 'global event fanout mismatch: expected 2, found %',global_deliveries;
  END IF;
  IF tenant_deliveries<>1 THEN
    RAISE EXCEPTION 'tenant event isolation mismatch: expected 1, found %',tenant_deliveries;
  END IF;
END
$$;

DO $$
DECLARE
  tenant_a_secret uuid;
BEGIN
  INSERT INTO tenant_secret(
    tenant_id,secret_kind,ciphertext,fingerprint,created_by
  ) VALUES (
    '10000000-0000-4000-8000-000000000001','NEO4J_PASSWORD',
    decode('00','hex'),'test','neo4j-smoke'
  ) RETURNING id INTO tenant_a_secret;

  BEGIN
    UPDATE tenant_graph_deployment
    SET credential_reference=NULL,credential_secret_id=tenant_a_secret
    WHERE tenant_id='10000000-0000-4000-8000-000000000002';
    RAISE EXCEPTION 'cross-tenant Neo4j credential reference was accepted';
  EXCEPTION
    WHEN foreign_key_violation THEN NULL;
  END;
END
$$;

UPDATE tenant_graph_deployment
SET rebuild_state='RUNNING',candidate_database_name='neo4j_green',
    rebuild_started_at=now(),rebuild_started_outbox_id=desired_outbox_id,
    candidate_projected_outbox_id=projected_outbox_id
WHERE tenant_id='10000000-0000-4000-8000-000000000001';

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM tenant_graph_deployment
    WHERE tenant_id='10000000-0000-4000-8000-000000000001'
      AND rebuild_state='RUNNING' AND candidate_database_name='neo4j_green'
  ) THEN
    RAISE EXCEPTION 'blue/green rebuild state was not retained';
  END IF;
  BEGIN
    UPDATE tenant_graph_deployment
    SET rebuild_state='RUNNING',candidate_database_name=NULL,rebuild_started_at=NULL
    WHERE tenant_id='10000000-0000-4000-8000-000000000002';
    RAISE EXCEPTION 'invalid blue/green rebuild state was accepted';
  EXCEPTION WHEN check_violation THEN NULL;
  END;
END
$$;

ROLLBACK;

SELECT 'neo4j projection control-plane smoke passed' AS result;
