-- Governed modernization policy, calibration, canonical business capability links,
-- shared capability footprints, portfolio scoring, and bounded ecosystem admission.

ALTER TABLE modernization_policy
  ADD COLUMN configuration_fingerprint text
    CHECK(configuration_fingerprint IS NULL OR configuration_fingerprint ~ '^sha256:[a-f0-9]{64}$'),
  ADD COLUMN activated_by text,
  ADD COLUMN activated_at timestamptz,
  ADD COLUMN retired_by text,
  ADD COLUMN retired_at timestamptz;

ALTER TABLE modernization_internal_component
  ADD COLUMN review_state text NOT NULL DEFAULT 'UNREVIEWED'
    CHECK(review_state IN ('UNREVIEWED','APPROVED','REJECTED')),
  ADD COLUMN owner text,
  ADD COLUMN governed_by text,
  ADD COLUMN governed_at timestamptz,
  ADD COLUMN catalog_fingerprint text
    CHECK(catalog_fingerprint IS NULL OR catalog_fingerprint ~ '^sha256:[a-f0-9]{64}$');

CREATE TABLE modernization_calibration_corpus (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES tenant(id),
  corpus_key text NOT NULL CHECK(corpus_key ~ '^[a-z][a-z0-9_.-]{2,127}$'),
  version text NOT NULL CHECK(version<>''),
  status text NOT NULL DEFAULT 'DRAFT' CHECK(status IN ('DRAFT','ACTIVE','RETIRED')),
  case_count integer NOT NULL DEFAULT 0 CHECK(case_count>=0),
  case_fingerprints text[] NOT NULL DEFAULT '{}',
  thresholds jsonb NOT NULL CHECK(jsonb_typeof(thresholds)='object'),
  observed_metrics jsonb NOT NULL DEFAULT '{}' CHECK(jsonb_typeof(observed_metrics)='object'),
  corpus_fingerprint text NOT NULL CHECK(corpus_fingerprint ~ '^sha256:[a-f0-9]{64}$'),
  promotion_passed boolean NOT NULL DEFAULT false,
  promotion_failures text[] NOT NULL DEFAULT '{}',
  evaluation_fingerprint text CHECK(evaluation_fingerprint IS NULL OR evaluation_fingerprint ~ '^sha256:[a-f0-9]{64}$'),
  evaluated_at timestamptz,
  created_by text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(tenant_id,corpus_key,version)
);
CREATE UNIQUE INDEX uq_modernization_calibration_active
  ON modernization_calibration_corpus(tenant_id,corpus_key) WHERE status='ACTIVE';

CREATE TABLE modernization_portfolio_policy (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES tenant(id),
  policy_key text NOT NULL CHECK(policy_key ~ '^[a-z][a-z0-9_.-]{2,127}$'),
  version text NOT NULL CHECK(version<>''),
  status text NOT NULL DEFAULT 'DRAFT' CHECK(status IN ('DRAFT','ACTIVE','RETIRED')),
  weights jsonb NOT NULL CHECK(jsonb_typeof(weights)='object'),
  effort_penalty_weight numeric(5,4) NOT NULL CHECK(effort_penalty_weight BETWEEN 0 AND 1),
  policy_fingerprint text NOT NULL CHECK(policy_fingerprint ~ '^sha256:[a-f0-9]{64}$'),
  calibration_corpus_id uuid REFERENCES modernization_calibration_corpus(id),
  created_by text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(tenant_id,policy_key,version)
);
CREATE UNIQUE INDEX uq_modernization_portfolio_policy_active
  ON modernization_portfolio_policy(tenant_id,policy_key) WHERE status='ACTIVE';

CREATE TABLE ecosystem_admission (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES tenant(id),
  ecosystem text NOT NULL CHECK(ecosystem IN ('PYPI','MAVEN','CARGO','NUGET')),
  sequence integer NOT NULL CHECK(sequence>0),
  status text NOT NULL DEFAULT 'PROPOSED' CHECK(status IN ('PROPOSED','ADMITTED','RETIRED')),
  observed_repositories integer NOT NULL DEFAULT 0 CHECK(observed_repositories>=0),
  observed_dependency_share numeric(7,6) NOT NULL DEFAULT 0 CHECK(observed_dependency_share BETWEEN 0 AND 1),
  minimum_repositories integer NOT NULL DEFAULT 10 CHECK(minimum_repositories>0),
  minimum_dependency_share numeric(7,6) NOT NULL DEFAULT 0.02 CHECK(minimum_dependency_share BETWEEN 0 AND 1),
  metadata_parity boolean NOT NULL DEFAULT false,
  calibration_gate_passed boolean NOT NULL DEFAULT false,
  decision_fingerprint text NOT NULL CHECK(decision_fingerprint ~ '^sha256:[a-f0-9]{64}$'),
  reasons text[] NOT NULL DEFAULT '{}',
  decided_by text NOT NULL,
  decided_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(tenant_id,ecosystem),
  UNIQUE(tenant_id,sequence)
);

