CREATE OR REPLACE FUNCTION publish_source_snapshot(p_snapshot_id uuid) RETURNS void LANGUAGE plpgsql AS $$
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
