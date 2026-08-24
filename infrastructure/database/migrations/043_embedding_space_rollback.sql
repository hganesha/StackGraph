-- Permit an explicitly selected, still-qualified retired space to be restored.
-- Coverage and reviewed evaluation gates remain identical to forward promotion.

CREATE OR REPLACE FUNCTION stackgraph_validate_active_embedding_space()
RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE candidate embedding_space%ROWTYPE;
BEGIN
  SELECT * INTO candidate FROM embedding_space WHERE id=NEW.embedding_space_id FOR SHARE;
  IF candidate.id IS NULL OR candidate.tenant_id<>NEW.tenant_id OR candidate.space_kind<>NEW.space_kind THEN
    RAISE EXCEPTION 'active embedding space must match tenant and space kind';
  END IF;
  IF candidate.lifecycle_state NOT IN ('SHADOW','ACTIVE','RETIRED') THEN
    RAISE EXCEPTION 'active embedding space must be a successful shadow, active, or retired space';
  END IF;
  IF candidate.coverage_ratio<0.95 OR coalesce((candidate.evaluation->>'passed')::boolean,false) IS NOT TRUE THEN
    RAISE EXCEPTION 'active embedding space must pass coverage and evaluation gates';
  END IF;
  UPDATE embedding_space SET lifecycle_state='RETIRED',updated_at=now()
   WHERE tenant_id=NEW.tenant_id AND space_kind=NEW.space_kind
     AND lifecycle_state='ACTIVE' AND id<>NEW.embedding_space_id;
  UPDATE embedding_space SET lifecycle_state='ACTIVE',updated_at=now()
   WHERE id=NEW.embedding_space_id;
  RETURN NEW;
END $$;
