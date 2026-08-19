CREATE TABLE package_api_surface (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid REFERENCES tenant(id),
  package_version_entity_id uuid NOT NULL REFERENCES entity(id) ON DELETE CASCADE,
  ecosystem text NOT NULL CHECK(ecosystem IN ('npm','pypi')),
  artifact_checksum text NOT NULL CHECK(artifact_checksum ~ '^sha256:[a-f0-9]{64}$'),
  analyzer_key text NOT NULL,
  analyzer_version text NOT NULL,
  analysis_fingerprint text NOT NULL CHECK(analysis_fingerprint ~ '^sha256:[a-f0-9]{64}$'),
  public_symbol_count integer NOT NULL CHECK(public_symbol_count >= 0),
  symbols jsonb NOT NULL DEFAULT '[]' CHECK(jsonb_typeof(symbols)='array'),
  completeness text NOT NULL CHECK(completeness IN ('COMPLETE','PARTIAL')),
  limitations jsonb NOT NULL DEFAULT '[]' CHECK(jsonb_typeof(limitations)='array'),
  stats jsonb NOT NULL DEFAULT '{}' CHECK(jsonb_typeof(stats)='object'),
  analyzed_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE NULLS NOT DISTINCT(tenant_id, analysis_fingerprint),
  UNIQUE NULLS NOT DISTINCT(
    tenant_id, package_version_entity_id, artifact_checksum,
    analyzer_key, analyzer_version
  )
);

CREATE INDEX idx_package_api_surface_lookup
  ON package_api_surface(package_version_entity_id, analyzed_at DESC);

CREATE TABLE dependency_usage_summary (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES tenant(id),
  source_snapshot_id uuid NOT NULL REFERENCES source_snapshot(id) ON DELETE CASCADE,
  dependency_fact_assertion_id uuid NOT NULL REFERENCES fact_assertion(id) ON DELETE CASCADE,
  declared boolean NOT NULL,
  resolved boolean NOT NULL,
  referenced boolean NOT NULL,
  static_reachability text NOT NULL CHECK(static_reachability IN ('OBSERVED','NOT_OBSERVED','UNKNOWN')),
  runtime_observed text NOT NULL CHECK(runtime_observed IN ('OBSERVED','NOT_OBSERVED','UNKNOWN')),
  reference_count integer NOT NULL CHECK(reference_count >= 0),
  referenced_symbols jsonb NOT NULL DEFAULT '[]' CHECK(jsonb_typeof(referenced_symbols)='array'),
  source_files_scanned integer NOT NULL CHECK(source_files_scanned >= 0),
  limitations jsonb NOT NULL DEFAULT '[]' CHECK(jsonb_typeof(limitations)='array'),
  analysis_fingerprint text NOT NULL CHECK(analysis_fingerprint ~ '^sha256:[a-f0-9]{64}$'),
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(dependency_fact_assertion_id)
);

CREATE INDEX idx_dependency_usage_snapshot
  ON dependency_usage_summary(source_snapshot_id, referenced, static_reachability);

ALTER TABLE package_api_surface ENABLE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON package_api_surface
  USING (tenant_id IS NULL OR tenant_id=stackgraph_current_tenant_id())
  WITH CHECK (tenant_id=stackgraph_current_tenant_id());

ALTER TABLE dependency_usage_summary ENABLE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON dependency_usage_summary
  USING (tenant_id=stackgraph_current_tenant_id())
  WITH CHECK (tenant_id=stackgraph_current_tenant_id());

CREATE OR REPLACE FUNCTION publish_source_snapshot(p_snapshot_id uuid)
RETURNS void LANGUAGE plpgsql AS $$
DECLARE s source_snapshot%ROWTYPE;
BEGIN
  SELECT * INTO s FROM source_snapshot WHERE id=p_snapshot_id FOR UPDATE;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'source snapshot % not found',p_snapshot_id;
  END IF;
  IF s.status<>'STAGED' THEN
    RAISE EXCEPTION 'source snapshot % is not staged',p_snapshot_id;
  END IF;
  IF s.completeness='COMPLETE' THEN
    WITH closed AS (
      UPDATE fact_assertion f SET system_to=now() FROM source_snapshot old
      WHERE f.source_snapshot_id=old.id
        AND old.ingest_target_id=s.ingest_target_id
        AND old.extractor_key=s.extractor_key
        AND old.id<>s.id
        AND f.system_to IS NULL
      RETURNING f.id,f.tenant_id
    )
    INSERT INTO projection_outbox(
      tenant_id,aggregate_type,aggregate_id,operation,dedupe_key,payload
    )
    SELECT closed.tenant_id,'FACT',closed.id,'CLOSE',
      'snapshot:'||p_snapshot_id::text||':close:'||closed.id::text,
      jsonb_build_object('closed_by_source_snapshot_id',p_snapshot_id)
    FROM closed ON CONFLICT(dedupe_key) DO NOTHING;
  END IF;
  UPDATE source_snapshot SET status='PUBLISHED',published_at=now()
  WHERE id=p_snapshot_id;
  INSERT INTO projection_outbox(
    tenant_id,aggregate_type,aggregate_id,operation,dedupe_key,payload
  )
  SELECT f.tenant_id,'FACT',f.id,'UPSERT',
    'snapshot:'||p_snapshot_id::text||':fact:'||f.id::text,
    jsonb_build_object('source_snapshot_id',p_snapshot_id)
  FROM fact_assertion f WHERE f.source_snapshot_id=p_snapshot_id
  ON CONFLICT(dedupe_key) DO NOTHING;
END $$;
