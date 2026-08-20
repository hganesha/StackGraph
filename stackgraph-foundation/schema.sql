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
END; $$;
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
END; $$;
CREATE TRIGGER trg_validate_dependency_resolution_scope BEFORE INSERT OR UPDATE ON dependency_resolution FOR EACH ROW EXECUTE FUNCTION validate_dependency_resolution_scope();
CREATE FUNCTION require_fact_evidence() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN IF NOT EXISTS(SELECT 1 FROM evidence WHERE fact_assertion_id=NEW.id) THEN RAISE EXCEPTION 'fact_assertion % must have evidence',NEW.id; END IF; RETURN NEW; END; $$;
CREATE CONSTRAINT TRIGGER trg_require_fact_evidence AFTER INSERT OR UPDATE ON fact_assertion DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION require_fact_evidence();

CREATE TABLE package_api_surface (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(), tenant_id uuid REFERENCES tenant(id), package_version_entity_id uuid NOT NULL REFERENCES entity(id) ON DELETE CASCADE,
  ecosystem text NOT NULL CHECK(ecosystem IN ('npm','pypi')), artifact_checksum text NOT NULL CHECK(artifact_checksum ~ '^sha256:[a-f0-9]{64}$'),
  analyzer_key text NOT NULL, analyzer_version text NOT NULL, analysis_fingerprint text NOT NULL CHECK(analysis_fingerprint ~ '^sha256:[a-f0-9]{64}$'),
  public_symbol_count integer NOT NULL CHECK(public_symbol_count>=0), symbols jsonb NOT NULL DEFAULT '[]' CHECK(jsonb_typeof(symbols)='array'),
  completeness text NOT NULL CHECK(completeness IN ('COMPLETE','PARTIAL')), limitations jsonb NOT NULL DEFAULT '[]' CHECK(jsonb_typeof(limitations)='array'),
  stats jsonb NOT NULL DEFAULT '{}' CHECK(jsonb_typeof(stats)='object'), analyzed_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE NULLS NOT DISTINCT(tenant_id,analysis_fingerprint),
  UNIQUE NULLS NOT DISTINCT(tenant_id,package_version_entity_id,artifact_checksum,analyzer_key,analyzer_version)
);
CREATE TABLE dependency_usage_summary (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(), tenant_id uuid NOT NULL REFERENCES tenant(id), source_snapshot_id uuid NOT NULL REFERENCES source_snapshot(id) ON DELETE CASCADE,
  dependency_fact_assertion_id uuid NOT NULL UNIQUE REFERENCES fact_assertion(id) ON DELETE CASCADE, declared boolean NOT NULL, resolved boolean NOT NULL,
  referenced boolean NOT NULL, static_reachability text NOT NULL CHECK(static_reachability IN ('OBSERVED','NOT_OBSERVED','UNKNOWN')),
  runtime_observed text NOT NULL CHECK(runtime_observed IN ('OBSERVED','NOT_OBSERVED','UNKNOWN')), reference_count integer NOT NULL CHECK(reference_count>=0),
  referenced_symbols jsonb NOT NULL DEFAULT '[]' CHECK(jsonb_typeof(referenced_symbols)='array'), source_files_scanned integer NOT NULL CHECK(source_files_scanned>=0),
  limitations jsonb NOT NULL DEFAULT '[]' CHECK(jsonb_typeof(limitations)='array'), analysis_fingerprint text NOT NULL CHECK(analysis_fingerprint ~ '^sha256:[a-f0-9]{64}$'),
  created_at timestamptz NOT NULL DEFAULT now()
);

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

CREATE TABLE ai_prompt_template (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(), tenant_id uuid REFERENCES tenant(id),
  prompt_key text NOT NULL CHECK(prompt_key ~ '^[a-z][a-z0-9_.-]{2,127}$'), version text NOT NULL CHECK(version ~ '^[A-Za-z0-9][A-Za-z0-9_.+-]{0,63}$'),
  status text NOT NULL DEFAULT 'DRAFT' CHECK(status IN ('DRAFT','ACTIVE','RETIRED')),
  messages jsonb NOT NULL CHECK(jsonb_typeof(messages)='array' AND jsonb_array_length(messages)>0), input_variables text[] NOT NULL DEFAULT '{}',
  output_schema jsonb CHECK(output_schema IS NULL OR jsonb_typeof(output_schema)='object'), model_parameters jsonb NOT NULL DEFAULT '{}' CHECK(jsonb_typeof(model_parameters)='object'),
  metadata jsonb NOT NULL DEFAULT '{}' CHECK(jsonb_typeof(metadata)='object'), content_hash text NOT NULL CHECK(content_hash ~ '^sha256:[a-f0-9]{64}$'),
  created_by text NOT NULL, created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE NULLS NOT DISTINCT(tenant_id,prompt_key,version)
);
CREATE UNIQUE INDEX uq_ai_prompt_active_global ON ai_prompt_template(prompt_key) WHERE tenant_id IS NULL AND status='ACTIVE';
CREATE UNIQUE INDEX uq_ai_prompt_active_tenant ON ai_prompt_template(tenant_id,prompt_key) WHERE tenant_id IS NOT NULL AND status='ACTIVE';
CREATE INDEX idx_ai_prompt_lookup ON ai_prompt_template(tenant_id,prompt_key,status,created_at DESC);

CREATE TABLE ai_model_invocation (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(), tenant_id uuid REFERENCES tenant(id), prompt_template_id uuid REFERENCES ai_prompt_template(id),
  prompt_key text NOT NULL CHECK(prompt_key ~ '^[a-z][a-z0-9_.-]{2,127}$'), prompt_version text NOT NULL,
  prompt_content_hash text NOT NULL CHECK(prompt_content_hash ~ '^sha256:[a-f0-9]{64}$'), input_fingerprint text NOT NULL CHECK(input_fingerprint ~ '^sha256:[a-f0-9]{64}$'),
  provider text NOT NULL, requested_model text NOT NULL, resolved_model text, provider_request_id text, policy_version text,
  status text NOT NULL DEFAULT 'PENDING' CHECK(status IN ('PENDING','SUCCEEDED','FAILED','CANCELLED')), finish_reason text,
  input_tokens integer CHECK(input_tokens IS NULL OR input_tokens>=0), output_tokens integer CHECK(output_tokens IS NULL OR output_tokens>=0), total_tokens integer CHECK(total_tokens IS NULL OR total_tokens>=0),
  actual_cost_usd numeric(16,8) CHECK(actual_cost_usd IS NULL OR actual_cost_usd>=0), duration_ms integer CHECK(duration_ms IS NULL OR duration_ms>=0),
  error_code text, error_detail jsonb CHECK(error_detail IS NULL OR jsonb_typeof(error_detail)='object'), metadata jsonb NOT NULL DEFAULT '{}' CHECK(jsonb_typeof(metadata)='object'),
  started_at timestamptz NOT NULL DEFAULT now(), completed_at timestamptz
);
CREATE INDEX idx_ai_invocation_tenant_started ON ai_model_invocation(tenant_id,started_at DESC);
CREATE INDEX idx_ai_invocation_fingerprint ON ai_model_invocation(tenant_id,input_fingerprint,status);

