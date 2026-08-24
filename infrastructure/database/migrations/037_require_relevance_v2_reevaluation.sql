-- Upgrade safety: spaces evaluated before the reviewed relevance-corpus gate was
-- introduced must fail closed until the v2 evaluator has run. The active pointer
-- is intentionally retained so operators can inspect/roll back the space, while
-- API serving checks the invalidated evaluation and refuses semantic retrieval.
UPDATE embedding_space
SET evaluation = jsonb_build_object(
      'passed', false,
      'method_version', 'embedding-space-relevance/v2',
      'reason', 'RELEVANCE_V2_REEVALUATION_REQUIRED'
    ),
    updated_at = now()
WHERE space_kind = 'SEMANTIC_ENTITY'
  AND lifecycle_state IN ('SHADOW', 'ACTIVE')
  AND coalesce(evaluation->>'method_version', '') <> 'embedding-space-relevance/v2';
