-- Close two deferrals: registry-enumerated target versions, and container digest resolution.
--
-- Both were deferred for the same reason — they need data from outside the repository — and both
-- are answerable with the connector machinery that already exists for deps.dev and OSV.

-- 1. The registry's catalogue, kept apart from the estate's identity -----------------------
--
-- `package_registry_identity` records versions the estate actually uses; every row has an
-- entity. Enumerating a registry would mean inventing entities for versions nobody runs, which
-- would inflate the estate with things it does not have and make every count wrong.
--
-- A catalogue is a different claim: "the registry offers this", not "we run this". It gets its
-- own table, has no entity, and is joined at read time so `valid_targets` can offer an upgrade
-- to a version the estate has never seen while still saying which of the two it is.

CREATE TABLE package_version_catalog (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  -- NULL for a public registry, so one enumeration serves every tenant. A private registry's
  -- catalogue is tenant-scoped because its contents are not public knowledge.
  tenant_id uuid REFERENCES tenant(id),
  registry_key text NOT NULL CHECK(registry_key<>''),
  ecosystem text NOT NULL CHECK(ecosystem IN ('npm','pypi','nuget','maven','cargo','go')),
  package_name text NOT NULL CHECK(package_name<>''),
  version text NOT NULL CHECK(version<>''),
  is_prerelease boolean NOT NULL DEFAULT false,
  -- Yanked and deprecated are different failures: a yanked release should not be installed at
  -- all, a deprecated one still works. Collapsing them would hide which is which.
  is_yanked boolean NOT NULL DEFAULT false,
  is_deprecated boolean NOT NULL DEFAULT false,
  deprecation_reason text,
  published_at timestamptz,
  support_status text NOT NULL DEFAULT 'UNKNOWN'
    CHECK(support_status IN ('SUPPORTED','UNKNOWN','UNSUPPORTED','END_OF_LIFE')),
  source_uri text,
  collected_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE NULLS NOT DISTINCT(tenant_id,registry_key,package_name,version)
);

CREATE INDEX idx_package_version_catalog_lookup
  ON package_version_catalog(ecosystem,lower(package_name),collected_at DESC);

ALTER TABLE package_version_catalog ENABLE ROW LEVEL SECURITY;
CREATE POLICY package_version_catalog_visibility ON package_version_catalog
  USING(tenant_id IS NULL OR tenant_id=stackgraph_current_tenant_id())
  WITH CHECK(tenant_id=stackgraph_current_tenant_id());

COMMENT ON TABLE package_version_catalog IS
  'What a registry offers, as distinct from what the estate runs. Never joined to entity: a '
  'catalogue row is a purchasable option, not a thing StackGraph has observed in the estate.';

-- Records one enumeration attempt per package, so a package the enumerator has never reached is
-- distinguishable from one it reached and found nothing for. §9.1 forbids the second reading of
-- the first.
CREATE TABLE package_catalog_collection (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid REFERENCES tenant(id),
  registry_key text NOT NULL CHECK(registry_key<>''),
  ecosystem text NOT NULL,
  package_name text NOT NULL CHECK(package_name<>''),
  status text NOT NULL CHECK(status IN ('AVAILABLE','PARTIAL','NOT_FOUND','ERROR')),
  version_count integer NOT NULL DEFAULT 0 CHECK(version_count>=0),
  limitations jsonb NOT NULL DEFAULT '[]' CHECK(jsonb_typeof(limitations)='array'),
  collected_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE NULLS NOT DISTINCT(tenant_id,registry_key,package_name)
);

ALTER TABLE package_catalog_collection ENABLE ROW LEVEL SECURITY;
CREATE POLICY package_catalog_collection_visibility ON package_catalog_collection
  USING(tenant_id IS NULL OR tenant_id=stackgraph_current_tenant_id())
  WITH CHECK(tenant_id=stackgraph_current_tenant_id());

-- 2. Container registries as a source system -----------------------------------------------
--
-- S3 requires digest-first container identity, resolved asynchronously, cached, rate-limited,
-- allowlisted, and never blocking a local scan. That is exactly the ingest_target/ingest_run
-- contract deps.dev and OSV already use, so the registry becomes another source system rather
-- than a bespoke pipeline.

ALTER TABLE source_system DROP CONSTRAINT IF EXISTS source_system_kind_check;
ALTER TABLE source_system ADD CONSTRAINT source_system_kind_check
  CHECK(kind IN (
    'GITHUB','PACKAGE_REGISTRY','DEPS_DEV','OSV','OPENSSF','CURATED','CONTAINER_REGISTRY','OTHER'
  ));

-- A mutable tag is an observation, never an identity (S3). This records which tag was asked
-- about, what digest came back, and when — so a tag that has since moved is visible as a moved
-- tag rather than silently overwriting what production actually ran.
CREATE TABLE container_tag_resolution (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid REFERENCES tenant(id),
  registry_host text NOT NULL CHECK(registry_host<>''),
  repository text NOT NULL CHECK(repository<>''),
  tag text NOT NULL CHECK(tag<>''),
  digest text NOT NULL CHECK(digest ~ '^sha256:[a-f0-9]{64}$'),
  architecture text,
  operating_system text,
  media_type text,
  resolved_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE NULLS NOT DISTINCT(tenant_id,registry_host,repository,tag,digest)
);

CREATE INDEX idx_container_tag_resolution_current
  ON container_tag_resolution(registry_host,repository,tag,resolved_at DESC);

ALTER TABLE container_tag_resolution ENABLE ROW LEVEL SECURITY;
CREATE POLICY container_tag_resolution_visibility ON container_tag_resolution
  USING(tenant_id IS NULL OR tenant_id=stackgraph_current_tenant_id())
  WITH CHECK(tenant_id=stackgraph_current_tenant_id());

COMMENT ON TABLE container_tag_resolution IS
  'Tag-to-digest observations over time. A tag is not an identity; keeping the history is what '
  'makes a moved tag visible instead of silently replacing what production ran.';

-- Container enrichment gets its own kill switch, because it is the one Phase 2 path that talks
-- to a network the scanner deliberately never touches. It defaults off: reaching an external
-- registry is a decision an operator makes, not one a migration makes for them.
ALTER TABLE phase2_feature_flag DROP CONSTRAINT IF EXISTS phase2_feature_flag_flag_key_check;
ALTER TABLE phase2_feature_flag ADD CONSTRAINT phase2_feature_flag_flag_key_check
  CHECK(flag_key IN (
    'SCANNER_PROFILES','CHANGE_COMPILER','CHANGE_SIMULATION','AI_INTERPRETATION',
    'CHANGE_EXECUTION','REGISTRY_ENRICHMENT'
  ));

INSERT INTO phase2_feature_flag(tenant_id,flag_key,enabled,updated_by) VALUES
  (NULL,'REGISTRY_ENRICHMENT',false,'migration:058')
ON CONFLICT DO NOTHING;