CREATE TABLE capability_taxonomy_version (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),tenant_id uuid REFERENCES tenant(id),taxonomy_key text NOT NULL,version text NOT NULL,
 status text NOT NULL CHECK(status IN ('DRAFT','ACTIVE','RETIRED')),name text NOT NULL,description text NOT NULL,
 content_hash text NOT NULL CHECK(content_hash ~ '^sha256:[a-f0-9]{64}$'),metadata jsonb NOT NULL DEFAULT '{}',created_by text NOT NULL,
 created_at timestamptz NOT NULL DEFAULT now(),updated_at timestamptz NOT NULL DEFAULT now(),UNIQUE NULLS NOT DISTINCT(tenant_id,taxonomy_key,version)
);
CREATE UNIQUE INDEX uq_capability_taxonomy_active_global ON capability_taxonomy_version(taxonomy_key) WHERE tenant_id IS NULL AND status='ACTIVE';
CREATE UNIQUE INDEX uq_capability_taxonomy_active_tenant ON capability_taxonomy_version(tenant_id,taxonomy_key) WHERE tenant_id IS NOT NULL AND status='ACTIVE';
CREATE TABLE capability_definition (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),taxonomy_version_id uuid NOT NULL REFERENCES capability_taxonomy_version(id) ON DELETE CASCADE,
 capability_key text NOT NULL,name text NOT NULL,description text NOT NULL,parent_capability_key text,aliases jsonb NOT NULL DEFAULT '[]',metadata jsonb NOT NULL DEFAULT '{}',
 UNIQUE(taxonomy_version_id,capability_key)
);
CREATE TABLE capability_mapping (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),taxonomy_version_id uuid NOT NULL REFERENCES capability_taxonomy_version(id) ON DELETE CASCADE,
 capability_definition_id uuid NOT NULL REFERENCES capability_definition(id) ON DELETE CASCADE,ecosystem text NOT NULL CHECK(ecosystem IN ('npm','pypi')),
 package_name text NOT NULL,symbol_pattern text,confidence numeric(5,4) NOT NULL CHECK(confidence BETWEEN 0 AND 1),rationale text NOT NULL,evidence jsonb NOT NULL DEFAULT '{}',
 UNIQUE NULLS NOT DISTINCT(taxonomy_version_id,ecosystem,package_name,symbol_pattern,capability_definition_id)
);
CREATE INDEX idx_capability_mapping_lookup ON capability_mapping(taxonomy_version_id,ecosystem,package_name);
CREATE TABLE capability_inference (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),tenant_id uuid NOT NULL REFERENCES tenant(id),repository_entity_id uuid NOT NULL REFERENCES entity(id) ON DELETE CASCADE,
 subject_entity_id uuid NOT NULL REFERENCES entity(id) ON DELETE CASCADE,capability_definition_id uuid NOT NULL REFERENCES capability_definition(id),source_revision text NOT NULL,
 assertion_class text NOT NULL CHECK(assertion_class IN ('CURATED','INFERRED')),confidence numeric(5,4) NOT NULL CHECK(confidence BETWEEN 0 AND 1),
 confidence_band text NOT NULL CHECK(confidence_band IN ('LOW','MEDIUM','HIGH')),supporting_fact_ids uuid[] NOT NULL CHECK(cardinality(supporting_fact_ids)>0),counter_evidence_fact_ids uuid[] NOT NULL DEFAULT '{}',
 taxonomy_version_id uuid NOT NULL REFERENCES capability_taxonomy_version(id),analyzer_key text NOT NULL,analyzer_version text NOT NULL,model_invocation_id uuid REFERENCES ai_model_invocation(id),
 model_provider text,model_name text,policy_version text,input_fingerprint text NOT NULL CHECK(input_fingerprint ~ '^sha256:[a-f0-9]{64}$'),
 analysis_fingerprint text NOT NULL CHECK(analysis_fingerprint ~ '^sha256:[a-f0-9]{64}$'),rationale text NOT NULL,
 review_state text NOT NULL DEFAULT 'UNREVIEWED' CHECK(review_state IN ('UNREVIEWED','CONFIRMED','REJECTED')),version integer NOT NULL DEFAULT 1 CHECK(version>0),
 stale_at timestamptz,created_at timestamptz NOT NULL DEFAULT now(),updated_at timestamptz NOT NULL DEFAULT now(),UNIQUE(tenant_id,analysis_fingerprint)
);
CREATE INDEX idx_capability_inference_repository ON capability_inference(tenant_id,repository_entity_id,source_revision,review_state);
CREATE INDEX idx_capability_inference_subject ON capability_inference(subject_entity_id,capability_definition_id);
CREATE TABLE capability_inference_review (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),tenant_id uuid NOT NULL REFERENCES tenant(id),capability_inference_id uuid NOT NULL REFERENCES capability_inference(id) ON DELETE CASCADE,
 decision text NOT NULL CHECK(decision IN ('CONFIRM','REJECT')),rationale text NOT NULL,reviewer_actor_key text NOT NULL,prior_version integer NOT NULL CHECK(prior_version>0),
 resulting_version integer NOT NULL CHECK(resulting_version=prior_version+1),reviewed_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE duplicate_capability_candidate (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),tenant_id uuid NOT NULL REFERENCES tenant(id),repository_entity_id uuid NOT NULL REFERENCES entity(id) ON DELETE CASCADE,
 capability_definition_id uuid NOT NULL REFERENCES capability_definition(id),source_revision text NOT NULL,dependency_entity_ids uuid[] NOT NULL CHECK(cardinality(dependency_entity_ids)>=2),
 capability_inference_ids uuid[] NOT NULL CHECK(cardinality(capability_inference_ids)>=2),supporting_fact_ids uuid[] NOT NULL CHECK(cardinality(supporting_fact_ids)>=2),
 confidence numeric(5,4) NOT NULL CHECK(confidence BETWEEN 0 AND 1),analysis_fingerprint text NOT NULL CHECK(analysis_fingerprint ~ '^sha256:[a-f0-9]{64}$'),
 summary text NOT NULL,limitations jsonb NOT NULL DEFAULT '[]',review_state text NOT NULL DEFAULT 'UNREVIEWED' CHECK(review_state IN ('UNREVIEWED','CONFIRMED','REJECTED')),
 version integer NOT NULL DEFAULT 1 CHECK(version>0),stale_at timestamptz,created_at timestamptz NOT NULL DEFAULT now(),updated_at timestamptz NOT NULL DEFAULT now(),UNIQUE(tenant_id,analysis_fingerprint)
);
CREATE INDEX idx_duplicate_capability_repository ON duplicate_capability_candidate(tenant_id,repository_entity_id,source_revision,review_state);
CREATE TABLE duplicate_capability_candidate_review (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),tenant_id uuid NOT NULL REFERENCES tenant(id),duplicate_capability_candidate_id uuid NOT NULL REFERENCES duplicate_capability_candidate(id) ON DELETE CASCADE,
 decision text NOT NULL CHECK(decision IN ('CONFIRM','REJECT')),rationale text NOT NULL,reviewer_actor_key text NOT NULL,prior_version integer NOT NULL CHECK(prior_version>0),
 resulting_version integer NOT NULL CHECK(resulting_version=prior_version+1),reviewed_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE intelligence_job (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),tenant_id uuid NOT NULL REFERENCES tenant(id),repository_entity_id uuid NOT NULL REFERENCES entity(id) ON DELETE CASCADE,
 source_snapshot_id uuid NOT NULL REFERENCES source_snapshot(id) ON DELETE CASCADE,source_revision text NOT NULL,job_kind text NOT NULL CHECK(job_kind IN ('REPOSITORY_MODERNIZATION')),
 status text NOT NULL DEFAULT 'PENDING' CHECK(status IN ('PENDING','RUNNING','SUCCEEDED','FAILED')),available_at timestamptz NOT NULL DEFAULT now(),leased_by text,leased_until timestamptz,
 attempt integer NOT NULL DEFAULT 0 CHECK(attempt>=0),max_attempts integer NOT NULL DEFAULT 5 CHECK(max_attempts>0),last_error jsonb,created_at timestamptz NOT NULL DEFAULT now(),
 started_at timestamptz,completed_at timestamptz,updated_at timestamptz NOT NULL DEFAULT now(),configuration_fingerprint text NOT NULL DEFAULT 'snapshot-v1',
 UNIQUE(tenant_id,repository_entity_id,source_revision,job_kind,configuration_fingerprint)
);
CREATE TABLE modernization_candidate (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),tenant_id uuid NOT NULL REFERENCES tenant(id),repository_entity_id uuid NOT NULL REFERENCES entity(id) ON DELETE CASCADE,
 source_revision text NOT NULL,duplicate_capability_candidate_id uuid REFERENCES duplicate_capability_candidate(id) ON DELETE CASCADE,capability_definition_id uuid REFERENCES capability_definition(id),
 candidate_kind text NOT NULL CHECK(candidate_kind IN ('DEPENDENCY_CONSOLIDATION','INTERNAL_DUPLICATION','VENDORED_DUPLICATION','NATIVE_REPLACEMENT')),
 subject_entity_ids uuid[] NOT NULL CHECK(cardinality(subject_entity_ids)>0),confidence numeric(5,4) NOT NULL CHECK(confidence BETWEEN 0 AND 1),summary text NOT NULL,
 supporting_fact_ids uuid[] NOT NULL CHECK(cardinality(supporting_fact_ids)>0),counter_evidence_fact_ids uuid[] NOT NULL DEFAULT '{}',source_locations jsonb NOT NULL DEFAULT '[]',validation_gaps jsonb NOT NULL DEFAULT '[]',
 analyzer_key text NOT NULL,analyzer_version text NOT NULL,input_fingerprint text NOT NULL CHECK(input_fingerprint ~ '^sha256:[a-f0-9]{64}$'),analysis_fingerprint text NOT NULL CHECK(analysis_fingerprint ~ '^sha256:[a-f0-9]{64}$'),
 review_state text NOT NULL DEFAULT 'UNREVIEWED' CHECK(review_state IN ('UNREVIEWED','CONFIRMED','REJECTED')),version integer NOT NULL DEFAULT 1 CHECK(version>0),stale_at timestamptz,
 source_code_unit_ids uuid[] NOT NULL DEFAULT '{}',created_at timestamptz NOT NULL DEFAULT now(),updated_at timestamptz NOT NULL DEFAULT now(),UNIQUE(tenant_id,analysis_fingerprint)
);
CREATE TABLE modernization_option (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),tenant_id uuid NOT NULL REFERENCES tenant(id),modernization_candidate_id uuid NOT NULL REFERENCES modernization_candidate(id) ON DELETE CASCADE,
 option_kind text NOT NULL CHECK(option_kind IN ('NATIVE','INTERNAL','UPGRADE','PACKAGE')),canonical_key text NOT NULL,name text NOT NULL,target_entity_id uuid REFERENCES entity(id),
 compatibility text NOT NULL CHECK(compatibility IN ('OBSERVED','COMPATIBLE','UNKNOWN','INCOMPATIBLE')),rank integer NOT NULL CHECK(rank>0),score numeric(7,4) NOT NULL CHECK(score BETWEEN 0 AND 1),
 score_components jsonb NOT NULL,rationale text NOT NULL,tradeoffs jsonb NOT NULL DEFAULT '[]',disqualifiers jsonb NOT NULL DEFAULT '[]',validation_gaps jsonb NOT NULL DEFAULT '[]',
 supporting_fact_ids uuid[] NOT NULL DEFAULT '{}',created_at timestamptz NOT NULL DEFAULT now(),UNIQUE(modernization_candidate_id,canonical_key)
);
CREATE TABLE modernization_recommendation (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),tenant_id uuid NOT NULL REFERENCES tenant(id),repository_entity_id uuid NOT NULL REFERENCES entity(id) ON DELETE CASCADE,
 modernization_candidate_id uuid NOT NULL REFERENCES modernization_candidate(id) ON DELETE CASCADE,selected_option_id uuid REFERENCES modernization_option(id),source_revision text NOT NULL,
 action text NOT NULL CHECK(action IN ('CONSOLIDATE','REPLACE','UPGRADE','REFACTOR','INVESTIGATE')),objective text NOT NULL,title text NOT NULL,rationale text NOT NULL,
 confidence numeric(5,4) NOT NULL CHECK(confidence BETWEEN 0 AND 1),estimated_effort text NOT NULL CHECK(estimated_effort IN ('LOW','MEDIUM','HIGH','UNKNOWN')),
 affected_call_sites integer NOT NULL CHECK(affected_call_sites>=0),affected_files integer NOT NULL CHECK(affected_files>=0),validation_gaps jsonb NOT NULL DEFAULT '[]',
 migration_plan jsonb NOT NULL,rollback_plan jsonb NOT NULL,supporting_fact_ids uuid[] NOT NULL CHECK(cardinality(supporting_fact_ids)>0),counter_evidence_fact_ids uuid[] NOT NULL DEFAULT '{}',
 counter_signals jsonb NOT NULL DEFAULT '[]',policy_version text NOT NULL,input_fingerprint text NOT NULL CHECK(input_fingerprint ~ '^sha256:[a-f0-9]{64}$'),
 analysis_fingerprint text NOT NULL CHECK(analysis_fingerprint ~ '^sha256:[a-f0-9]{64}$'),review_state text NOT NULL DEFAULT 'UNREVIEWED' CHECK(review_state IN ('UNREVIEWED','ACCEPTED','REJECTED','DISMISSED')),
 version integer NOT NULL DEFAULT 1 CHECK(version>0),stale_at timestamptz,created_at timestamptz NOT NULL DEFAULT now(),updated_at timestamptz NOT NULL DEFAULT now(),UNIQUE(tenant_id,analysis_fingerprint)
);
CREATE TABLE modernization_recommendation_review (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),tenant_id uuid NOT NULL REFERENCES tenant(id),modernization_recommendation_id uuid NOT NULL REFERENCES modernization_recommendation(id) ON DELETE CASCADE,
 decision text NOT NULL CHECK(decision IN ('ACCEPT','REJECT','DISMISS')),rationale text NOT NULL,reviewer_actor_key text NOT NULL,prior_version integer NOT NULL CHECK(prior_version>0),
 resulting_version integer NOT NULL CHECK(resulting_version=prior_version+1),reviewed_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE code_implementation_summary (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),tenant_id uuid NOT NULL REFERENCES tenant(id),source_snapshot_id uuid NOT NULL REFERENCES source_snapshot(id) ON DELETE CASCADE,
 repository_entity_id uuid NOT NULL REFERENCES entity(id) ON DELETE CASCADE,fact_assertion_id uuid NOT NULL UNIQUE REFERENCES fact_assertion(id) ON DELETE CASCADE,source_revision text NOT NULL,
 language text NOT NULL CHECK(language IN ('python','javascript')),symbol_kind text NOT NULL CHECK(symbol_kind IN ('FUNCTION','CLASS')),qualified_name text NOT NULL,path text NOT NULL,
 line_start integer NOT NULL CHECK(line_start>0),line_end integer NOT NULL CHECK(line_end>=line_start),structural_fingerprint text NOT NULL CHECK(structural_fingerprint ~ '^sha256:[a-f0-9]{64}$'),
 semantic_tokens text[] NOT NULL DEFAULT '{}',dependency_keys text[] NOT NULL DEFAULT '{}',covering_tests text[] NOT NULL DEFAULT '{}',dynamic_signals text[] NOT NULL DEFAULT '{}',
 touchpoints jsonb NOT NULL DEFAULT '[]',vendored boolean NOT NULL DEFAULT false,completeness text NOT NULL CHECK(completeness IN ('COMPLETE','PARTIAL')),limitations jsonb NOT NULL DEFAULT '[]',created_at timestamptz NOT NULL DEFAULT now(),
 UNIQUE(tenant_id,repository_entity_id,source_revision,path,qualified_name,line_start,structural_fingerprint)
);
CREATE TABLE modernization_policy (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),tenant_id uuid NOT NULL REFERENCES tenant(id),policy_key text NOT NULL,version text NOT NULL,status text NOT NULL CHECK(status IN ('DRAFT','ACTIVE','RETIRED')),
 runtime_versions jsonb NOT NULL DEFAULT '{}',allowed_licenses text[] NOT NULL DEFAULT '{}',denied_option_keys text[] NOT NULL DEFAULT '{}',allowed_security_statuses text[] NOT NULL DEFAULT ARRAY['CLEAR','UNKNOWN']::text[],
 required_policy_tags text[] NOT NULL DEFAULT '{}',metadata jsonb NOT NULL DEFAULT '{}',content_hash text NOT NULL CHECK(content_hash ~ '^sha256:[a-f0-9]{64}$'),created_by text NOT NULL,
 created_at timestamptz NOT NULL DEFAULT now(),updated_at timestamptz NOT NULL DEFAULT now(),UNIQUE(tenant_id,policy_key,version)
);
CREATE UNIQUE INDEX uq_modernization_policy_active ON modernization_policy(tenant_id,policy_key) WHERE status='ACTIVE';
CREATE TABLE modernization_internal_component (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),tenant_id uuid NOT NULL REFERENCES tenant(id),component_entity_id uuid NOT NULL REFERENCES entity(id) ON DELETE CASCADE,
 capability_definition_id uuid NOT NULL REFERENCES capability_definition(id),component_key text NOT NULL,version text NOT NULL,status text NOT NULL CHECK(status IN ('APPROVED','DEPRECATED','BLOCKED')),
 api_symbols text[] NOT NULL DEFAULT '{}',runtime_constraints jsonb NOT NULL DEFAULT '{}',behavior_claims jsonb NOT NULL DEFAULT '[]',license text,
 security_status text NOT NULL DEFAULT 'UNKNOWN' CHECK(security_status IN ('CLEAR','WARN','BLOCKED','UNKNOWN')),policy_tags text[] NOT NULL DEFAULT '{}',supporting_fact_ids uuid[] NOT NULL DEFAULT '{}',
 metadata jsonb NOT NULL DEFAULT '{}',created_at timestamptz NOT NULL DEFAULT now(),updated_at timestamptz NOT NULL DEFAULT now(),UNIQUE(tenant_id,component_key,version)
);
CREATE TABLE modernization_option_evaluation (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),tenant_id uuid NOT NULL REFERENCES tenant(id),modernization_option_id uuid NOT NULL UNIQUE REFERENCES modernization_option(id) ON DELETE CASCADE,
 policy_id uuid REFERENCES modernization_policy(id),capability_fit text NOT NULL CHECK(capability_fit IN ('PASS','FAIL','UNKNOWN')),api_fit text NOT NULL CHECK(api_fit IN ('PASS','FAIL','UNKNOWN')),
 behavior_fit text NOT NULL CHECK(behavior_fit IN ('PASS','FAIL','UNKNOWN')),runtime_fit text NOT NULL CHECK(runtime_fit IN ('PASS','FAIL','UNKNOWN')),license_fit text NOT NULL CHECK(license_fit IN ('PASS','FAIL','UNKNOWN')),
 security_fit text NOT NULL CHECK(security_fit IN ('PASS','FAIL','UNKNOWN')),policy_fit text NOT NULL CHECK(policy_fit IN ('PASS','FAIL','UNKNOWN')),eligible boolean NOT NULL,
 evidence jsonb NOT NULL DEFAULT '{}',disqualifiers jsonb NOT NULL DEFAULT '[]',unknowns jsonb NOT NULL DEFAULT '[]',evaluated_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE modernization_impact (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),tenant_id uuid NOT NULL REFERENCES tenant(id),modernization_candidate_id uuid NOT NULL UNIQUE REFERENCES modernization_candidate(id) ON DELETE CASCADE,
 affected_call_sites integer NOT NULL CHECK(affected_call_sites>=0),affected_files integer NOT NULL CHECK(affected_files>=0),covered_call_sites integer NOT NULL CHECK(covered_call_sites>=0),
 uncovered_call_sites integer NOT NULL CHECK(uncovered_call_sites>=0),affected_test_files text[] NOT NULL DEFAULT '{}',dynamic_signals text[] NOT NULL DEFAULT '{}',
 configuration_touchpoints jsonb NOT NULL DEFAULT '[]',build_touchpoints jsonb NOT NULL DEFAULT '[]',deployment_touchpoints jsonb NOT NULL DEFAULT '[]',evidence_locations jsonb NOT NULL DEFAULT '[]',
 confidence numeric(5,4) NOT NULL CHECK(confidence BETWEEN 0 AND 1),effort_points integer NOT NULL CHECK(effort_points>=0),effort_model_version text NOT NULL,limitations jsonb NOT NULL DEFAULT '[]',
 created_at timestamptz NOT NULL DEFAULT now(),updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE modernization_validation_outcome (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),tenant_id uuid NOT NULL REFERENCES tenant(id),modernization_recommendation_id uuid NOT NULL REFERENCES modernization_recommendation(id) ON DELETE CASCADE,
 validation_status text NOT NULL CHECK(validation_status IN ('SUCCEEDED','PARTIAL','FAILED')),actual_call_sites integer CHECK(actual_call_sites IS NULL OR actual_call_sites>=0),
 actual_files integer CHECK(actual_files IS NULL OR actual_files>=0),actual_effort text CHECK(actual_effort IS NULL OR actual_effort IN ('LOW','MEDIUM','HIGH','UNKNOWN')),
 successful_checks text[] NOT NULL DEFAULT '{}',failed_checks text[] NOT NULL DEFAULT '{}',notes text NOT NULL,reporter_actor_key text NOT NULL,reported_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE modernization_candidate_review (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),tenant_id uuid NOT NULL REFERENCES tenant(id),modernization_candidate_id uuid NOT NULL REFERENCES modernization_candidate(id) ON DELETE CASCADE,
 decision text NOT NULL CHECK(decision IN ('CONFIRM','REJECT')),rationale text NOT NULL,reviewer_actor_key text NOT NULL,prior_version integer NOT NULL CHECK(prior_version>0),
 resulting_version integer NOT NULL CHECK(resulting_version=prior_version+1),reviewed_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE projection_outbox (
 id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY, tenant_id uuid REFERENCES tenant(id), aggregate_type text NOT NULL CHECK(aggregate_type IN ('ENTITY','FACT','ASSESSMENT','RECOMMENDATION','IDENTITY_ASSERTION')),
 aggregate_id uuid NOT NULL, operation text NOT NULL CHECK(operation IN ('UPSERT','CLOSE','DELETE')), dedupe_key text NOT NULL UNIQUE,
 payload jsonb NOT NULL DEFAULT '{}', created_at timestamptz NOT NULL DEFAULT now(), available_at timestamptz NOT NULL DEFAULT now(), leased_by text, leased_until timestamptz, processed_at timestamptz,
 attempt integer NOT NULL DEFAULT 0 CHECK(attempt>=0), last_error jsonb
);
CREATE TABLE dead_letter(id uuid PRIMARY KEY DEFAULT gen_random_uuid(),tenant_id uuid REFERENCES tenant(id),source_kind text NOT NULL,source_id text NOT NULL,error_class text NOT NULL,error_detail jsonb NOT NULL,replay_metadata jsonb NOT NULL DEFAULT '{}',failed_at timestamptz NOT NULL DEFAULT now(),replayed_at timestamptz,replay_run_id uuid REFERENCES ingest_run(id));
CREATE TABLE freshness_state(id uuid PRIMARY KEY DEFAULT gen_random_uuid(),tenant_id uuid REFERENCES tenant(id),ingest_target_id uuid NOT NULL REFERENCES ingest_target(id) ON DELETE CASCADE,expected_by timestamptz,last_observed_at timestamptz,last_source_revision text,status text NOT NULL CHECK(status IN ('FRESH','STALE','UNKNOWN','ERROR')),limitations jsonb NOT NULL DEFAULT '[]',updated_at timestamptz NOT NULL DEFAULT now(),UNIQUE(ingest_target_id));

