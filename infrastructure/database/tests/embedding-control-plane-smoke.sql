\set ON_ERROR_STOP on

BEGIN;

INSERT INTO tenant(id,tenant_key,name) VALUES
  ('10000000-0000-4000-8000-000000000001','embedding-smoke-a','Embedding Smoke A'),
  ('20000000-0000-4000-8000-000000000001','embedding-smoke-b','Embedding Smoke B');

INSERT INTO entity(id,tenant_id,namespace,entity_type,canonical_key,name) VALUES
  ('10000000-0000-4000-8000-000000000010','10000000-0000-4000-8000-000000000001','ENTERPRISE','Application','application:billing','Billing'),
  ('10000000-0000-4000-8000-000000000011','10000000-0000-4000-8000-000000000001','ENTERPRISE','Application','application:ledger','Ledger'),
  ('20000000-0000-4000-8000-000000000010','20000000-0000-4000-8000-000000000001','ENTERPRISE','Application','application:private','Private');
INSERT INTO entity(id,tenant_id,namespace,entity_type,canonical_key,name) VALUES
  ('30000000-0000-4000-8000-000000000010',NULL,'TECHNOLOGY','Technology','technology:global-smoke','Global Smoke Technology');

INSERT INTO embedding_space(
  id,tenant_id,space_key,space_kind,provider,model_or_algorithm,dimensions,
  normalization,template_version,content_hash,coverage_ratio,evaluation
) VALUES
  ('10000000-0000-4000-8000-000000000020','10000000-0000-4000-8000-000000000001','semantic-v1','SEMANTIC_ENTITY','LOCAL','smoke-v1',8,'L2','entity/v1','sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',0.5,'{"passed":false}'),
  ('10000000-0000-4000-8000-000000000021','10000000-0000-4000-8000-000000000001','semantic-v2','SEMANTIC_ENTITY','LOCAL','smoke-v2',8,'L2','entity/v1','sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb',1,'{"passed":true}'),
  ('20000000-0000-4000-8000-000000000020','20000000-0000-4000-8000-000000000001','semantic-private','SEMANTIC_ENTITY','LOCAL','smoke-private',8,'L2','entity/v1','sha256:cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc',1,'{"passed":true}');

DO $$
BEGIN
  BEGIN
    INSERT INTO active_embedding_space(tenant_id,space_kind,embedding_space_id,activated_by)
    VALUES('10000000-0000-4000-8000-000000000001','SEMANTIC_ENTITY','10000000-0000-4000-8000-000000000020','smoke');
    RAISE EXCEPTION 'coverage/evaluation gate accepted an unqualified space';
  EXCEPTION WHEN raise_exception THEN
    IF SQLERRM='coverage/evaluation gate accepted an unqualified space' THEN RAISE; END IF;
  END;
END $$;

INSERT INTO entity_embedding(
  tenant_id,embedding_space_id,entity_id,dimensions,input_hash,embedding
) VALUES(
  '10000000-0000-4000-8000-000000000001','10000000-0000-4000-8000-000000000021',
  '30000000-0000-4000-8000-000000000010',8,
  'sha256:eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee',
  '[1,0,0,0,0,0,0,0]'::vector
);

DO $$
BEGIN
  BEGIN
    INSERT INTO entity_embedding(
      tenant_id,embedding_space_id,entity_id,dimensions,input_hash,embedding
    ) VALUES(
      '10000000-0000-4000-8000-000000000001','10000000-0000-4000-8000-000000000021',
      '20000000-0000-4000-8000-000000000010',8,
      'sha256:ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff',
      '[1,0,0,0,0,0,0,0]'::vector
    );
    RAISE EXCEPTION 'cross-tenant derived entity reference was accepted';
  EXCEPTION WHEN check_violation THEN NULL;
  END;
END $$;

UPDATE embedding_space
SET coverage_ratio=1,evaluation='{"passed":true}'
WHERE id='10000000-0000-4000-8000-000000000020';
INSERT INTO active_embedding_space(tenant_id,space_kind,embedding_space_id,activated_by)
VALUES('10000000-0000-4000-8000-000000000001','SEMANTIC_ENTITY','10000000-0000-4000-8000-000000000020','smoke');
UPDATE active_embedding_space
SET embedding_space_id='10000000-0000-4000-8000-000000000021',activated_by='smoke-swap',activated_at=now()
WHERE tenant_id='10000000-0000-4000-8000-000000000001' AND space_kind='SEMANTIC_ENTITY';

