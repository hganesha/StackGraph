\set ON_ERROR_STOP on

BEGIN;

INSERT INTO tenant(id,tenant_key,name)
VALUES ('11000000-0000-4000-8000-000000000001','graph-analysis-smoke','Graph analysis smoke');

INSERT INTO tenant_graph_deployment(
  tenant_id,endpoint,database_name,username,credential_reference,deployment_state
) VALUES (
  '11000000-0000-4000-8000-000000000001','neo4j://analysis-smoke:7687',
  'neo4j','neo4j','env://SMOKE_PASSWORD','SUSPENDED'
);

DO $$
DECLARE
  policy_count integer;
  request_count integer;
BEGIN
  SELECT count(*) INTO policy_count
  FROM graph_analysis_policy WHERE status='ACTIVE';
  PERFORM stackgraph_request_graph_analysis(
    '11000000-0000-4000-8000-000000000001',10,'SMOKE_INITIAL'
  );
  SELECT count(*) INTO request_count
  FROM graph_analysis_request
  WHERE tenant_id='11000000-0000-4000-8000-000000000001';
  IF request_count<>policy_count THEN
    RAISE EXCEPTION 'expected one request per active policy: % versus %',
      request_count,policy_count;
  END IF;
END
$$;

SELECT stackgraph_request_graph_analysis(
  '11000000-0000-4000-8000-000000000001',20,'SMOKE_COALESCED'
);

DO $$
DECLARE
  bad_count integer;
BEGIN
  SELECT count(*) INTO bad_count
  FROM graph_analysis_request
  WHERE tenant_id='11000000-0000-4000-8000-000000000001'
    AND (requested_change_watermark<>20 OR status<>'WAITING_FOR_PROJECTION');
  IF bad_count<>0 THEN
    RAISE EXCEPTION 'request coalescing or projection waiting state is invalid';
  END IF;
END
$$;

UPDATE tenant_graph_deployment
SET projected_outbox_id=20
WHERE tenant_id='11000000-0000-4000-8000-000000000001';
SELECT stackgraph_request_graph_analysis(
  '11000000-0000-4000-8000-000000000001',20,'SMOKE_PROJECTION_READY'
);

DO $$
DECLARE
  bad_count integer;
BEGIN
  SELECT count(*) INTO bad_count
  FROM graph_analysis_request
  WHERE tenant_id='11000000-0000-4000-8000-000000000001'
    AND status<>'PENDING';
  IF bad_count<>0 THEN
    RAISE EXCEPTION 'projection-ready requests did not return to PENDING';
  END IF;
END
$$;

WITH selected AS (
  SELECT id FROM graph_analysis_request
  WHERE tenant_id='11000000-0000-4000-8000-000000000001'
  ORDER BY policy_key LIMIT 1
)
UPDATE graph_analysis_request
SET status='RUNNING',started_at=now(),leased_by='smoke',leased_until=now()+interval '1 minute'
WHERE id=(SELECT id FROM selected);

UPDATE tenant_graph_deployment
SET projected_outbox_id=30
WHERE tenant_id='11000000-0000-4000-8000-000000000001';
SELECT stackgraph_request_graph_analysis(
  '11000000-0000-4000-8000-000000000001',30,'SMOKE_SUCCESSOR'
);

DO $$
DECLARE
  successor_count integer;
BEGIN
  SELECT count(*) INTO successor_count
  FROM graph_analysis_request request
  WHERE tenant_id='11000000-0000-4000-8000-000000000001'
    AND EXISTS (
      SELECT 1 FROM graph_analysis_request running
      WHERE running.tenant_id=request.tenant_id
        AND running.policy_id=request.policy_id
        AND running.status='RUNNING'
    );
  IF successor_count<>2 THEN
    RAISE EXCEPTION 'expected a running request and one coalesced successor, found %',
      successor_count;
  END IF;
END
$$;

DO $$
DECLARE
  request_row graph_analysis_request%ROWTYPE;
  run_id uuid;
BEGIN
  SELECT * INTO request_row
  FROM graph_analysis_request
  WHERE tenant_id='11000000-0000-4000-8000-000000000001'
    AND status='RUNNING'
  LIMIT 1;

  INSERT INTO graph_analysis_run(
    tenant_id,policy_id,policy_key,request_id,requested_change_watermark,
    neo4j_projection_watermark,input_fingerprint,worker_id,lease_expires_at
  ) VALUES (
    request_row.tenant_id,request_row.policy_id,request_row.policy_key,request_row.id,
    request_row.requested_change_watermark,30,
    'sha256:'||repeat('a',64),'smoke',now()+interval '1 minute'
  ) RETURNING id INTO run_id;

  BEGIN
    INSERT INTO active_graph_analysis_run(tenant_id,policy_key,run_id)
    VALUES (request_row.tenant_id,request_row.policy_key,run_id);
    RAISE EXCEPTION 'active pointer accepted an incomplete run';
  EXCEPTION WHEN check_violation THEN NULL;
  END;

  UPDATE graph_analysis_run
  SET status='SUCCEEDED',stage='COMPLETE',completed_at=now()
  WHERE id=run_id;

  INSERT INTO active_graph_analysis_run(tenant_id,policy_key,run_id)
  VALUES (request_row.tenant_id,request_row.policy_key,run_id);

  BEGIN
    UPDATE graph_analysis_run SET node_count=1 WHERE id=run_id;
    RAISE EXCEPTION 'terminal run accepted a mutation';
  EXCEPTION WHEN object_not_in_prerequisite_state THEN NULL;
  END;
END
$$;

ROLLBACK;

SELECT 'graph analysis control-plane smoke passed' AS result;