CREATE TABLE tenant_secret(id uuid PRIMARY KEY DEFAULT gen_random_uuid(),tenant_id uuid NOT NULL REFERENCES tenant(id),secret_kind text NOT NULL CHECK(secret_kind IN ('AI_PROVIDER_KEY')),ciphertext bytea NOT NULL,fingerprint text NOT NULL CHECK(length(fingerprint)=4),created_by text NOT NULL,created_at timestamptz NOT NULL DEFAULT now(),updated_at timestamptz NOT NULL DEFAULT now());
CREATE TABLE tenant_ai_configuration(tenant_id uuid PRIMARY KEY REFERENCES tenant(id),provider text NOT NULL CHECK(provider IN ('openrouter','openai','anthropic')),model text NOT NULL DEFAULT '',credential_secret_id uuid REFERENCES tenant_secret(id) ON DELETE SET NULL,enabled boolean NOT NULL DEFAULT true,test_status text NOT NULL DEFAULT 'NOT_TESTED' CHECK(test_status IN ('NOT_TESTED','SUCCEEDED','FAILED')),tested_at timestamptz,last_error text,updated_by text NOT NULL,created_at timestamptz NOT NULL DEFAULT now(),updated_at timestamptz NOT NULL DEFAULT now());

-- Business Map persistence (migration 009). Catalog rows (function/process/capability) carry a
-- nullable entity_id linking to the canonical BUSINESS-namespace ontology entity; shared groups
-- persist as overlays over map capabilities and a stage span.
CREATE TABLE business_map(id uuid PRIMARY KEY DEFAULT gen_random_uuid(),tenant_id uuid NOT NULL REFERENCES tenant(id),map_key text NOT NULL CHECK(map_key ~ '^[a-z][a-z0-9_.-]{2,127}$'),title text NOT NULL CHECK(title<>''),view_mode text NOT NULL DEFAULT 'VALUE_CHAIN' CHECK(view_mode IN ('VALUE_CHAIN','ORGANIZATION')),template_id text NOT NULL DEFAULT 'porter',status text NOT NULL DEFAULT 'ACTIVE' CHECK(status IN ('DRAFT','ACTIVE','ARCHIVED')),version integer NOT NULL DEFAULT 1 CHECK(version>0),metadata jsonb NOT NULL DEFAULT '{}' CHECK(jsonb_typeof(metadata)='object'),created_by text NOT NULL,created_at timestamptz NOT NULL DEFAULT now(),updated_at timestamptz NOT NULL DEFAULT now(),UNIQUE(tenant_id,map_key));
CREATE TABLE business_map_lane(id uuid PRIMARY KEY DEFAULT gen_random_uuid(),tenant_id uuid NOT NULL REFERENCES tenant(id),business_map_id uuid NOT NULL REFERENCES business_map(id) ON DELETE CASCADE,lane_kind text NOT NULL CHECK(lane_kind IN ('STAGE','ORG_UNIT')),lane_key text NOT NULL CHECK(lane_key<>''),label text NOT NULL CHECK(label<>''),sublabel text NOT NULL DEFAULT '',color text NOT NULL DEFAULT '',gradient text NOT NULL DEFAULT '',icon text NOT NULL DEFAULT '',position integer NOT NULL CHECK(position>=0),created_at timestamptz NOT NULL DEFAULT now(),updated_at timestamptz NOT NULL DEFAULT now(),UNIQUE(business_map_id,lane_kind,lane_key));
CREATE TABLE business_map_function(id uuid PRIMARY KEY DEFAULT gen_random_uuid(),tenant_id uuid NOT NULL REFERENCES tenant(id),business_map_id uuid NOT NULL REFERENCES business_map(id) ON DELETE CASCADE,function_key text NOT NULL CHECK(function_key<>''),entity_id uuid REFERENCES entity(id) ON DELETE SET NULL,name text NOT NULL CHECK(name<>''),description text NOT NULL DEFAULT '',color text NOT NULL DEFAULT '',gradient text NOT NULL DEFAULT '',icon text NOT NULL DEFAULT '',position integer NOT NULL CHECK(position>=0),created_at timestamptz NOT NULL DEFAULT now(),updated_at timestamptz NOT NULL DEFAULT now(),UNIQUE(business_map_id,function_key));
CREATE TABLE business_map_process(id uuid PRIMARY KEY DEFAULT gen_random_uuid(),tenant_id uuid NOT NULL REFERENCES tenant(id),business_map_id uuid NOT NULL REFERENCES business_map(id) ON DELETE CASCADE,business_map_function_id uuid NOT NULL REFERENCES business_map_function(id) ON DELETE CASCADE,process_key text NOT NULL CHECK(process_key<>''),entity_id uuid REFERENCES entity(id) ON DELETE SET NULL,name text NOT NULL CHECK(name<>''),description text NOT NULL DEFAULT '',position integer NOT NULL CHECK(position>=0),created_at timestamptz NOT NULL DEFAULT now(),updated_at timestamptz NOT NULL DEFAULT now(),UNIQUE(business_map_id,process_key));
CREATE TABLE business_map_capability(id uuid PRIMARY KEY DEFAULT gen_random_uuid(),tenant_id uuid NOT NULL REFERENCES tenant(id),business_map_id uuid NOT NULL REFERENCES business_map(id) ON DELETE CASCADE,business_map_process_id uuid NOT NULL REFERENCES business_map_process(id) ON DELETE CASCADE,capability_key text NOT NULL CHECK(capability_key<>''),entity_id uuid REFERENCES entity(id) ON DELETE SET NULL,name text NOT NULL CHECK(name<>''),description text NOT NULL DEFAULT '',tags text[] NOT NULL DEFAULT '{}',kpis text[] NOT NULL DEFAULT '{}',owner text,position integer NOT NULL CHECK(position>=0),created_at timestamptz NOT NULL DEFAULT now(),updated_at timestamptz NOT NULL DEFAULT now(),UNIQUE(business_map_id,capability_key));
CREATE TABLE business_map_placement(id uuid PRIMARY KEY DEFAULT gen_random_uuid(),tenant_id uuid NOT NULL REFERENCES tenant(id),business_map_id uuid NOT NULL REFERENCES business_map(id) ON DELETE CASCADE,business_map_capability_id uuid NOT NULL REFERENCES business_map_capability(id) ON DELETE CASCADE,lane_id uuid REFERENCES business_map_lane(id) ON DELETE SET NULL,source_function_id uuid REFERENCES business_map_function(id) ON DELETE SET NULL,maturity smallint NOT NULL DEFAULT 2 CHECK(maturity BETWEEN 1 AND 5),created_at timestamptz NOT NULL DEFAULT now(),updated_at timestamptz NOT NULL DEFAULT now(),UNIQUE(business_map_id,business_map_capability_id));
CREATE TABLE business_map_shared_group(id uuid PRIMARY KEY DEFAULT gen_random_uuid(),tenant_id uuid NOT NULL REFERENCES tenant(id),business_map_id uuid NOT NULL REFERENCES business_map(id) ON DELETE CASCADE,group_key text NOT NULL CHECK(group_key<>''),name text NOT NULL CHECK(name<>''),description text NOT NULL DEFAULT '',start_lane_id uuid REFERENCES business_map_lane(id) ON DELETE CASCADE,end_lane_id uuid REFERENCES business_map_lane(id) ON DELETE CASCADE,created_at timestamptz NOT NULL DEFAULT now(),updated_at timestamptz NOT NULL DEFAULT now(),UNIQUE(business_map_id,group_key));
CREATE TABLE business_map_shared_group_member(tenant_id uuid NOT NULL REFERENCES tenant(id),shared_group_id uuid NOT NULL REFERENCES business_map_shared_group(id) ON DELETE CASCADE,business_map_capability_id uuid NOT NULL REFERENCES business_map_capability(id) ON DELETE CASCADE,PRIMARY KEY(shared_group_id,business_map_capability_id));
CREATE TABLE business_map_function_assignment(id uuid PRIMARY KEY DEFAULT gen_random_uuid(),tenant_id uuid NOT NULL REFERENCES tenant(id),business_map_id uuid NOT NULL REFERENCES business_map(id) ON DELETE CASCADE,business_map_function_id uuid NOT NULL REFERENCES business_map_function(id) ON DELETE CASCADE,lane_id uuid REFERENCES business_map_lane(id) ON DELETE CASCADE,created_at timestamptz NOT NULL DEFAULT now(),updated_at timestamptz NOT NULL DEFAULT now(),UNIQUE(business_map_id,business_map_function_id));
CREATE TABLE business_map_revision(id uuid PRIMARY KEY DEFAULT gen_random_uuid(),tenant_id uuid NOT NULL REFERENCES tenant(id),business_map_id uuid NOT NULL REFERENCES business_map(id) ON DELETE CASCADE,version integer NOT NULL CHECK(version>0),snapshot jsonb NOT NULL CHECK(jsonb_typeof(snapshot)='object'),actor_key text NOT NULL,created_at timestamptz NOT NULL DEFAULT now(),UNIQUE(business_map_id,version));