UPDATE entity SET properties='{"catalog_revision":"smoke-v2"}'
WHERE id='30000000-0000-4000-8000-000000000010';
DO $$
BEGIN
  IF (SELECT count(*) FROM embedding_job
      WHERE subject_id='30000000-0000-4000-8000-000000000010')<>2 THEN
    RAISE EXCEPTION 'global technology embedding changes did not fan out to every eligible tenant space';
  END IF;
END $$;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM embedding_space
    WHERE id='10000000-0000-4000-8000-000000000020' AND lifecycle_state='RETIRED'
  ) OR NOT EXISTS (
    SELECT 1 FROM embedding_space
    WHERE id='10000000-0000-4000-8000-000000000021' AND lifecycle_state='ACTIVE'
  ) THEN RAISE EXCEPTION 'active-space swap was not atomic'; END IF;

  BEGIN
    INSERT INTO entity_embedding(
      tenant_id,embedding_space_id,entity_id,dimensions,input_hash,embedding
    ) VALUES(
      '10000000-0000-4000-8000-000000000001','10000000-0000-4000-8000-000000000021',
      '10000000-0000-4000-8000-000000000010',8,
      'sha256:dddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd','[1,2,3]'::vector
    );
    RAISE EXCEPTION 'dimension mismatch was accepted';
  EXCEPTION WHEN check_violation THEN NULL;
  END;
END $$;

INSERT INTO embedding_relevance_case(
  id,tenant_id,case_key,query_text,relevant_entity_ids,hard_negative_entity_ids,created_by
) VALUES(
  '10000000-0000-4000-8000-000000000040','10000000-0000-4000-8000-000000000001',
  'billing-query','billing invoices',ARRAY['10000000-0000-4000-8000-000000000010'::uuid],
  ARRAY['10000000-0000-4000-8000-000000000011'::uuid],'smoke'
);

DO $$
BEGIN
  IF (SELECT coalesce((evaluation->>'passed')::boolean,true)
      FROM embedding_space WHERE id='10000000-0000-4000-8000-000000000021') THEN
    RAISE EXCEPTION 'relevance corpus change did not invalidate the active semantic space';
  END IF;
  BEGIN
    DELETE FROM embedding_relevance_case
    WHERE id='10000000-0000-4000-8000-000000000040';
    RAISE EXCEPTION 'relevance corpus case was deleted';
  EXCEPTION WHEN raise_exception THEN
    IF SQLERRM='relevance corpus case was deleted' THEN RAISE; END IF;
  END;
END $$;

INSERT INTO application_similarity_candidate(
  id,tenant_id,left_application_id,right_application_id,score,method_version,
  components,overlap_features,differences,coverage
) VALUES(
  '10000000-0000-4000-8000-000000000030','10000000-0000-4000-8000-000000000001',
  '10000000-0000-4000-8000-000000000010','10000000-0000-4000-8000-000000000011',
  0.8,'smoke-v1','{}','{}','{}','{}'
);
INSERT INTO application_similarity_feedback(
  id,tenant_id,candidate_id,decision,reason_code,candidate_method_version,candidate_score,actor_key
) VALUES(
  '10000000-0000-4000-8000-000000000031','10000000-0000-4000-8000-000000000001',
  '10000000-0000-4000-8000-000000000030','CONFIRMED_SIMILAR','smoke','smoke-v1',0.8,'smoke'
);

DO $$
BEGIN
  BEGIN
    UPDATE application_similarity_feedback SET rationale='tampered'
    WHERE id='10000000-0000-4000-8000-000000000031';
    RAISE EXCEPTION 'append-only feedback was mutable';
  EXCEPTION WHEN raise_exception THEN
    IF SQLERRM='append-only feedback was mutable' THEN RAISE; END IF;
  END;
END $$;

CREATE ROLE embedding_smoke_reader NOLOGIN;
GRANT USAGE ON SCHEMA public TO embedding_smoke_reader;
GRANT SELECT ON embedding_space TO embedding_smoke_reader;
SET LOCAL ROLE embedding_smoke_reader;
SELECT set_config('app.tenant_id','10000000-0000-4000-8000-000000000001',true);
DO $$
BEGIN
  IF (SELECT count(*) FROM embedding_space)<>2 THEN
    RAISE EXCEPTION 'tenant RLS leaked or hid an embedding space';
  END IF;
END $$;
RESET ROLE;

ROLLBACK;
