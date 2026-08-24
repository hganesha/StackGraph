CREATE EXTENSION IF NOT EXISTS vector;

ALTER TABLE tenant_secret DROP CONSTRAINT tenant_secret_secret_kind_check;
ALTER TABLE tenant_secret ADD CONSTRAINT tenant_secret_secret_kind_check
  CHECK(secret_kind IN ('AI_PROVIDER_KEY','EMBEDDING_PROVIDER_KEY','GITHUB_TOKEN','NEO4J_PASSWORD'));
ALTER TABLE entity ADD CONSTRAINT uq_entity_id_tenant UNIQUE(id,tenant_id);
ALTER TABLE tenant_service_control
  DROP CONSTRAINT tenant_service_control_service_key_check;
ALTER TABLE tenant_service_control
  ADD CONSTRAINT tenant_service_control_service_key_check
  CHECK(service_key IN (
    'github-webhook','github-control-loop','projection','intelligence','graph-intelligence','embeddings'
  ));

CREATE TABLE tenant_embedding_policy (
  tenant_id uuid PRIMARY KEY REFERENCES tenant(id) ON DELETE CASCADE,
  enabled boolean NOT NULL DEFAULT true,
  provider text NOT NULL DEFAULT 'LOCAL' CHECK (provider IN ('LOCAL','OPENAI_COMPATIBLE')),
  provider_base_url text,
  credential_secret_id uuid REFERENCES tenant_secret(id) ON DELETE SET NULL,
  model text NOT NULL DEFAULT 'stackgraph-hash-embedding-v1' CHECK (model<>''),
  dimensions integer NOT NULL DEFAULT 384 CHECK (dimensions BETWEEN 8 AND 4096),
  normalization text NOT NULL DEFAULT 'L2' CHECK (normalization IN ('L2','NONE')),
  external_processing_allowed boolean NOT NULL DEFAULT false,
  sensitive_content_allowed boolean NOT NULL DEFAULT false,
  max_concurrency integer NOT NULL DEFAULT 2 CHECK (max_concurrency BETWEEN 1 AND 32),
  requests_per_minute integer NOT NULL DEFAULT 60 CHECK (requests_per_minute BETWEEN 1 AND 10000),
  retry_horizon interval NOT NULL DEFAULT interval '24 hours' CHECK (retry_horizon>interval '0'),
  description_generation_allowed boolean NOT NULL DEFAULT false,
  updated_by text NOT NULL DEFAULT 'system' CHECK (updated_by<>''),
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE embedding_space (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES tenant(id) ON DELETE CASCADE,
  space_key text NOT NULL CHECK (space_key ~ '^[a-z][a-z0-9._-]{2,127}$'),
  space_kind text NOT NULL CHECK (space_kind IN ('SEMANTIC_ENTITY','STRUCTURAL_GRAPH','CODE')),
  provider text NOT NULL CHECK (provider<>''),
  model_or_algorithm text NOT NULL CHECK (model_or_algorithm<>''),
  dimensions integer NOT NULL CHECK (dimensions BETWEEN 8 AND 4096),
  normalization text NOT NULL CHECK (normalization IN ('L2','NONE')),
  template_version text NOT NULL CHECK (template_version<>''),
  configuration jsonb NOT NULL DEFAULT '{}' CHECK (jsonb_typeof(configuration)='object'),
  content_hash text NOT NULL CHECK (content_hash ~ '^sha256:[a-f0-9]{64}$'),
  lifecycle_state text NOT NULL DEFAULT 'SHADOW'
    CHECK (lifecycle_state IN ('SHADOW','ACTIVE','RETIRED','FAILED')),
  evaluation jsonb NOT NULL DEFAULT '{}' CHECK (jsonb_typeof(evaluation)='object'),
  coverage_ratio double precision NOT NULL DEFAULT 0 CHECK (coverage_ratio BETWEEN 0 AND 1),
  last_error text,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(tenant_id,space_key),
  UNIQUE(id,tenant_id),
  UNIQUE(id,tenant_id,dimensions)
);

CREATE TABLE active_embedding_space (
  tenant_id uuid NOT NULL REFERENCES tenant(id) ON DELETE CASCADE,
  space_kind text NOT NULL CHECK (space_kind IN ('SEMANTIC_ENTITY','STRUCTURAL_GRAPH','CODE')),
  embedding_space_id uuid NOT NULL,
  activated_at timestamptz NOT NULL DEFAULT now(),
  activated_by text NOT NULL DEFAULT 'system' CHECK (activated_by<>''),
  PRIMARY KEY(tenant_id,space_kind),
  FOREIGN KEY(embedding_space_id,tenant_id)
    REFERENCES embedding_space(id,tenant_id) ON DELETE RESTRICT
);

CREATE OR REPLACE FUNCTION stackgraph_validate_active_embedding_space()
RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE candidate embedding_space%ROWTYPE;
BEGIN
  SELECT * INTO candidate FROM embedding_space WHERE id=NEW.embedding_space_id FOR SHARE;
  IF candidate.id IS NULL OR candidate.tenant_id<>NEW.tenant_id OR candidate.space_kind<>NEW.space_kind THEN
    RAISE EXCEPTION 'active embedding space must match tenant and space kind';
  END IF;
  IF candidate.lifecycle_state NOT IN ('SHADOW','ACTIVE') THEN
    RAISE EXCEPTION 'active embedding space must be a successful shadow or active space';
  END IF;
  IF candidate.coverage_ratio<0.95 OR coalesce((candidate.evaluation->>'passed')::boolean,false) IS NOT TRUE THEN
    RAISE EXCEPTION 'active embedding space must pass coverage and evaluation gates';
  END IF;
  UPDATE embedding_space SET lifecycle_state='RETIRED',updated_at=now()
   WHERE tenant_id=NEW.tenant_id AND space_kind=NEW.space_kind
     AND lifecycle_state='ACTIVE' AND id<>NEW.embedding_space_id;
  UPDATE embedding_space SET lifecycle_state='ACTIVE',updated_at=now()
   WHERE id=NEW.embedding_space_id;
  RETURN NEW;
END $$;

CREATE TRIGGER active_embedding_space_validate
BEFORE INSERT OR UPDATE ON active_embedding_space
FOR EACH ROW EXECUTE FUNCTION stackgraph_validate_active_embedding_space();

CREATE TABLE embedding_document (
  tenant_id uuid NOT NULL REFERENCES tenant(id) ON DELETE CASCADE,
  embedding_space_id uuid NOT NULL,
  entity_id uuid NOT NULL,
  entity_type text NOT NULL CHECK (entity_type<>''),
  template_version text NOT NULL CHECK (template_version<>''),
  rendered_content text NOT NULL CHECK (rendered_content<>''),
  input_hash text NOT NULL CHECK (input_hash ~ '^sha256:[a-f0-9]{64}$'),
  source_fact_ids uuid[] NOT NULL DEFAULT '{}',
  sensitivity text NOT NULL DEFAULT 'INTERNAL'
    CHECK (sensitivity IN ('PUBLIC','INTERNAL','CONFIDENTIAL','RESTRICTED')),
  source_revision jsonb NOT NULL DEFAULT '{}' CHECK (jsonb_typeof(source_revision)='object'),
  rendered_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY(embedding_space_id,entity_id),
  FOREIGN KEY(embedding_space_id,tenant_id)
    REFERENCES embedding_space(id,tenant_id) ON DELETE CASCADE,
  FOREIGN KEY(entity_id,tenant_id) REFERENCES entity(id,tenant_id) ON DELETE CASCADE
);

CREATE TABLE entity_embedding (
  tenant_id uuid NOT NULL REFERENCES tenant(id) ON DELETE CASCADE,
  embedding_space_id uuid NOT NULL,
  entity_id uuid NOT NULL,
  dimensions integer NOT NULL CHECK (dimensions BETWEEN 8 AND 4096),
  input_hash text NOT NULL CHECK (input_hash ~ '^sha256:[a-f0-9]{64}$'),
  embedding vector NOT NULL,
  token_count integer NOT NULL DEFAULT 0 CHECK (token_count>=0),
  provider_latency_ms integer CHECK (provider_latency_ms IS NULL OR provider_latency_ms>=0),
  provider_usage jsonb NOT NULL DEFAULT '{}' CHECK (jsonb_typeof(provider_usage)='object'),
  created_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY(embedding_space_id,entity_id),
  FOREIGN KEY(embedding_space_id,tenant_id,dimensions)
    REFERENCES embedding_space(id,tenant_id,dimensions) ON DELETE CASCADE,
  FOREIGN KEY(entity_id,tenant_id) REFERENCES entity(id,tenant_id) ON DELETE CASCADE,
  CHECK (vector_dims(embedding)=dimensions)
);

CREATE INDEX idx_entity_embedding_tenant_entity
  ON entity_embedding(tenant_id,entity_id);

CREATE TABLE embedding_job (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES tenant(id) ON DELETE CASCADE,
  embedding_space_id uuid NOT NULL,
  subject_kind text NOT NULL DEFAULT 'ENTITY' CHECK (subject_kind IN ('ENTITY')),
  subject_id uuid NOT NULL,
  input_hash text NOT NULL CHECK (input_hash ~ '^sha256:[a-f0-9]{64}$'),
  status text NOT NULL DEFAULT 'PENDING'
    CHECK (status IN ('PENDING','RUNNING','SUCCEEDED','RETRY_WAIT','DEAD_LETTER','CANCELLED')),
  attempt_count integer NOT NULL DEFAULT 0 CHECK (attempt_count>=0),
  max_attempts integer NOT NULL DEFAULT 8 CHECK (max_attempts BETWEEN 1 AND 100),
  available_at timestamptz NOT NULL DEFAULT now(),
  lease_owner text,
  lease_expires_at timestamptz,
  heartbeat_at timestamptz,
  retry_after_at timestamptz,
  provider_request_id text,
  last_error_class text,
  last_error text,
  created_at timestamptz NOT NULL DEFAULT now(),
  started_at timestamptz,
  completed_at timestamptz,
  updated_at timestamptz NOT NULL DEFAULT now(),
  FOREIGN KEY(embedding_space_id,tenant_id)
    REFERENCES embedding_space(id,tenant_id) ON DELETE CASCADE,
  FOREIGN KEY(subject_id,tenant_id) REFERENCES entity(id,tenant_id) ON DELETE CASCADE
);

CREATE UNIQUE INDEX idx_embedding_job_inflight
  ON embedding_job(embedding_space_id,subject_id,input_hash)
  WHERE status IN ('PENDING','RUNNING','RETRY_WAIT');
CREATE INDEX idx_embedding_job_claim
  ON embedding_job(status,available_at,tenant_id,created_at)
  WHERE status IN ('PENDING','RETRY_WAIT');

CREATE TABLE application_similarity_candidate (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES tenant(id) ON DELETE CASCADE,
  left_application_id uuid NOT NULL,
  right_application_id uuid NOT NULL,
  score double precision NOT NULL CHECK (score BETWEEN 0 AND 1),
  method_version text NOT NULL CHECK (method_version<>''),
  analysis_run_id uuid REFERENCES graph_analysis_run(id) ON DELETE SET NULL,
  semantic_space_id uuid REFERENCES embedding_space(id) ON DELETE SET NULL,
  structural_space_id uuid REFERENCES embedding_space(id) ON DELETE SET NULL,
  components jsonb NOT NULL CHECK (jsonb_typeof(components)='object'),
  overlap_features jsonb NOT NULL DEFAULT '{}' CHECK (jsonb_typeof(overlap_features)='object'),
  differences jsonb NOT NULL DEFAULT '{}' CHECK (jsonb_typeof(differences)='object'),
  coverage jsonb NOT NULL DEFAULT '{}' CHECK (jsonb_typeof(coverage)='object'),
  limitations jsonb NOT NULL DEFAULT '[]' CHECK (jsonb_typeof(limitations)='array'),
  review_state text NOT NULL DEFAULT 'UNREVIEWED'
    CHECK (review_state IN ('UNREVIEWED','CONFIRMED_SIMILAR','CONFIRMED_DISTINCT','CONSOLIDATION_CANDIDATE','DISMISSED')),
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  CHECK (left_application_id<right_application_id),
  FOREIGN KEY(left_application_id,tenant_id) REFERENCES entity(id,tenant_id) ON DELETE CASCADE,
  FOREIGN KEY(right_application_id,tenant_id) REFERENCES entity(id,tenant_id) ON DELETE CASCADE,
  UNIQUE(tenant_id,left_application_id,right_application_id,method_version)
);

CREATE INDEX idx_application_similarity_subject
  ON application_similarity_candidate(tenant_id,left_application_id,score DESC);
CREATE INDEX idx_application_similarity_peer
  ON application_similarity_candidate(tenant_id,right_application_id,score DESC);

CREATE TABLE application_similarity_feedback (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES tenant(id) ON DELETE CASCADE,
  candidate_id uuid NOT NULL REFERENCES application_similarity_candidate(id) ON DELETE CASCADE,
  decision text NOT NULL
    CHECK (decision IN ('CONFIRMED_SIMILAR','CONFIRMED_DISTINCT','CONSOLIDATION_CANDIDATE','DISMISSED')),
  reason_code text NOT NULL CHECK (reason_code<>''),
  rationale text NOT NULL DEFAULT '',
  candidate_method_version text NOT NULL CHECK (candidate_method_version<>''),
  candidate_score double precision NOT NULL CHECK (candidate_score BETWEEN 0 AND 1),
  actor_key text NOT NULL CHECK (actor_key<>''),
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE OR REPLACE FUNCTION stackgraph_similarity_feedback_immutable()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN RAISE EXCEPTION 'application similarity feedback is append-only'; END $$;
CREATE TRIGGER application_similarity_feedback_immutable
BEFORE UPDATE OR DELETE ON application_similarity_feedback
FOR EACH ROW EXECUTE FUNCTION stackgraph_similarity_feedback_immutable();

CREATE OR REPLACE FUNCTION stackgraph_enqueue_entity_embedding()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  INSERT INTO embedding_job(tenant_id,embedding_space_id,subject_id,input_hash)
  SELECT NEW.tenant_id,space.id,NEW.id,
         'sha256:'||encode(digest(concat_ws(E'\n',NEW.entity_type,NEW.name,NEW.canonical_key,NEW.properties::text,space.template_version),'sha256'),'hex')
  FROM embedding_space space
  WHERE space.tenant_id=NEW.tenant_id AND space.space_kind='SEMANTIC_ENTITY'
    AND space.lifecycle_state IN ('SHADOW','ACTIVE')
  ON CONFLICT DO NOTHING;
  RETURN NEW;
END $$;

CREATE TRIGGER entity_embedding_enqueue
AFTER INSERT OR UPDATE OF name,canonical_key,properties ON entity
FOR EACH ROW EXECUTE FUNCTION stackgraph_enqueue_entity_embedding();

CREATE OR REPLACE FUNCTION stackgraph_enqueue_fact_embedding()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  INSERT INTO embedding_job(tenant_id,embedding_space_id,subject_id,input_hash)
  SELECT entity_row.tenant_id,space.id,entity_row.id,
         'sha256:'||encode(digest(concat_ws(':',entity_row.id::text,NEW.id::text,NEW.recorded_at::text,space.template_version),'sha256'),'hex')
  FROM entity entity_row
  JOIN embedding_space space ON space.tenant_id=entity_row.tenant_id
  WHERE entity_row.id IN (NEW.subject_entity_id,NEW.object_entity_id)
    AND space.space_kind='SEMANTIC_ENTITY' AND space.lifecycle_state IN ('SHADOW','ACTIVE')
  ON CONFLICT DO NOTHING;
  RETURN NEW;
END $$;

CREATE TRIGGER fact_embedding_enqueue
AFTER INSERT OR UPDATE OF system_to,confidence,object_value ON fact_assertion
FOR EACH ROW EXECUTE FUNCTION stackgraph_enqueue_fact_embedding();

INSERT INTO tenant_service_control(tenant_id,service_key,desired_state,updated_by)
SELECT id,'embeddings','RUNNING','migration-032' FROM tenant
ON CONFLICT(tenant_id,service_key) DO NOTHING;

ALTER TABLE tenant_embedding_policy ENABLE ROW LEVEL SECURITY;
ALTER TABLE embedding_space ENABLE ROW LEVEL SECURITY;
ALTER TABLE active_embedding_space ENABLE ROW LEVEL SECURITY;
ALTER TABLE embedding_document ENABLE ROW LEVEL SECURITY;
ALTER TABLE entity_embedding ENABLE ROW LEVEL SECURITY;
ALTER TABLE embedding_job ENABLE ROW LEVEL SECURITY;
ALTER TABLE application_similarity_candidate ENABLE ROW LEVEL SECURITY;
ALTER TABLE application_similarity_feedback ENABLE ROW LEVEL SECURITY;

DO $$
DECLARE table_name text;
BEGIN
  FOREACH table_name IN ARRAY ARRAY[
    'tenant_embedding_policy','embedding_space','active_embedding_space','embedding_document',
    'entity_embedding','embedding_job','application_similarity_candidate','application_similarity_feedback'
  ] LOOP
    EXECUTE format(
      'CREATE POLICY tenant_isolation ON %I USING (tenant_id=stackgraph_current_tenant_id()) WITH CHECK (tenant_id=stackgraph_current_tenant_id())',
      table_name
    );
  END LOOP;
END $$;