-- Tenant administration and operator control (migration 010).
CREATE TABLE tenant_member(id uuid PRIMARY KEY DEFAULT gen_random_uuid(),tenant_id uuid NOT NULL REFERENCES tenant(id),actor_key text NOT NULL CHECK(actor_key<>''),display_name text NOT NULL DEFAULT '',email text NOT NULL DEFAULT '',role text NOT NULL DEFAULT 'view' CHECK(role IN ('view','review','execute','admin')),status text NOT NULL DEFAULT 'INVITED' CHECK(status IN ('INVITED','ACTIVE','SUSPENDED')),created_by text NOT NULL,created_at timestamptz NOT NULL DEFAULT now(),updated_at timestamptz NOT NULL DEFAULT now(),UNIQUE(tenant_id,actor_key));
CREATE TABLE connector(id uuid PRIMARY KEY DEFAULT gen_random_uuid(),tenant_id uuid NOT NULL REFERENCES tenant(id),provider text NOT NULL CHECK(provider IN ('GITHUB_APP','PACKAGE_REGISTRY','DEPS_DEV','OSV','OTHER')),display_name text NOT NULL CHECK(display_name<>''),external_account_key text NOT NULL DEFAULT '',credential_reference text NOT NULL DEFAULT '',scopes text[] NOT NULL DEFAULT '{}',status text NOT NULL DEFAULT 'CONNECTED' CHECK(status IN ('CONNECTED','NEEDS_REAUTH','DISABLED','REVOKED')),last_synced_at timestamptz,last_error text,metadata jsonb NOT NULL DEFAULT '{}' CHECK(jsonb_typeof(metadata)='object'),created_by text NOT NULL,created_at timestamptz NOT NULL DEFAULT now(),updated_at timestamptz NOT NULL DEFAULT now(),UNIQUE(tenant_id,provider,external_account_key));
CREATE TABLE scan_policy(tenant_id uuid PRIMARY KEY REFERENCES tenant(id),cadence text NOT NULL DEFAULT 'DAILY' CHECK(cadence IN ('HOURLY','DAILY','WEEKLY','MANUAL')),enabled boolean NOT NULL DEFAULT true,updated_by text NOT NULL,created_at timestamptz NOT NULL DEFAULT now(),updated_at timestamptz NOT NULL DEFAULT now());
CREATE TABLE rescan_job(id uuid PRIMARY KEY DEFAULT gen_random_uuid(),tenant_id uuid NOT NULL REFERENCES tenant(id),connector_id uuid REFERENCES connector(id) ON DELETE SET NULL,idempotency_key text NOT NULL CHECK(idempotency_key<>''),status text NOT NULL DEFAULT 'PENDING' CHECK(status IN ('PENDING','RUNNING','SUCCEEDED','FAILED')),reason text NOT NULL DEFAULT '',requested_by text NOT NULL,last_error text,created_at timestamptz NOT NULL DEFAULT now(),started_at timestamptz,completed_at timestamptz,updated_at timestamptz NOT NULL DEFAULT now(),UNIQUE(tenant_id,idempotency_key));
CREATE TABLE connector_quota(tenant_id uuid NOT NULL REFERENCES tenant(id),provider text NOT NULL CHECK(provider IN ('GITHUB_APP','PACKAGE_REGISTRY','DEPS_DEV','OSV','OTHER')),used integer NOT NULL DEFAULT 0 CHECK(used>=0),limit_value integer CHECK(limit_value IS NULL OR limit_value>=0),status text NOT NULL DEFAULT 'OK' CHECK(status IN ('OK','THROTTLED','EXHAUSTED')),resets_at timestamptz,backoff_until timestamptz,observed_at timestamptz NOT NULL DEFAULT now(),updated_at timestamptz NOT NULL DEFAULT now(),PRIMARY KEY(tenant_id,provider));
CREATE TABLE admin_audit_log(id uuid PRIMARY KEY DEFAULT gen_random_uuid(),tenant_id uuid NOT NULL REFERENCES tenant(id),actor_key text NOT NULL,action text NOT NULL CHECK(action<>''),target_kind text NOT NULL,target_id text NOT NULL DEFAULT '',detail jsonb NOT NULL DEFAULT '{}' CHECK(jsonb_typeof(detail)='object'),created_at timestamptz NOT NULL DEFAULT now());
CREATE TABLE auth_token_revocation(tenant_id uuid NOT NULL REFERENCES tenant(id) ON DELETE CASCADE,jti uuid NOT NULL,actor_key text NOT NULL CHECK(actor_key<>''),token_type text NOT NULL CHECK(token_type IN ('access','refresh')),expires_at timestamptz NOT NULL,reason text NOT NULL CHECK(reason<>''),revoked_at timestamptz NOT NULL DEFAULT now(),PRIMARY KEY(tenant_id,jti));
CREATE TABLE api_rate_limit_window(tenant_id uuid NOT NULL REFERENCES tenant(id) ON DELETE CASCADE,actor_key text NOT NULL CHECK(actor_key<>''),route_bucket text NOT NULL CHECK(route_bucket IN ('general','ask')),window_started_at timestamptz NOT NULL,request_count integer NOT NULL DEFAULT 1 CHECK(request_count>0),PRIMARY KEY(tenant_id,actor_key,route_bucket,window_started_at));

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
    AND old.id<>s.id AND f.system_to IS NULL
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
END; $$;

