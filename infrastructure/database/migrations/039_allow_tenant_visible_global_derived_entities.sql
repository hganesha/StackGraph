CREATE OR REPLACE FUNCTION stackgraph_validate_visible_entity_reference()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path=pg_catalog,public
AS $$
DECLARE
  referenced_entity_id uuid;
  referenced_tenant_id uuid;
BEGIN
  referenced_entity_id := (to_jsonb(NEW)->>TG_ARGV[0])::uuid;
  SELECT entity.tenant_id INTO referenced_tenant_id
  FROM public.entity
  WHERE entity.id=referenced_entity_id;

  IF NOT FOUND THEN
    RAISE EXCEPTION 'derived intelligence references an unknown entity %',referenced_entity_id
      USING ERRCODE='23503';
  END IF;
  IF referenced_tenant_id IS NOT NULL AND referenced_tenant_id<>NEW.tenant_id THEN
    RAISE EXCEPTION 'entity % is not visible to tenant %',referenced_entity_id,NEW.tenant_id
      USING ERRCODE='23514';
  END IF;
  RETURN NEW;
END $$;

ALTER TABLE embedding_document
  DROP CONSTRAINT embedding_document_entity_id_tenant_id_fkey,
  ADD CONSTRAINT embedding_document_entity_id_fkey
    FOREIGN KEY(entity_id) REFERENCES entity(id) ON DELETE CASCADE;
CREATE TRIGGER embedding_document_visible_entity
BEFORE INSERT OR UPDATE OF tenant_id,entity_id ON embedding_document
FOR EACH ROW EXECUTE FUNCTION stackgraph_validate_visible_entity_reference('entity_id');

ALTER TABLE entity_embedding
  DROP CONSTRAINT entity_embedding_entity_id_tenant_id_fkey,
  ADD CONSTRAINT entity_embedding_entity_id_fkey
    FOREIGN KEY(entity_id) REFERENCES entity(id) ON DELETE CASCADE;
CREATE TRIGGER entity_embedding_visible_entity
BEFORE INSERT OR UPDATE OF tenant_id,entity_id ON entity_embedding
FOR EACH ROW EXECUTE FUNCTION stackgraph_validate_visible_entity_reference('entity_id');

ALTER TABLE embedding_job
  DROP CONSTRAINT embedding_job_subject_id_tenant_id_fkey,
  ADD CONSTRAINT embedding_job_subject_id_fkey
    FOREIGN KEY(subject_id) REFERENCES entity(id) ON DELETE CASCADE;
CREATE TRIGGER embedding_job_visible_entity
BEFORE INSERT OR UPDATE OF tenant_id,subject_id ON embedding_job
FOR EACH ROW EXECUTE FUNCTION stackgraph_validate_visible_entity_reference('subject_id');

ALTER TABLE graph_community_alignment
  DROP CONSTRAINT graph_community_alignment_entity_id_tenant_id_fkey,
  ADD CONSTRAINT graph_community_alignment_entity_id_fkey
    FOREIGN KEY(entity_id) REFERENCES entity(id) ON DELETE CASCADE;
CREATE TRIGGER graph_community_alignment_visible_entity
BEFORE INSERT OR UPDATE OF tenant_id,entity_id ON graph_community_alignment
FOR EACH ROW EXECUTE FUNCTION stackgraph_validate_visible_entity_reference('entity_id');

ALTER TABLE graph_anomaly
  DROP CONSTRAINT graph_anomaly_entity_id_tenant_id_fkey,
  ADD CONSTRAINT graph_anomaly_entity_id_fkey
    FOREIGN KEY(entity_id) REFERENCES entity(id) ON DELETE CASCADE;
CREATE TRIGGER graph_anomaly_visible_entity
BEFORE INSERT OR UPDATE OF tenant_id,entity_id ON graph_anomaly
FOR EACH ROW EXECUTE FUNCTION stackgraph_validate_visible_entity_reference('entity_id');
