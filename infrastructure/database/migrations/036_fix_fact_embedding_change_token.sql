CREATE OR REPLACE FUNCTION stackgraph_enqueue_fact_embedding()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  INSERT INTO embedding_job(tenant_id,embedding_space_id,subject_id,input_hash)
  SELECT entity_row.tenant_id,space.id,entity_row.id,
         'sha256:'||encode(digest(concat_ws(':',
           entity_row.id::text,NEW.id::text,NEW.predicate,
           coalesce(NEW.object_entity_id::text,''),coalesce(NEW.object_value::text,''),
           NEW.confidence::text,coalesce(NEW.system_to::text,''),space.template_version
         ),'sha256'),'hex')
  FROM entity entity_row
  JOIN embedding_space space ON space.tenant_id=entity_row.tenant_id
  WHERE entity_row.id IN (NEW.subject_entity_id,NEW.object_entity_id)
    AND space.space_kind='SEMANTIC_ENTITY' AND space.lifecycle_state IN ('SHADOW','ACTIVE')
  ON CONFLICT DO NOTHING;
  RETURN NEW;
END $$;