CREATE FUNCTION tenant_ai_configuration_fingerprint(
 p_provider text,p_model text,p_secret_id uuid
) RETURNS text LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $$
 SELECT 'sha256:'||encode(digest(convert_to(
  'tenant-ai-v1'||chr(31)||p_provider||chr(31)||p_model||chr(31)||p_secret_id::text,
  'UTF8'
 ),'sha256'),'hex')
$$;

CREATE FUNCTION enqueue_repository_intelligence_on_publish() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF NEW.status='PUBLISHED' AND OLD.status IS DISTINCT FROM NEW.status
    AND NEW.completeness='COMPLETE' AND NEW.extractor_key='repository-dependency-usage' THEN
  INSERT INTO intelligence_job(
   tenant_id,repository_entity_id,source_snapshot_id,source_revision,
   job_kind,configuration_fingerprint
  )
  SELECT NEW.tenant_id,repository.id,NEW.id,NEW.source_revision,'REPOSITORY_MODERNIZATION',
   coalesce(tenant_ai_configuration_fingerprint(
    configuration.provider,configuration.model,configuration.credential_secret_id
   ),'snapshot-v1')
  FROM ingest_target target JOIN entity repository
    ON repository.tenant_id=NEW.tenant_id AND repository.namespace='ENTERPRISE'
   AND repository.entity_type='Repository' AND repository.canonical_key=target.target_key
  LEFT JOIN tenant_ai_configuration configuration
    ON configuration.tenant_id=NEW.tenant_id AND configuration.enabled
   AND configuration.model<>'' AND configuration.credential_secret_id IS NOT NULL
  WHERE target.id=NEW.ingest_target_id
  ON CONFLICT DO NOTHING;
 END IF;
 RETURN NEW;
