ALTER TABLE duplicate_capability_candidate
  ADD COLUMN version integer NOT NULL DEFAULT 1 CHECK(version > 0);

-- Migration 002 scoped closure to one extractor version. Repository analysis now
-- treats a newer analyzer version as the replacement for the prior complete
-- snapshot, so complete publication must close every prior version for the same
-- target and extractor key. Partial publication still closes nothing.
CREATE OR REPLACE FUNCTION publish_source_snapshot(p_snapshot_id uuid) RETURNS void
LANGUAGE plpgsql AS $$
DECLARE s source_snapshot%ROWTYPE;
BEGIN
 SELECT * INTO s FROM source_snapshot WHERE id=p_snapshot_id FOR UPDATE;
 IF NOT FOUND THEN RAISE EXCEPTION 'source snapshot % not found',p_snapshot_id; END IF;
 IF s.status<>'STAGED' THEN RAISE EXCEPTION 'source snapshot % is not staged',p_snapshot_id; END IF;
 IF s.completeness='COMPLETE' THEN
  WITH closed AS (
   UPDATE fact_assertion f SET system_to=now() FROM source_snapshot old
    WHERE f.source_snapshot_id=old.id AND old.ingest_target_id=s.ingest_target_id
      AND old.extractor_key=s.extractor_key AND old.id<>s.id AND f.system_to IS NULL
    RETURNING f.id,f.tenant_id
  )
  INSERT INTO projection_outbox(tenant_id,aggregate_type,aggregate_id,operation,dedupe_key,payload)
  SELECT closed.tenant_id,'FACT',closed.id,'CLOSE',
    'snapshot:'||p_snapshot_id::text||':close:'||closed.id::text,
    jsonb_build_object('closed_by_source_snapshot_id',p_snapshot_id)
  FROM closed ON CONFLICT(dedupe_key) DO NOTHING;
 END IF;
 UPDATE source_snapshot SET status='PUBLISHED',published_at=now() WHERE id=p_snapshot_id;
 INSERT INTO projection_outbox(tenant_id,aggregate_type,aggregate_id,operation,dedupe_key,payload)
 SELECT f.tenant_id,'FACT',f.id,'UPSERT',
   'snapshot:'||p_snapshot_id::text||':fact:'||f.id::text,
   jsonb_build_object('source_snapshot_id',p_snapshot_id)
 FROM fact_assertion f WHERE f.source_snapshot_id=p_snapshot_id
 ON CONFLICT(dedupe_key) DO NOTHING;
END $$;

