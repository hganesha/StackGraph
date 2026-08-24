CREATE OR REPLACE FUNCTION stackgraph_validate_embedding_relevance_case()
RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE entity_id uuid;
BEGIN
  FOREACH entity_id IN ARRAY NEW.relevant_entity_ids||NEW.hard_negative_entity_ids LOOP
    IF NOT EXISTS (SELECT 1 FROM entity WHERE id=entity_id AND tenant_id=NEW.tenant_id) THEN
      RAISE EXCEPTION 'embedding relevance case entity % is outside tenant %',entity_id,NEW.tenant_id;
    END IF;
  END LOOP;
  UPDATE embedding_space
  SET evaluation=jsonb_build_object(
        'passed',false,
        'method_version','embedding-space-relevance/v2',
        'reason','RELEVANCE_CORPUS_CHANGED_REEVALUATION_REQUIRED'
      ),updated_at=now()
  WHERE tenant_id=NEW.tenant_id AND space_kind='SEMANTIC_ENTITY'
    AND lifecycle_state IN ('SHADOW','ACTIVE');
  RETURN NEW;
END $$;

CREATE OR REPLACE FUNCTION stackgraph_embedding_relevance_case_no_delete()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  RAISE EXCEPTION 'embedding relevance cases are retained; set status to RETIRED';
END $$;

CREATE TRIGGER embedding_relevance_case_no_delete
BEFORE DELETE ON embedding_relevance_case
FOR EACH ROW EXECUTE FUNCTION stackgraph_embedding_relevance_case_no_delete();