END; $$;
CREATE TRIGGER source_snapshot_enqueue_repository_intelligence AFTER UPDATE OF status ON source_snapshot
FOR EACH ROW EXECUTE FUNCTION enqueue_repository_intelligence_on_publish();

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
CREATE INDEX idx_package_api_surface_lookup ON package_api_surface(package_version_entity_id,analyzed_at DESC);
CREATE INDEX idx_dependency_usage_snapshot ON dependency_usage_summary(source_snapshot_id,referenced,static_reachability);
CREATE INDEX idx_assessment_subject ON assessment(subject_entity_id,assessment_type,dimension,status);
CREATE INDEX idx_recommendation_subject ON recommendation(subject_entity_id,status);
CREATE INDEX idx_projection_outbox_claim ON projection_outbox(processed_at,available_at,leased_until);
CREATE INDEX idx_intelligence_job_claim ON intelligence_job(status,available_at,leased_until,created_at);
CREATE INDEX idx_modernization_candidate_repository ON modernization_candidate(tenant_id,repository_entity_id,source_revision,review_state);
CREATE INDEX idx_modernization_option_candidate ON modernization_option(modernization_candidate_id,rank);
CREATE INDEX idx_modernization_recommendation_repository ON modernization_recommendation(tenant_id,repository_entity_id,source_revision,review_state);
CREATE INDEX idx_code_implementation_repository ON code_implementation_summary(tenant_id,repository_entity_id,source_revision,path);
CREATE INDEX idx_code_implementation_structure ON code_implementation_summary(tenant_id,structural_fingerprint,source_revision);
CREATE INDEX idx_code_implementation_tokens ON code_implementation_summary USING gin(semantic_tokens);
CREATE INDEX idx_modernization_internal_capability ON modernization_internal_component(tenant_id,capability_definition_id,status);
CREATE INDEX idx_tenant_member_tenant ON tenant_member(tenant_id,role,status);
CREATE INDEX idx_connector_tenant ON connector(tenant_id,status,updated_at DESC);
CREATE INDEX idx_rescan_job_tenant ON rescan_job(tenant_id,created_at DESC,id DESC);
CREATE INDEX idx_admin_audit_log_tenant ON admin_audit_log(tenant_id,created_at DESC,id DESC);
CREATE INDEX idx_auth_token_revocation_expiry ON auth_token_revocation(expires_at);
CREATE INDEX idx_api_rate_limit_window_expiry ON api_rate_limit_window(window_started_at);
CREATE INDEX idx_identity_assertion_review_queue ON identity_assertion(created_at DESC,id DESC) WHERE review_state='POSSIBLE';
CREATE INDEX idx_capability_inference_review_queue ON capability_inference(created_at DESC,id DESC) WHERE review_state='UNREVIEWED';
CREATE INDEX idx_duplicate_capability_review_queue ON duplicate_capability_candidate(created_at DESC,id DESC) WHERE review_state='UNREVIEWED';
CREATE INDEX idx_modernization_candidate_review_queue ON modernization_candidate(created_at DESC,id DESC) WHERE review_state='UNREVIEWED';
CREATE INDEX idx_modernization_recommendation_review_queue ON modernization_recommendation(created_at DESC,id DESC) WHERE review_state='UNREVIEWED';
CREATE INDEX idx_modernization_validation_recommendation ON modernization_validation_outcome(tenant_id,modernization_recommendation_id,reported_at DESC);
CREATE INDEX idx_business_map_tenant ON business_map(tenant_id,status,updated_at DESC);
CREATE INDEX idx_business_map_lane_map ON business_map_lane(tenant_id,business_map_id,lane_kind,position);
CREATE INDEX idx_business_map_function_map ON business_map_function(tenant_id,business_map_id,position);
CREATE INDEX idx_business_map_process_function ON business_map_process(tenant_id,business_map_function_id,position);
CREATE INDEX idx_business_map_capability_process ON business_map_capability(tenant_id,business_map_process_id,position);
CREATE INDEX idx_business_map_capability_entity ON business_map_capability(tenant_id,entity_id) WHERE entity_id IS NOT NULL;
CREATE INDEX idx_business_map_placement_lane ON business_map_placement(tenant_id,business_map_id,lane_id);
CREATE INDEX idx_business_map_shared_group_map ON business_map_shared_group(tenant_id,business_map_id);
CREATE INDEX idx_business_map_assignment_lane ON business_map_function_assignment(tenant_id,lane_id);
CREATE INDEX idx_business_map_revision_map ON business_map_revision(tenant_id,business_map_id,version DESC);

