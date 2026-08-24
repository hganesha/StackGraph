CREATE OR REPLACE FUNCTION stackgraph_enqueue_entity_embedding()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  INSERT INTO embedding_job(tenant_id,embedding_space_id,subject_id,input_hash)
  SELECT space.tenant_id,space.id,NEW.id,
         'sha256:'||encode(digest(concat_ws(E'\n',NEW.entity_type,NEW.name,NEW.canonical_key,
           NEW.properties::text,space.template_version),'sha256'),'hex')
  FROM embedding_space space
  WHERE (space.tenant_id=NEW.tenant_id OR (
      NEW.tenant_id IS NULL AND NEW.entity_type=ANY(ARRAY['Technology','Runtime','Database','Package'])
    ))
    AND space.space_kind='SEMANTIC_ENTITY'
    AND space.lifecycle_state IN ('SHADOW','ACTIVE')
  ON CONFLICT DO NOTHING;
  RETURN NEW;
END $$;

CREATE OR REPLACE FUNCTION stackgraph_enqueue_fact_embedding()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  INSERT INTO embedding_job(tenant_id,embedding_space_id,subject_id,input_hash)
  SELECT space.tenant_id,space.id,entity_row.id,
         'sha256:'||encode(digest(concat_ws(':',
           entity_row.id::text,NEW.id::text,NEW.predicate,
           coalesce(NEW.object_entity_id::text,''),coalesce(NEW.object_value::text,''),
           NEW.confidence::text,coalesce(NEW.system_to::text,''),space.template_version
         ),'sha256'),'hex')
  FROM entity entity_row
  JOIN embedding_space space ON (
    space.tenant_id=entity_row.tenant_id OR (
      entity_row.tenant_id IS NULL
      AND entity_row.entity_type=ANY(ARRAY['Technology','Runtime','Database','Package'])
    )
  )
  WHERE entity_row.id IN (NEW.subject_entity_id,NEW.object_entity_id)
    AND (NEW.tenant_id IS NULL OR NEW.tenant_id=space.tenant_id)
    AND space.space_kind='SEMANTIC_ENTITY'
    AND space.lifecycle_state IN ('SHADOW','ACTIVE')
  ON CONFLICT DO NOTHING;
  RETURN NEW;
END $$;