-- New snapshots and explicit reanalysis now share the same governed configuration boundary.
CREATE OR REPLACE FUNCTION enqueue_repository_intelligence_on_publish() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF NEW.status='PUBLISHED' AND OLD.status IS DISTINCT FROM NEW.status
    AND NEW.completeness='COMPLETE' AND NEW.extractor_key='repository-dependency-usage' THEN
  INSERT INTO intelligence_job(
   tenant_id,repository_entity_id,source_snapshot_id,source_revision,
   job_kind,configuration_fingerprint
  )
  SELECT NEW.tenant_id,repository.id,NEW.id,NEW.source_revision,'REPOSITORY_MODERNIZATION',
   coalesce(policy.configuration_fingerprint,
    tenant_ai_configuration_fingerprint(
      configuration.provider,configuration.model,configuration.credential_secret_id
    ),'snapshot-v1')
  FROM ingest_target target JOIN entity repository
    ON repository.tenant_id=NEW.tenant_id AND repository.namespace='ENTERPRISE'
   AND repository.entity_type='Repository' AND repository.canonical_key=target.target_key
  LEFT JOIN tenant_ai_configuration configuration
    ON configuration.tenant_id=NEW.tenant_id AND configuration.enabled
   AND configuration.model<>'' AND configuration.credential_secret_id IS NOT NULL
  LEFT JOIN LATERAL (
    SELECT value.configuration_fingerprint FROM modernization_policy value
    WHERE value.tenant_id=NEW.tenant_id AND value.status='ACTIVE'
      AND value.configuration_fingerprint IS NOT NULL
    ORDER BY value.updated_at DESC,value.id DESC LIMIT 1
  ) policy ON true
  WHERE target.id=NEW.ingest_target_id
  ON CONFLICT DO NOTHING;
 END IF;
 RETURN NEW;
END; $$;

-- Canonicalize business-map capabilities to stable BUSINESS entities. A capability key is
-- intentionally shared across maps; map revisions remain the evidence for each assignment.
INSERT INTO entity(tenant_id,namespace,entity_type,canonical_key,name,properties,first_seen_at,last_seen_at)
SELECT DISTINCT capability.tenant_id,'BUSINESS','BusinessCapability',
       'capability:'||capability.capability_key,capability.name,
       jsonb_build_object('source','business-map','governance','CURATED'),
       capability.created_at,capability.updated_at
FROM business_map_capability capability
ON CONFLICT(tenant_id,namespace,entity_type,canonical_key) DO UPDATE
SET name=EXCLUDED.name,last_seen_at=greatest(entity.last_seen_at,EXCLUDED.last_seen_at),updated_at=now();

UPDATE business_map_capability capability
SET entity_id=entity.id
FROM entity
WHERE entity.tenant_id=capability.tenant_id
  AND entity.namespace='BUSINESS' AND entity.entity_type='BusinessCapability'
  AND entity.canonical_key='capability:'||capability.capability_key;

CREATE VIEW current_capability_application_relationship WITH (security_invoker=true) AS
SELECT assignment.tenant_id,capability.entity_id capability_entity_id,
       assignment.application_entity_id,assignment.business_map_id,
       revision.id evidence_revision_id,'CURATED'::text assertion_class,
       1.0::numeric(5,4) confidence,
       'sha256:'||encode(digest(convert_to(
         assignment.tenant_id::text||chr(31)||capability.entity_id::text||chr(31)||
         assignment.application_entity_id::text||chr(31)||revision.id::text,'UTF8'
       ),'sha256'),'hex') analysis_fingerprint,
       revision.created_at observed_at
FROM business_map_application_assignment assignment
JOIN business_map_capability capability
  ON capability.id=assignment.business_map_capability_id
JOIN LATERAL (
  SELECT value.id,value.created_at FROM business_map_revision value
  WHERE value.business_map_id=assignment.business_map_id
  ORDER BY value.version DESC LIMIT 1
) revision ON true
WHERE capability.entity_id IS NOT NULL;

