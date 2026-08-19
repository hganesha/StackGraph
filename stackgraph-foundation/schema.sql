-- StackGraph authoritative PostgreSQL schema, contract v1.0.0.
-- PostgreSQL 15+ is required. Apache AGE is an asynchronous projection.
BEGIN;
CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE tenant (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(), tenant_key text UNIQUE NOT NULL CHECK (tenant_key <> ''),
  name text NOT NULL CHECK (name <> ''), status text NOT NULL DEFAULT 'ACTIVE' CHECK (status IN ('ACTIVE','SUSPENDED','DELETED')),
  created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE FUNCTION stackgraph_current_tenant_id() RETURNS uuid LANGUAGE sql STABLE AS $$
  SELECT NULLIF(current_setting('app.tenant_id', true), '')::uuid
$$;

CREATE TABLE ontology_entity_type (
  namespace text NOT NULL CHECK (namespace IN ('BUSINESS','ENTERPRISE','TECHNOLOGY','OSS','DEPLOYMENT','INTELLIGENCE')),
  entity_type text NOT NULL, contract_version text NOT NULL DEFAULT '1.0.0', PRIMARY KEY (namespace, entity_type)
);
INSERT INTO ontology_entity_type(namespace,entity_type) VALUES
 ('BUSINESS','Organization'),('BUSINESS','BusinessUnit'),('BUSINESS','ValueChain'),('BUSINESS','BusinessFunction'),('BUSINESS','BusinessProcess'),('BUSINESS','BusinessCapability'),
 ('ENTERPRISE','Application'),('ENTERPRISE','Service'),('ENTERPRISE','Component'),('ENTERPRISE','API'),('ENTERPRISE','Repository'),
 ('TECHNOLOGY','Technology'),('TECHNOLOGY','Capability'),('TECHNOLOGY','ArchitecturePattern'),('TECHNOLOGY','Language'),('TECHNOLOGY','Framework'),('TECHNOLOGY','Runtime'),('TECHNOLOGY','Package'),('TECHNOLOGY','PackageVersion'),('TECHNOLOGY','Database'),('TECHNOLOGY','Storage'),('TECHNOLOGY','Queue'),
 ('DEPLOYMENT','Deployment'),('DEPLOYMENT','Environment'),('DEPLOYMENT','ComputeTarget'),('DEPLOYMENT','CloudProvider'),('DEPLOYMENT','OnPrem'),('DEPLOYMENT','Region'),('DEPLOYMENT','ContainerImage'),('DEPLOYMENT','InfrastructureResource'),
 ('OSS','OSSProject'),('OSS','OSSRepository'),('OSS','Release'),('OSS','License'),('OSS','Maintainer'),('OSS','ReferenceImplementation'),('OSS','MigrationPattern'),('OSS','Ecosystem'),
 ('INTELLIGENCE','Vulnerability'),('INTELLIGENCE','Finding'),('INTELLIGENCE','Assessment'),('INTELLIGENCE','Recommendation'),('INTELLIGENCE','ModernizationOpportunity'),('INTELLIGENCE','Standard'),('INTELLIGENCE','Trend');

CREATE TABLE predicate_definition (
  predicate text PRIMARY KEY, object_kind text NOT NULL CHECK (object_kind IN ('ENTITY','VALUE','EITHER')),
  projects_as_edge boolean NOT NULL DEFAULT true, contract_version text NOT NULL DEFAULT '1.0.0'
);
INSERT INTO predicate_definition(predicate,object_kind,projects_as_edge) VALUES
 ('OWNS','ENTITY',true),('OPERATES','ENTITY',true),('CONTAINS','ENTITY',true),('REQUIRES','ENTITY',true),('ENABLED_BY','ENTITY',true),('PROVIDED_BY','ENTITY',true),('PROVIDES','ENTITY',true),('IMPLEMENTED_BY','ENTITY',true),('IMPLEMENTS','ENTITY',true),('DEPENDS_ON','ENTITY',true),('USES','ENTITY',true),('CALLS','ENTITY',true),('EXPOSES','ENTITY',true),('DEPLOYED_AS','ENTITY',true),('RUNS_ON','ENTITY',true),('LOCATED_IN','ENTITY',true),('HOSTED_IN','ENTITY',true),('HOSTED_AT','ENTITY',true),('CONNECTS_TO','ENTITY',true),('HAS_VERSION','ENTITY',true),('AFFECTED_BY','ENTITY',true),('ALTERNATIVE_TO','ENTITY',true),('COMMONLY_USED_WITH','ENTITY',true),('MIGRATED_TO','ENTITY',true),('PUBLISHES','ENTITY',true),('PUBLISHED_BY','ENTITY',true),('MAINTAINED_BY','ENTITY',true),('HAS_RELEASE','ENTITY',true),('USES_LICENSE','ENTITY',true),('DEMONSTRATES','ENTITY',true),('BUILT_ON','ENTITY',true),('PAIRS_WITH','ENTITY',true),('SAME_AS','ENTITY',true),('LIKELY_SUPERSEDED_BY','ENTITY',true),('TARGETS','ENTITY',true),('RECOMMENDS','ENTITY',true),('TREND','ENTITY',true),('HAS_PROPERTY','VALUE',false);

CREATE TABLE source_system (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(), tenant_id uuid REFERENCES tenant(id), source_key text NOT NULL,
  kind text NOT NULL CHECK (kind IN ('GITHUB','PACKAGE_REGISTRY','DEPS_DEV','OSV','OPENSSF','CURATED','OTHER')),
  base_uri text, metadata jsonb NOT NULL DEFAULT '{}' CHECK (jsonb_typeof(metadata)='object'), created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE NULLS NOT DISTINCT (tenant_id,source_key)
);
CREATE TABLE connector_account (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(), tenant_id uuid REFERENCES tenant(id), source_system_id uuid NOT NULL REFERENCES source_system(id),
  external_account_key text NOT NULL, credential_reference text NOT NULL, permissions jsonb NOT NULL DEFAULT '[]' CHECK (jsonb_typeof(permissions)='array'),
  status text NOT NULL DEFAULT 'ACTIVE' CHECK (status IN ('ACTIVE','DISABLED','REVOKED')), created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE NULLS NOT DISTINCT (tenant_id,source_system_id,external_account_key)
);
CREATE TABLE package_registry (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(), tenant_id uuid REFERENCES tenant(id), source_system_id uuid NOT NULL REFERENCES source_system(id),
  connector_account_id uuid REFERENCES connector_account(id), registry_key text NOT NULL,
  origin_uri text NOT NULL CHECK(NOT origin_uri ~ '^https?://[^/]*@'),
  normalized_origin_uri text NOT NULL CHECK(normalized_origin_uri ~ '^https?://[^@]+/?$'),
  ecosystem text NOT NULL CHECK(ecosystem IN ('NPM','PYPI','MAVEN','CARGO','OTHER')),
  visibility text NOT NULL DEFAULT 'UNKNOWN' CHECK(visibility IN ('PUBLIC','PRIVATE','UNKNOWN')),
  auth_mode text NOT NULL DEFAULT 'NONE' CHECK(auth_mode IN ('NONE','TOKEN','BASIC','MTLS','OIDC','OTHER')),
  allow_metadata_fetch boolean NOT NULL DEFAULT true, metadata jsonb NOT NULL DEFAULT '{}',
  created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(),
  CHECK(visibility<>'PRIVATE' OR tenant_id IS NOT NULL),
  UNIQUE NULLS NOT DISTINCT(tenant_id,ecosystem,normalized_origin_uri), UNIQUE NULLS NOT DISTINCT(tenant_id,registry_key)
);
CREATE TABLE package_registry_scope (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(), tenant_id uuid NOT NULL REFERENCES tenant(id), package_registry_id uuid NOT NULL REFERENCES package_registry(id) ON DELETE CASCADE,
  target_key text NOT NULL, package_scope text NOT NULL CHECK(package_scope ~ '^@[a-z0-9._~-]+$'), config_path text, source_revision text NOT NULL,
  first_seen_at timestamptz NOT NULL DEFAULT now(), last_seen_at timestamptz, UNIQUE(tenant_id,target_key,package_scope,source_revision)
);
CREATE TABLE ingest_target (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(), tenant_id uuid REFERENCES tenant(id), source_system_id uuid NOT NULL REFERENCES source_system(id), connector_account_id uuid REFERENCES connector_account(id),
  target_kind text NOT NULL, target_key text NOT NULL, priority text NOT NULL DEFAULT 'WARM' CHECK (priority IN ('HOT','WARM','COLD','ON_DEMAND')),
  enabled boolean NOT NULL DEFAULT true, refresh_policy jsonb NOT NULL DEFAULT '{}' CHECK (jsonb_typeof(refresh_policy)='object'),
  desired_source_revision text, next_due_at timestamptz, last_success_at timestamptz, created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE NULLS NOT DISTINCT (tenant_id,source_system_id,target_kind,target_key)
);
CREATE TABLE ingest_cursor (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(), tenant_id uuid REFERENCES tenant(id), ingest_target_id uuid NOT NULL REFERENCES ingest_target(id) ON DELETE CASCADE,
  cursor_kind text NOT NULL, cursor_value jsonb NOT NULL, source_revision text, updated_at timestamptz NOT NULL DEFAULT now(), UNIQUE(ingest_target_id,cursor_kind)
);
CREATE TABLE webhook_delivery (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(), tenant_id uuid REFERENCES tenant(id), source_system_id uuid NOT NULL REFERENCES source_system(id),
  provider_delivery_id text NOT NULL, event_type text NOT NULL, event_action text, signature_verified boolean NOT NULL,
  headers jsonb NOT NULL DEFAULT '{}', body_hash text NOT NULL CHECK (body_hash ~ '^sha256:[a-f0-9]{64}$'), blob_uri text,
  status text NOT NULL DEFAULT 'RECEIVED' CHECK (status IN ('RECEIVED','PROCESSING','PROCESSED','IGNORED','FAILED')),
  received_at timestamptz NOT NULL DEFAULT now(), processed_at timestamptz, error jsonb, UNIQUE(source_system_id,provider_delivery_id)
);
CREATE TABLE ingest_run (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(), tenant_id uuid REFERENCES tenant(id), ingest_target_id uuid NOT NULL REFERENCES ingest_target(id),
  trigger_kind text NOT NULL CHECK (trigger_kind IN ('WEBHOOK','SCHEDULE','RECONCILIATION','MANUAL','REPLAY')), requested_source_revision text,
  status text NOT NULL DEFAULT 'PENDING' CHECK (status IN ('PENDING','RUNNING','SUCCEEDED','FAILED','PARTIAL','CANCELLED')),
  completeness text CHECK (completeness IN ('COMPLETE','PARTIAL')), attempt integer NOT NULL DEFAULT 1 CHECK (attempt>0),
  available_at timestamptz NOT NULL DEFAULT now(), lease_owner text, lease_expires_at timestamptz, started_at timestamptz, completed_at timestamptz,
  stats jsonb NOT NULL DEFAULT '{}', error_class text, error_detail jsonb, created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE ingest_item (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(), tenant_id uuid REFERENCES tenant(id), ingest_run_id uuid NOT NULL REFERENCES ingest_run(id) ON DELETE CASCADE,
  item_key text NOT NULL, item_kind text NOT NULL, status text NOT NULL DEFAULT 'PENDING' CHECK (status IN ('PENDING','RUNNING','SUCCEEDED','FAILED','SKIPPED')),
  attempt integer NOT NULL DEFAULT 1 CHECK(attempt>0), available_at timestamptz NOT NULL DEFAULT now(), lease_owner text, lease_expires_at timestamptz,
  stats jsonb NOT NULL DEFAULT '{}', error jsonb, UNIQUE(ingest_run_id,item_key)
);
CREATE TABLE source_artifact (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(), tenant_id uuid REFERENCES tenant(id), source_system_id uuid NOT NULL REFERENCES source_system(id),
  external_key text NOT NULL, artifact_type text NOT NULL, name text, source_revision text NOT NULL,
  content_hash text CHECK(content_hash IS NULL OR content_hash ~ '^sha256:[a-f0-9]{64}$'), blob_uri text, metadata jsonb NOT NULL DEFAULT '{}',
  observed_at timestamptz NOT NULL, created_at timestamptz NOT NULL DEFAULT now(), UNIQUE NULLS NOT DISTINCT(tenant_id,source_system_id,external_key,source_revision)
);
CREATE TABLE raw_observation (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(), tenant_id uuid REFERENCES tenant(id), ingest_run_id uuid REFERENCES ingest_run(id), source_system_id uuid NOT NULL REFERENCES source_system(id),
  target_key text NOT NULL, source_revision text NOT NULL, adapter_key text NOT NULL, adapter_version text NOT NULL, provider_schema_version text,
  idempotency_key text NOT NULL UNIQUE CHECK(idempotency_key ~ '^sha256:[a-f0-9]{64}$'), content_hash text NOT NULL CHECK(content_hash ~ '^sha256:[a-f0-9]{64}$'),
  media_type text NOT NULL, size_bytes bigint NOT NULL CHECK(size_bytes>=0), inline_body jsonb, blob_uri text, request_metadata jsonb NOT NULL DEFAULT '{}',
  observed_at timestamptz NOT NULL, effective_at timestamptz, recorded_at timestamptz NOT NULL DEFAULT now(), CHECK((inline_body IS NOT NULL)<>(blob_uri IS NOT NULL))
);
CREATE TABLE source_snapshot (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(), tenant_id uuid REFERENCES tenant(id), ingest_run_id uuid NOT NULL REFERENCES ingest_run(id), ingest_target_id uuid NOT NULL REFERENCES ingest_target(id),
  source_revision text NOT NULL, extractor_key text NOT NULL, extractor_version text NOT NULL, completeness text NOT NULL CHECK(completeness IN ('COMPLETE','PARTIAL')),
  status text NOT NULL DEFAULT 'STAGED' CHECK(status IN ('STAGED','PUBLISHED','REJECTED')), observed_at timestamptz NOT NULL, published_at timestamptz,
  stats jsonb NOT NULL DEFAULT '{}', UNIQUE(ingest_target_id,source_revision,extractor_key,extractor_version)
);

CREATE TABLE entity (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(), tenant_id uuid REFERENCES tenant(id), namespace text NOT NULL, entity_type text NOT NULL,
  canonical_key text NOT NULL, name text NOT NULL, properties jsonb NOT NULL DEFAULT '{}' CHECK(jsonb_typeof(properties)='object'),
  first_seen_at timestamptz, last_seen_at timestamptz, created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(),
  FOREIGN KEY(namespace,entity_type) REFERENCES ontology_entity_type(namespace,entity_type), UNIQUE NULLS NOT DISTINCT(tenant_id,namespace,entity_type,canonical_key)
);
CREATE TABLE entity_identity (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(), tenant_id uuid REFERENCES tenant(id), entity_id uuid NOT NULL REFERENCES entity(id) ON DELETE CASCADE,
  scheme text NOT NULL CHECK(scheme IN ('PURL','GITHUB_REPOSITORY_ID','GITHUB_NODE_ID','SPDX','OSV','CVE','GHSA','URL','STACKGRAPH')),
  identity_value text NOT NULL, is_canonical boolean NOT NULL DEFAULT false, source_artifact_id uuid REFERENCES source_artifact(id),
  first_seen_at timestamptz NOT NULL DEFAULT now(), last_seen_at timestamptz, UNIQUE NULLS NOT DISTINCT(tenant_id,scheme,identity_value)
);
CREATE TABLE package_registry_identity (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(), tenant_id uuid REFERENCES tenant(id), entity_id uuid NOT NULL REFERENCES entity(id) ON DELETE CASCADE,
  package_registry_id uuid NOT NULL REFERENCES package_registry(id), package_name text NOT NULL, package_version text,
  purl text NOT NULL CHECK(purl ~ '^pkg:[^/]+/.+'), visibility text NOT NULL CHECK(visibility IN ('PUBLIC','PRIVATE','UNKNOWN')),
  first_seen_at timestamptz NOT NULL DEFAULT now(), last_seen_at timestamptz,
  UNIQUE NULLS NOT DISTINCT(package_registry_id,package_name,package_version)
);
CREATE TABLE entity_alias (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(), tenant_id uuid REFERENCES tenant(id), entity_id uuid NOT NULL REFERENCES entity(id) ON DELETE CASCADE,
  alias_kind text NOT NULL, alias_value text NOT NULL, valid_from timestamptz, valid_to timestamptz, source_artifact_id uuid REFERENCES source_artifact(id),
  UNIQUE NULLS NOT DISTINCT(tenant_id,alias_kind,alias_value,valid_from)
);
CREATE TABLE identity_assertion (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(), tenant_id uuid REFERENCES tenant(id), left_entity_id uuid NOT NULL REFERENCES entity(id) ON DELETE CASCADE,
  right_entity_id uuid NOT NULL REFERENCES entity(id) ON DELETE CASCADE, method text NOT NULL, method_version text NOT NULL,
  confidence numeric(5,4) NOT NULL CHECK(confidence BETWEEN 0 AND 1), review_state text NOT NULL DEFAULT 'POSSIBLE' CHECK(review_state IN ('POSSIBLE','CONFIRMED','REJECTED')),
  version integer NOT NULL DEFAULT 1 CHECK(version>0), source_artifact_id uuid REFERENCES source_artifact(id), created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(),
  CHECK(left_entity_id<>right_entity_id), UNIQUE NULLS NOT DISTINCT(tenant_id,left_entity_id,right_entity_id,method,method_version)
);
CREATE TABLE identity_assertion_review (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(), tenant_id uuid NOT NULL REFERENCES tenant(id), identity_assertion_id uuid NOT NULL REFERENCES identity_assertion(id) ON DELETE CASCADE,
  decision text NOT NULL CHECK(decision IN ('CONFIRM','REJECT')), rationale text NOT NULL, actor_key text NOT NULL, prior_version integer NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(), UNIQUE(identity_assertion_id,prior_version)
);

CREATE TABLE fact_assertion (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(), tenant_id uuid REFERENCES tenant(id), source_snapshot_id uuid NOT NULL REFERENCES source_snapshot(id),
  subject_entity_id uuid NOT NULL REFERENCES entity(id) ON DELETE CASCADE, predicate text NOT NULL REFERENCES predicate_definition(predicate),
  object_entity_id uuid REFERENCES entity(id) ON DELETE CASCADE, object_value jsonb,
  assertion_class text NOT NULL CHECK(assertion_class IN ('DECLARED','OBSERVED','INFERRED','CURATED','EXTERNAL_MEASURED')),
  confidence numeric(5,4) NOT NULL CHECK(confidence BETWEEN 0 AND 1), logical_key text NOT NULL CHECK(logical_key ~ '^sha256:[a-f0-9]{64}$'),
  idempotency_key text NOT NULL UNIQUE CHECK(idempotency_key ~ '^sha256:[a-f0-9]{64}$'), source_revision text NOT NULL, extractor_key text NOT NULL, extractor_version text NOT NULL,
  properties jsonb NOT NULL DEFAULT '{}', effective_from timestamptz, effective_to timestamptz, observed_at timestamptz NOT NULL,
  system_from timestamptz NOT NULL DEFAULT now(), system_to timestamptz,
  CHECK((object_entity_id IS NOT NULL)<>(object_value IS NOT NULL)), CHECK(effective_to IS NULL OR effective_from IS NULL OR effective_to>=effective_from), CHECK(system_to IS NULL OR system_to>=system_from)
);
CREATE FUNCTION validate_fact_object_kind() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE expected_kind text; snapshot_tenant uuid; subject_tenant uuid; object_tenant uuid;
BEGIN
 SELECT object_kind INTO expected_kind FROM predicate_definition WHERE predicate=NEW.predicate;
 IF expected_kind='ENTITY' AND NEW.object_entity_id IS NULL THEN RAISE EXCEPTION 'predicate % requires object_entity_id',NEW.predicate;
 ELSIF expected_kind='VALUE' AND NEW.object_value IS NULL THEN RAISE EXCEPTION 'predicate % requires object_value',NEW.predicate; END IF;
 SELECT tenant_id INTO snapshot_tenant FROM source_snapshot WHERE id=NEW.source_snapshot_id;
 IF snapshot_tenant IS DISTINCT FROM NEW.tenant_id THEN RAISE EXCEPTION 'fact tenant must match source snapshot tenant'; END IF;
 SELECT tenant_id INTO subject_tenant FROM entity WHERE id=NEW.subject_entity_id;
 IF subject_tenant IS NOT NULL AND subject_tenant IS DISTINCT FROM NEW.tenant_id THEN RAISE EXCEPTION 'fact subject is outside tenant scope'; END IF;
 IF NEW.object_entity_id IS NOT NULL THEN
  SELECT tenant_id INTO object_tenant FROM entity WHERE id=NEW.object_entity_id;
  IF object_tenant IS NOT NULL AND object_tenant IS DISTINCT FROM NEW.tenant_id THEN RAISE EXCEPTION 'fact object is outside tenant scope'; END IF;
 END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER trg_validate_fact_object_kind BEFORE INSERT OR UPDATE OF predicate,object_entity_id,object_value ON fact_assertion FOR EACH ROW EXECUTE FUNCTION validate_fact_object_kind();
CREATE TABLE evidence (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(), tenant_id uuid REFERENCES tenant(id), fact_assertion_id uuid NOT NULL REFERENCES fact_assertion(id) ON DELETE CASCADE,
  source_artifact_id uuid NOT NULL REFERENCES source_artifact(id), evidence_type text NOT NULL, locator jsonb NOT NULL CHECK(jsonb_typeof(locator)='object' AND locator<>'{}'),
  excerpt_hash text CHECK(excerpt_hash IS NULL OR excerpt_hash ~ '^sha256:[a-f0-9]{64}$'), metadata jsonb NOT NULL DEFAULT '{}', observed_at timestamptz NOT NULL,
  UNIQUE(fact_assertion_id,source_artifact_id,evidence_type,locator)
);
CREATE TABLE dependency_resolution (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(), tenant_id uuid NOT NULL REFERENCES tenant(id),
  fact_assertion_id uuid NOT NULL UNIQUE REFERENCES fact_assertion(id) ON DELETE CASCADE,
  package_registry_id uuid NOT NULL REFERENCES package_registry(id), resolution_source text NOT NULL CHECK(resolution_source IN ('LOCKFILE','NPMRC_SCOPE','NPMRC_DEFAULT','NPM_DEFAULT','EXPLICIT_TARBALL','UNKNOWN')),
  requested_spec text NOT NULL, resolved_version text, resolved_artifact_uri text, integrity text, npm_scope text,
  config_path text, custom_registry boolean NOT NULL, lockfile_behavior text NOT NULL CHECK(lockfile_behavior IN ('CONFIGURED_DEFAULT','CUSTOM_PINNED','EXPLICIT_TARBALL','UNKNOWN')),
  visibility text NOT NULL CHECK(visibility IN ('PUBLIC','PRIVATE','UNKNOWN')), observed_at timestamptz NOT NULL,
  CHECK(npm_scope IS NULL OR npm_scope ~ '^@[a-z0-9._~-]+$'),
  CHECK(resolved_artifact_uri IS NULL OR NOT resolved_artifact_uri ~ '^https?://[^/]*@')
);
CREATE FUNCTION validate_dependency_resolution_scope() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE fact_tenant uuid; registry_tenant uuid; registry_visibility text;
BEGIN
 SELECT tenant_id INTO fact_tenant FROM fact_assertion WHERE id=NEW.fact_assertion_id;
 IF fact_tenant IS DISTINCT FROM NEW.tenant_id THEN RAISE EXCEPTION 'dependency resolution tenant must match fact tenant'; END IF;
 SELECT tenant_id,visibility INTO registry_tenant,registry_visibility FROM package_registry WHERE id=NEW.package_registry_id;
 IF registry_tenant IS NOT NULL AND registry_tenant IS DISTINCT FROM NEW.tenant_id THEN RAISE EXCEPTION 'package registry is outside tenant scope'; END IF;
 IF registry_visibility='PRIVATE' AND registry_tenant IS NULL THEN RAISE EXCEPTION 'private registry must be tenant scoped'; END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER trg_validate_dependency_resolution_scope BEFORE INSERT OR UPDATE ON dependency_resolution FOR EACH ROW EXECUTE FUNCTION validate_dependency_resolution_scope();
CREATE FUNCTION require_fact_evidence() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN IF NOT EXISTS(SELECT 1 FROM evidence WHERE fact_assertion_id=NEW.id) THEN RAISE EXCEPTION 'fact_assertion % must have evidence',NEW.id; END IF; RETURN NEW; END $$;
CREATE CONSTRAINT TRIGGER trg_require_fact_evidence AFTER INSERT OR UPDATE ON fact_assertion DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION require_fact_evidence();

CREATE TABLE assessment (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(), tenant_id uuid REFERENCES tenant(id), subject_entity_id uuid NOT NULL REFERENCES entity(id) ON DELETE CASCADE,
  assessment_type text NOT NULL, dimension text NOT NULL, score numeric(8,4), categorical_value text, confidence numeric(5,4) NOT NULL CHECK(confidence BETWEEN 0 AND 1),
  method text NOT NULL, method_version text NOT NULL, rationale text NOT NULL, query_snapshot_key text,
  status text NOT NULL DEFAULT 'CURRENT' CHECK(status IN ('CURRENT','SUPERSEDED','WITHDRAWN')), valid_from timestamptz NOT NULL DEFAULT now(), valid_to timestamptz, created_at timestamptz NOT NULL DEFAULT now(),
  CHECK((score IS NOT NULL)<>(categorical_value IS NOT NULL))
);
CREATE TABLE assessment_input(tenant_id uuid REFERENCES tenant(id),assessment_id uuid NOT NULL REFERENCES assessment(id) ON DELETE CASCADE,fact_assertion_id uuid NOT NULL REFERENCES fact_assertion(id),PRIMARY KEY(assessment_id,fact_assertion_id));
CREATE TABLE recommendation (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(), tenant_id uuid REFERENCES tenant(id), subject_entity_id uuid NOT NULL REFERENCES entity(id) ON DELETE CASCADE,
  action text NOT NULL CHECK(action IN ('RETAIN','UPGRADE','REMOVE','REPLACE','CONSOLIDATE','REFACTOR','REBUILD','REPLATFORM','RETIRE','INVESTIGATE')),
  target_entity_id uuid REFERENCES entity(id), title text NOT NULL, rationale text NOT NULL, confidence numeric(5,4) NOT NULL CHECK(confidence BETWEEN 0 AND 1),
  method_version text NOT NULL, estimated_effort text CHECK(estimated_effort IN ('LOW','MEDIUM','HIGH','UNKNOWN')), expected_benefit jsonb NOT NULL DEFAULT '{}',
  counter_signals jsonb NOT NULL DEFAULT '[]' CHECK(jsonb_typeof(counter_signals)='array'), status text NOT NULL DEFAULT 'PROPOSED' CHECK(status IN ('PROPOSED','ACCEPTED','REJECTED','PLANNED','IN_PROGRESS','COMPLETED','DISMISSED')),
  created_by text NOT NULL, created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE recommendation_evidence(tenant_id uuid REFERENCES tenant(id),recommendation_id uuid NOT NULL REFERENCES recommendation(id) ON DELETE CASCADE,fact_assertion_id uuid NOT NULL REFERENCES fact_assertion(id),PRIMARY KEY(recommendation_id,fact_assertion_id));
CREATE TABLE recommendation_review(id uuid PRIMARY KEY DEFAULT gen_random_uuid(),tenant_id uuid NOT NULL REFERENCES tenant(id),recommendation_id uuid NOT NULL REFERENCES recommendation(id) ON DELETE CASCADE,from_status text NOT NULL,to_status text NOT NULL,actor_key text NOT NULL,rationale text,created_at timestamptz NOT NULL DEFAULT now());

CREATE TABLE projection_outbox (
 id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY, tenant_id uuid REFERENCES tenant(id), aggregate_type text NOT NULL CHECK(aggregate_type IN ('ENTITY','FACT','ASSESSMENT','RECOMMENDATION','IDENTITY_ASSERTION')),
 aggregate_id uuid NOT NULL, operation text NOT NULL CHECK(operation IN ('UPSERT','CLOSE','DELETE')), dedupe_key text NOT NULL UNIQUE,
 payload jsonb NOT NULL DEFAULT '{}', created_at timestamptz NOT NULL DEFAULT now(), available_at timestamptz NOT NULL DEFAULT now(), leased_by text, leased_until timestamptz, processed_at timestamptz,
 attempt integer NOT NULL DEFAULT 0 CHECK(attempt>=0), last_error jsonb
);
CREATE TABLE dead_letter(id uuid PRIMARY KEY DEFAULT gen_random_uuid(),tenant_id uuid REFERENCES tenant(id),source_kind text NOT NULL,source_id text NOT NULL,error_class text NOT NULL,error_detail jsonb NOT NULL,replay_metadata jsonb NOT NULL DEFAULT '{}',failed_at timestamptz NOT NULL DEFAULT now(),replayed_at timestamptz,replay_run_id uuid REFERENCES ingest_run(id));
CREATE TABLE freshness_state(id uuid PRIMARY KEY DEFAULT gen_random_uuid(),tenant_id uuid REFERENCES tenant(id),ingest_target_id uuid NOT NULL REFERENCES ingest_target(id) ON DELETE CASCADE,expected_by timestamptz,last_observed_at timestamptz,last_source_revision text,status text NOT NULL CHECK(status IN ('FRESH','STALE','UNKNOWN','ERROR')),limitations jsonb NOT NULL DEFAULT '[]',updated_at timestamptz NOT NULL DEFAULT now(),UNIQUE(ingest_target_id));

CREATE VIEW current_fact WITH (security_invoker=true) AS SELECT * FROM (
 SELECT f.*,row_number() OVER(PARTITION BY f.tenant_id,f.logical_key ORDER BY f.system_from DESC,f.id DESC) AS current_rank
 FROM fact_assertion f WHERE f.system_to IS NULL
) ranked WHERE current_rank=1;
CREATE VIEW current_relationship WITH (security_invoker=true) AS SELECT f.id fact_assertion_id,f.tenant_id,f.subject_entity_id source_entity_id,f.predicate relationship_type,
 f.object_entity_id target_entity_id,f.confidence,f.assertion_class,f.properties,f.effective_from,f.effective_to,f.observed_at,f.source_snapshot_id
 FROM current_fact f JOIN predicate_definition p ON p.predicate=f.predicate WHERE p.projects_as_edge AND f.object_entity_id IS NOT NULL;

CREATE FUNCTION publish_source_snapshot(p_snapshot_id uuid) RETURNS void LANGUAGE plpgsql AS $$
DECLARE s source_snapshot%ROWTYPE;
BEGIN
 SELECT * INTO s FROM source_snapshot WHERE id=p_snapshot_id FOR UPDATE;
 IF NOT FOUND THEN RAISE EXCEPTION 'source snapshot % not found',p_snapshot_id; END IF;
 IF s.status<>'STAGED' THEN RAISE EXCEPTION 'source snapshot % is not staged',p_snapshot_id; END IF;
 IF s.completeness='COMPLETE' THEN
  WITH closed AS (
   UPDATE fact_assertion f SET system_to=now() FROM source_snapshot old
    WHERE f.source_snapshot_id=old.id AND old.ingest_target_id=s.ingest_target_id AND old.extractor_key=s.extractor_key
    AND old.extractor_version=s.extractor_version AND old.id<>s.id AND f.system_to IS NULL
    RETURNING f.id,f.tenant_id
  )
  INSERT INTO projection_outbox(tenant_id,aggregate_type,aggregate_id,operation,dedupe_key,payload)
  SELECT closed.tenant_id,'FACT',closed.id,'CLOSE','snapshot:'||p_snapshot_id::text||':close:'||closed.id::text,
   jsonb_build_object('closed_by_source_snapshot_id',p_snapshot_id)
  FROM closed ON CONFLICT(dedupe_key) DO NOTHING;
 END IF;
 UPDATE source_snapshot SET status='PUBLISHED',published_at=now() WHERE id=p_snapshot_id;
 INSERT INTO projection_outbox(tenant_id,aggregate_type,aggregate_id,operation,dedupe_key,payload)
 SELECT f.tenant_id,'FACT',f.id,'UPSERT','snapshot:'||p_snapshot_id::text||':fact:'||f.id::text,jsonb_build_object('source_snapshot_id',p_snapshot_id)
 FROM fact_assertion f WHERE f.source_snapshot_id=p_snapshot_id ON CONFLICT(dedupe_key) DO NOTHING;
END $$;

CREATE INDEX idx_ingest_run_claim ON ingest_run(status,available_at,lease_expires_at);
CREATE INDEX idx_ingest_item_claim ON ingest_item(status,available_at,lease_expires_at);
CREATE INDEX idx_ingest_target_due ON ingest_target(enabled,next_due_at,priority);
CREATE INDEX idx_entity_type_key ON entity(namespace,entity_type,canonical_key);
CREATE INDEX idx_entity_properties_gin ON entity USING gin(properties);
CREATE INDEX idx_package_registry_origin ON package_registry(ecosystem,normalized_origin_uri);
CREATE INDEX idx_package_registry_identity_purl ON package_registry_identity(purl,package_registry_id);
CREATE INDEX idx_fact_subject_predicate ON fact_assertion(subject_entity_id,predicate,system_to);
CREATE INDEX idx_fact_snapshot ON fact_assertion(source_snapshot_id);
CREATE INDEX idx_fact_logical_current ON fact_assertion(tenant_id,logical_key) WHERE system_to IS NULL;
CREATE INDEX idx_evidence_fact ON evidence(fact_assertion_id);
CREATE INDEX idx_assessment_subject ON assessment(subject_entity_id,assessment_type,dimension,status);
CREATE INDEX idx_recommendation_subject ON recommendation(subject_entity_id,status);
CREATE INDEX idx_projection_outbox_claim ON projection_outbox(processed_at,available_at,leased_until);

ALTER TABLE tenant ENABLE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON tenant USING(id=stackgraph_current_tenant_id()) WITH CHECK(id=stackgraph_current_tenant_id());
DO $$ DECLARE t text; BEGIN FOREACH t IN ARRAY ARRAY[
 'source_system','connector_account','package_registry','package_registry_scope','ingest_target','ingest_cursor','webhook_delivery','ingest_run','ingest_item','source_artifact','raw_observation','source_snapshot','entity','entity_identity','package_registry_identity','entity_alias','identity_assertion','identity_assertion_review','fact_assertion','evidence','dependency_resolution','assessment','assessment_input','recommendation','recommendation_evidence','recommendation_review','projection_outbox','dead_letter','freshness_state'
] LOOP EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY',t); EXECUTE format('CREATE POLICY tenant_isolation ON %I USING (tenant_id IS NULL OR tenant_id=stackgraph_current_tenant_id()) WITH CHECK (tenant_id=stackgraph_current_tenant_id())',t); END LOOP; END $$;
COMMIT;