CREATE TABLE duplicate_capability_candidate_review (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES tenant(id),
  duplicate_capability_candidate_id uuid NOT NULL
    REFERENCES duplicate_capability_candidate(id) ON DELETE CASCADE,
  decision text NOT NULL CHECK(decision IN ('CONFIRM','REJECT')),
  rationale text NOT NULL,
  reviewer_actor_key text NOT NULL,
  prior_version integer NOT NULL CHECK(prior_version > 0),
  resulting_version integer NOT NULL CHECK(resulting_version = prior_version + 1),
  reviewed_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE intelligence_job (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES tenant(id),
  repository_entity_id uuid NOT NULL REFERENCES entity(id) ON DELETE CASCADE,
  source_snapshot_id uuid NOT NULL REFERENCES source_snapshot(id) ON DELETE CASCADE,
  source_revision text NOT NULL,
  job_kind text NOT NULL CHECK(job_kind IN ('REPOSITORY_MODERNIZATION')),
  status text NOT NULL DEFAULT 'PENDING'
    CHECK(status IN ('PENDING','RUNNING','SUCCEEDED','FAILED')),
  available_at timestamptz NOT NULL DEFAULT now(),
  leased_by text,
  leased_until timestamptz,
  attempt integer NOT NULL DEFAULT 0 CHECK(attempt >= 0),
  max_attempts integer NOT NULL DEFAULT 5 CHECK(max_attempts > 0),
  last_error jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  started_at timestamptz,
  completed_at timestamptz,
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(tenant_id,repository_entity_id,source_revision,job_kind)
);
CREATE INDEX idx_intelligence_job_claim
  ON intelligence_job(status,available_at,leased_until,created_at);

CREATE TABLE modernization_candidate (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES tenant(id),
  repository_entity_id uuid NOT NULL REFERENCES entity(id) ON DELETE CASCADE,
  source_revision text NOT NULL,
  duplicate_capability_candidate_id uuid
    REFERENCES duplicate_capability_candidate(id) ON DELETE CASCADE,
  capability_definition_id uuid REFERENCES capability_definition(id),
  candidate_kind text NOT NULL CHECK(candidate_kind IN (
    'DEPENDENCY_CONSOLIDATION','INTERNAL_DUPLICATION','VENDORED_DUPLICATION','NATIVE_REPLACEMENT'
  )),
  subject_entity_ids uuid[] NOT NULL CHECK(cardinality(subject_entity_ids) > 0),
  confidence numeric(5,4) NOT NULL CHECK(confidence BETWEEN 0 AND 1),
  summary text NOT NULL,
  supporting_fact_ids uuid[] NOT NULL CHECK(cardinality(supporting_fact_ids) > 0),
  counter_evidence_fact_ids uuid[] NOT NULL DEFAULT '{}',
  source_locations jsonb NOT NULL DEFAULT '[]' CHECK(jsonb_typeof(source_locations)='array'),
  validation_gaps jsonb NOT NULL DEFAULT '[]' CHECK(jsonb_typeof(validation_gaps)='array'),
  analyzer_key text NOT NULL,
  analyzer_version text NOT NULL,
  input_fingerprint text NOT NULL CHECK(input_fingerprint ~ '^sha256:[a-f0-9]{64}$'),
  analysis_fingerprint text NOT NULL CHECK(analysis_fingerprint ~ '^sha256:[a-f0-9]{64}$'),
  review_state text NOT NULL DEFAULT 'UNREVIEWED'
    CHECK(review_state IN ('UNREVIEWED','CONFIRMED','REJECTED')),
  version integer NOT NULL DEFAULT 1 CHECK(version > 0),
  stale_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(tenant_id,analysis_fingerprint)
);
CREATE INDEX idx_modernization_candidate_repository
  ON modernization_candidate(tenant_id,repository_entity_id,source_revision,review_state);

CREATE TABLE modernization_option (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES tenant(id),
  modernization_candidate_id uuid NOT NULL
    REFERENCES modernization_candidate(id) ON DELETE CASCADE,
  option_kind text NOT NULL CHECK(option_kind IN ('NATIVE','INTERNAL','UPGRADE','PACKAGE')),
  canonical_key text NOT NULL,
  name text NOT NULL,
  target_entity_id uuid REFERENCES entity(id),
  compatibility text NOT NULL CHECK(compatibility IN ('OBSERVED','COMPATIBLE','UNKNOWN','INCOMPATIBLE')),
  rank integer NOT NULL CHECK(rank > 0),
  score numeric(7,4) NOT NULL CHECK(score BETWEEN 0 AND 1),
  score_components jsonb NOT NULL CHECK(jsonb_typeof(score_components)='object'),
  rationale text NOT NULL,
  tradeoffs jsonb NOT NULL DEFAULT '[]' CHECK(jsonb_typeof(tradeoffs)='array'),
  disqualifiers jsonb NOT NULL DEFAULT '[]' CHECK(jsonb_typeof(disqualifiers)='array'),
  validation_gaps jsonb NOT NULL DEFAULT '[]' CHECK(jsonb_typeof(validation_gaps)='array'),
  supporting_fact_ids uuid[] NOT NULL DEFAULT '{}',
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(modernization_candidate_id,canonical_key)
);
CREATE INDEX idx_modernization_option_candidate
  ON modernization_option(modernization_candidate_id,rank);

CREATE TABLE modernization_recommendation (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES tenant(id),
  repository_entity_id uuid NOT NULL REFERENCES entity(id) ON DELETE CASCADE,
  modernization_candidate_id uuid NOT NULL
    REFERENCES modernization_candidate(id) ON DELETE CASCADE,
  selected_option_id uuid REFERENCES modernization_option(id),
  source_revision text NOT NULL,
  action text NOT NULL CHECK(action IN ('CONSOLIDATE','REPLACE','UPGRADE','REFACTOR','INVESTIGATE')),
  objective text NOT NULL,
  title text NOT NULL,
  rationale text NOT NULL,
  confidence numeric(5,4) NOT NULL CHECK(confidence BETWEEN 0 AND 1),
  estimated_effort text NOT NULL CHECK(estimated_effort IN ('LOW','MEDIUM','HIGH','UNKNOWN')),
  affected_call_sites integer NOT NULL CHECK(affected_call_sites >= 0),
  affected_files integer NOT NULL CHECK(affected_files >= 0),
  validation_gaps jsonb NOT NULL DEFAULT '[]' CHECK(jsonb_typeof(validation_gaps)='array'),
  migration_plan jsonb NOT NULL CHECK(jsonb_typeof(migration_plan)='array'),
  rollback_plan jsonb NOT NULL CHECK(jsonb_typeof(rollback_plan)='array'),
  supporting_fact_ids uuid[] NOT NULL CHECK(cardinality(supporting_fact_ids) > 0),
  counter_evidence_fact_ids uuid[] NOT NULL DEFAULT '{}',
  counter_signals jsonb NOT NULL DEFAULT '[]' CHECK(jsonb_typeof(counter_signals)='array'),
  policy_version text NOT NULL,
  input_fingerprint text NOT NULL CHECK(input_fingerprint ~ '^sha256:[a-f0-9]{64}$'),
  analysis_fingerprint text NOT NULL CHECK(analysis_fingerprint ~ '^sha256:[a-f0-9]{64}$'),
  review_state text NOT NULL DEFAULT 'UNREVIEWED'
    CHECK(review_state IN ('UNREVIEWED','ACCEPTED','REJECTED','DISMISSED')),
  version integer NOT NULL DEFAULT 1 CHECK(version > 0),
  stale_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(tenant_id,analysis_fingerprint)
);
CREATE INDEX idx_modernization_recommendation_repository
  ON modernization_recommendation(tenant_id,repository_entity_id,source_revision,review_state);

ALTER TABLE modernization_recommendation
  ADD CONSTRAINT fk_modernization_selected_option
  FOREIGN KEY(selected_option_id) REFERENCES modernization_option(id);

CREATE TABLE modernization_recommendation_review (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES tenant(id),
  modernization_recommendation_id uuid NOT NULL
    REFERENCES modernization_recommendation(id) ON DELETE CASCADE,
  decision text NOT NULL CHECK(decision IN ('ACCEPT','REJECT','DISMISS')),
  rationale text NOT NULL,
  reviewer_actor_key text NOT NULL,
  prior_version integer NOT NULL CHECK(prior_version > 0),
  resulting_version integer NOT NULL CHECK(resulting_version = prior_version + 1),
  reviewed_at timestamptz NOT NULL DEFAULT now()
);

ALTER TABLE duplicate_capability_candidate_review ENABLE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON duplicate_capability_candidate_review
  USING(tenant_id=stackgraph_current_tenant_id())
  WITH CHECK(tenant_id=stackgraph_current_tenant_id());
ALTER TABLE intelligence_job ENABLE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON intelligence_job
  USING(tenant_id=stackgraph_current_tenant_id())
  WITH CHECK(tenant_id=stackgraph_current_tenant_id());
ALTER TABLE modernization_candidate ENABLE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON modernization_candidate
  USING(tenant_id=stackgraph_current_tenant_id())
  WITH CHECK(tenant_id=stackgraph_current_tenant_id());
ALTER TABLE modernization_option ENABLE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON modernization_option
  USING(tenant_id=stackgraph_current_tenant_id())
  WITH CHECK(tenant_id=stackgraph_current_tenant_id());
ALTER TABLE modernization_recommendation ENABLE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON modernization_recommendation
  USING(tenant_id=stackgraph_current_tenant_id())
  WITH CHECK(tenant_id=stackgraph_current_tenant_id());
ALTER TABLE modernization_recommendation_review ENABLE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON modernization_recommendation_review
  USING(tenant_id=stackgraph_current_tenant_id())
  WITH CHECK(tenant_id=stackgraph_current_tenant_id());

CREATE FUNCTION enqueue_repository_intelligence_on_publish() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  IF NEW.status='PUBLISHED'
     AND OLD.status IS DISTINCT FROM NEW.status
     AND NEW.completeness='COMPLETE'
     AND NEW.extractor_key='repository-dependency-usage' THEN
    INSERT INTO intelligence_job(
      tenant_id,repository_entity_id,source_snapshot_id,source_revision,job_kind
    )
    SELECT NEW.tenant_id,repository.id,NEW.id,NEW.source_revision,'REPOSITORY_MODERNIZATION'
    FROM ingest_target target
    JOIN entity repository
      ON repository.tenant_id=NEW.tenant_id
     AND repository.namespace='ENTERPRISE'
     AND repository.entity_type='Repository'
     AND repository.canonical_key=target.target_key
    WHERE target.id=NEW.ingest_target_id
    ON CONFLICT(tenant_id,repository_entity_id,source_revision,job_kind) DO NOTHING;
  END IF;
  RETURN NEW;
END $$;

CREATE TRIGGER source_snapshot_enqueue_repository_intelligence
AFTER UPDATE OF status ON source_snapshot
FOR EACH ROW EXECUTE FUNCTION enqueue_repository_intelligence_on_publish();