CREATE VIEW capability_footprint WITH (security_invoker=true) AS
WITH relationship AS (
  SELECT DISTINCT tenant_id,capability_entity_id,application_entity_id
  FROM current_capability_application_relationship
), repository_link AS (
  SELECT DISTINCT relationship.tenant_id,relationship.capability_entity_id,
         relationship.application_entity_id,
         CASE WHEN edge.source_entity_id=relationship.application_entity_id
              THEN edge.target_entity_id ELSE edge.source_entity_id END repository_entity_id
  FROM relationship
  JOIN current_relationship edge
    ON edge.tenant_id=relationship.tenant_id
   AND (edge.source_entity_id=relationship.application_entity_id
        OR edge.target_entity_id=relationship.application_entity_id)
  JOIN entity repository ON repository.id=CASE
    WHEN edge.source_entity_id=relationship.application_entity_id
    THEN edge.target_entity_id ELSE edge.source_entity_id END
  WHERE repository.namespace='ENTERPRISE' AND repository.entity_type='Repository'
    AND edge.relationship_type IN ('IMPLEMENTED_BY','IMPLEMENTS','CONTAINS')
), technology_link AS (
  SELECT DISTINCT repository_link.tenant_id,repository_link.capability_entity_id,
         repository_link.repository_entity_id,
         CASE WHEN edge.source_entity_id=repository_link.repository_entity_id
              THEN edge.target_entity_id ELSE edge.source_entity_id END technology_entity_id
  FROM repository_link
  JOIN current_relationship edge
    ON edge.tenant_id=repository_link.tenant_id
   AND (edge.source_entity_id=repository_link.repository_entity_id
        OR edge.target_entity_id=repository_link.repository_entity_id)
  JOIN entity technology ON technology.id=CASE
    WHEN edge.source_entity_id=repository_link.repository_entity_id
    THEN edge.target_entity_id ELSE edge.source_entity_id END
  WHERE technology.namespace IN ('TECHNOLOGY','OSS')
    AND edge.relationship_type IN ('DEPENDS_ON','USES','RUNS_ON','BUILT_ON','HAS_VERSION')
), technology_count AS (
  SELECT tenant_id,capability_entity_id,technology_entity_id,
         count(DISTINCT repository_entity_id)::integer repository_occurrences
  FROM technology_link GROUP BY tenant_id,capability_entity_id,technology_entity_id
), technology_stat AS (
  SELECT tenant_id,capability_entity_id,count(*)::integer technology_count,
         sum(repository_occurrences)::numeric total_occurrences,
         jsonb_object_agg(technology_entity_id::text,repository_occurrences ORDER BY technology_entity_id) technology_counts
  FROM technology_count GROUP BY tenant_id,capability_entity_id
), entropy AS (
  SELECT item.tenant_id,item.capability_entity_id,
         CASE WHEN stat.technology_count<=1 OR stat.total_occurrences=0 THEN 0::numeric
              ELSE -sum((item.repository_occurrences/stat.total_occurrences)
                    *ln(item.repository_occurrences/stat.total_occurrences))
                   /ln(stat.technology_count) END technology_entropy
  FROM technology_count item JOIN technology_stat stat
    USING(tenant_id,capability_entity_id)
  GROUP BY item.tenant_id,item.capability_entity_id,stat.technology_count,stat.total_occurrences
), application_stat AS (
  SELECT tenant_id,capability_entity_id,count(DISTINCT application_entity_id)::integer application_count
  FROM relationship GROUP BY tenant_id,capability_entity_id
), repository_stat AS (
  SELECT tenant_id,capability_entity_id,count(DISTINCT repository_entity_id)::integer repository_count
  FROM repository_link GROUP BY tenant_id,capability_entity_id
)
SELECT application_stat.tenant_id,application_stat.capability_entity_id,
       application_stat.application_count,coalesce(repository_stat.repository_count,0) repository_count,
       coalesce(technology_stat.technology_count,0) technology_count,
       coalesce(technology_stat.technology_counts,'{}'::jsonb) technology_counts,
       coalesce(entropy.technology_entropy,0)::numeric(7,6) technology_entropy,
       least(1::numeric,ln(1+application_stat.application_count+coalesce(repository_stat.repository_count,0))/ln(21))::numeric(7,6) reuse_signal
FROM application_stat
LEFT JOIN repository_stat USING(tenant_id,capability_entity_id)
LEFT JOIN technology_stat USING(tenant_id,capability_entity_id)
LEFT JOIN entropy USING(tenant_id,capability_entity_id);

CREATE INDEX idx_modernization_policy_tenant_status
  ON modernization_policy(tenant_id,status,updated_at DESC);
CREATE INDEX idx_modernization_internal_governance
  ON modernization_internal_component(tenant_id,review_state,status,updated_at DESC);
CREATE INDEX idx_calibration_corpus_tenant
  ON modernization_calibration_corpus(tenant_id,status,updated_at DESC);
CREATE INDEX idx_ecosystem_admission_tenant
  ON ecosystem_admission(tenant_id,sequence,status);

ALTER TABLE modernization_calibration_corpus ENABLE ROW LEVEL SECURITY;
ALTER TABLE modernization_portfolio_policy ENABLE ROW LEVEL SECURITY;
ALTER TABLE ecosystem_admission ENABLE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON modernization_calibration_corpus
  USING(tenant_id=stackgraph_current_tenant_id()) WITH CHECK(tenant_id=stackgraph_current_tenant_id());
CREATE POLICY tenant_isolation ON modernization_portfolio_policy
  USING(tenant_id=stackgraph_current_tenant_id()) WITH CHECK(tenant_id=stackgraph_current_tenant_id());
CREATE POLICY tenant_isolation ON ecosystem_admission
  USING(tenant_id=stackgraph_current_tenant_id()) WITH CHECK(tenant_id=stackgraph_current_tenant_id());