ALTER TABLE tenant ENABLE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON tenant USING(id=stackgraph_current_tenant_id()) WITH CHECK(id=stackgraph_current_tenant_id());
DO $$ DECLARE t text; BEGIN FOREACH t IN ARRAY ARRAY[
 'source_system','connector_account','package_registry','package_registry_scope','ingest_target','ingest_cursor','webhook_delivery','ingest_run','ingest_item','source_artifact','raw_observation','source_snapshot','entity','entity_identity','package_registry_identity','entity_alias','identity_assertion','identity_assertion_review','fact_assertion','evidence','dependency_resolution','package_api_surface','dependency_usage_summary','assessment','assessment_input','recommendation','recommendation_evidence','recommendation_review','ai_prompt_template','ai_model_invocation','capability_taxonomy_version','capability_inference','capability_inference_review','duplicate_capability_candidate','duplicate_capability_candidate_review','intelligence_job','modernization_candidate','modernization_option','modernization_recommendation','modernization_recommendation_review','code_implementation_summary','modernization_policy','modernization_internal_component','modernization_option_evaluation','modernization_impact','modernization_validation_outcome','modernization_candidate_review','projection_outbox','dead_letter','freshness_state','tenant_secret','tenant_ai_configuration','business_map','business_map_lane','business_map_function','business_map_process','business_map_capability','business_map_placement','business_map_shared_group','business_map_shared_group_member','business_map_function_assignment','business_map_revision','tenant_member','connector','scan_policy','rescan_job','connector_quota','admin_audit_log','auth_token_revocation','api_rate_limit_window'
] LOOP EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY',t); EXECUTE format('CREATE POLICY tenant_isolation ON %I USING (tenant_id IS NULL OR tenant_id=stackgraph_current_tenant_id()) WITH CHECK (tenant_id=stackgraph_current_tenant_id())',t); END LOOP; END; $$;
ALTER TABLE capability_definition ENABLE ROW LEVEL SECURITY;
CREATE POLICY capability_definition_visibility ON capability_definition USING(EXISTS(SELECT 1 FROM capability_taxonomy_version t WHERE t.id=taxonomy_version_id AND (t.tenant_id IS NULL OR t.tenant_id=stackgraph_current_tenant_id())));
ALTER TABLE capability_mapping ENABLE ROW LEVEL SECURITY;
CREATE POLICY capability_mapping_visibility ON capability_mapping USING(EXISTS(SELECT 1 FROM capability_taxonomy_version t WHERE t.id=taxonomy_version_id AND (t.tenant_id IS NULL OR t.tenant_id=stackgraph_current_tenant_id())));
CREATE TABLE schema_migration(version text PRIMARY KEY,checksum text NOT NULL CHECK(checksum ~ '^[a-f0-9]{64}$'),applied_at timestamptz NOT NULL DEFAULT now());
INSERT INTO schema_migration(version,checksum) VALUES
 ('001_allow_global_assessment_inputs.sql','c15c6c623d9bb3514f3729f020ceff265cad1c5d630cd8b93d57c4a0702e16de'),
 ('002_emit_projection_closure_events.sql','2efc6f909027fc518da4909f16bceb8bb1d97c05123e92cd19a18adc343b96ec'),
 ('003_allow_global_recommendation_evidence.sql','031fcc0430b8502fdeee5593cd522e6b3ee2a6f0aa037481d389c81a51df861f'),
 ('004_ai_prompt_catalog.sql','0a2ac20afaa0a3f51f2227f22a79f8e3dc7cb7dc9fc394ec5fb2d6e0b7e34e24'),
 ('005_dependency_usage_analysis.sql','98263f1f32158e24b75518348dbe26bf66d68cd5d0d5e01596496850b9d08e74'),
 ('006_capability_intelligence.sql','100fd356a97e4d2fb2cd3eeecb2a53735971ef1751731ef5cda9a7820ccf2fa4'),
 ('007_modernization_intelligence.sql','bed4bc45230cff1a69e646e028b80cbb196522a377e9000fe1ae76c97e8ff918'),
 ('008_phase3_gap_closure.sql','056ecbe038a3fb008868b0e8845b0b6a071479b6352970c44388219fe662b270'),
 ('009_business_map_persistence.sql','9d32af5fb14888d2a2b1eaf31a748819d311a32f8462d7441b7a801cdd0cef5b'),
 ('010_admin_and_review_queue.sql','dd91b5ccda713baed50c26dca094028f472f662dea628de679e49ab6bbac4493'),
 ('011_tenant_ai_provider_configuration.sql','20f0096023b1f959de30e5a81764923392153caef120dd41eb2b85386078818c'),
 ('012_activate_tenant_ai_enrichment.sql','32fcc5401f4e0549c74e3e23997f19ada49b90de421c4ebd394f80ac4193b0b5'),
 ('013_auth_token_revocation.sql','835e327b669036047fbdf882a9abc4a1c2bf6829d838a084d3aa9bbc1c82617b'); -- gitleaks:allow; migration checksum, not a credential
COMMIT;
