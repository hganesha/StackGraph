CREATE TABLE embedding_relevance_case (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES tenant(id) ON DELETE CASCADE,
  case_key text NOT NULL CHECK (case_key ~ '^[a-z][a-z0-9._-]{2,127}$'),
  query_text text NOT NULL CHECK (query_text<>''),
  relevant_entity_ids uuid[] NOT NULL CHECK (cardinality(relevant_entity_ids)>=1),
  hard_negative_entity_ids uuid[] NOT NULL DEFAULT '{}',
  evaluation_k integer NOT NULL DEFAULT 10 CHECK (evaluation_k BETWEEN 1 AND 100),
  status text NOT NULL DEFAULT 'ACTIVE' CHECK (status IN ('ACTIVE','RETIRED')),
  rationale text NOT NULL DEFAULT '',
  created_by text NOT NULL CHECK (created_by<>''),
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(tenant_id,case_key),
  CHECK (NOT relevant_entity_ids && hard_negative_entity_ids)
);

CREATE OR REPLACE FUNCTION stackgraph_validate_embedding_relevance_case()
RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE entity_id uuid;
BEGIN
  FOREACH entity_id IN ARRAY NEW.relevant_entity_ids||NEW.hard_negative_entity_ids LOOP
    IF NOT EXISTS (SELECT 1 FROM entity WHERE id=entity_id AND tenant_id=NEW.tenant_id) THEN
      RAISE EXCEPTION 'embedding relevance case entity % is outside tenant %',entity_id,NEW.tenant_id;
    END IF;
  END LOOP;
  RETURN NEW;
END $$;

CREATE TRIGGER embedding_relevance_case_validate
BEFORE INSERT OR UPDATE ON embedding_relevance_case
FOR EACH ROW EXECUTE FUNCTION stackgraph_validate_embedding_relevance_case();

CREATE INDEX idx_embedding_relevance_case_active
  ON embedding_relevance_case(tenant_id,status,case_key);

ALTER TABLE embedding_relevance_case ENABLE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON embedding_relevance_case
USING (tenant_id=stackgraph_current_tenant_id())
WITH CHECK (tenant_id=stackgraph_current_tenant_id());
