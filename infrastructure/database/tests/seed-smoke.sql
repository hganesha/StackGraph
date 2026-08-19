\set ON_ERROR_STOP on

DO $$
DECLARE
  technology_count integer;
  capability_count integer;
  current_seed_fact_count integer;
  current_assessment_count integer;
  unevidenced_fact_count integer;
BEGIN
  SELECT count(*) INTO technology_count
  FROM entity
  WHERE tenant_id IS NULL
    AND namespace = 'TECHNOLOGY'
    AND entity_type = 'Technology'
    AND properties->>'seed_id' = 'framework-landscape-2026';

  SELECT count(*) INTO capability_count
  FROM entity
  WHERE tenant_id IS NULL
    AND namespace = 'TECHNOLOGY'
    AND entity_type = 'Capability'
    AND properties->>'seed_id' = 'framework-landscape-2026';

  SELECT count(*) INTO current_seed_fact_count
  FROM current_fact
  WHERE tenant_id IS NULL
    AND properties->>'seed_id' = 'framework-landscape-2026';

  SELECT count(*) INTO current_assessment_count
  FROM assessment
  WHERE tenant_id IS NULL
    AND method = 'CURATED_SEED'
    AND status = 'CURRENT';

  SELECT count(*) INTO unevidenced_fact_count
  FROM current_fact fact
  LEFT JOIN evidence ON evidence.fact_assertion_id = fact.id
  WHERE fact.tenant_id IS NULL
    AND fact.properties->>'seed_id' = 'framework-landscape-2026'
    AND evidence.id IS NULL;

  IF technology_count <> 192 THEN
    RAISE EXCEPTION 'expected 192 technologies, found %', technology_count;
  END IF;
  IF capability_count <> 38 THEN
    RAISE EXCEPTION 'expected 38 capabilities, found %', capability_count;
  END IF;
  IF current_seed_fact_count <> 337 THEN
    RAISE EXCEPTION 'expected 337 current seed facts, found %', current_seed_fact_count;
  END IF;
  IF current_assessment_count <> 6 THEN
    RAISE EXCEPTION 'expected 6 current assessments, found %', current_assessment_count;
  END IF;
  IF unevidenced_fact_count <> 0 THEN
    RAISE EXCEPTION 'found % seed facts without evidence', unevidenced_fact_count;
  END IF;
END
$$;

SELECT
  count(*) FILTER (WHERE entity_type = 'Technology') AS technologies,
  count(*) FILTER (WHERE entity_type = 'Capability') AS capabilities
FROM entity
WHERE tenant_id IS NULL
  AND properties->>'seed_id' = 'framework-landscape-2026';

SELECT
  count(*) AS current_facts,
  count(*) FILTER (WHERE predicate = 'PROVIDES') AS capability_relationships,
  count(*) FILTER (WHERE predicate = 'HAS_PROPERTY') AS property_facts
FROM current_fact
WHERE tenant_id IS NULL
  AND properties->>'seed_id' = 'framework-landscape-2026';

SELECT
  CASE WHEN processed_at IS NULL THEN 'PENDING' ELSE 'PROCESSED' END AS status,
  count(*)
FROM projection_outbox
WHERE projection_outbox.tenant_id IS NULL
  AND payload->>'source_snapshot_id' IS NOT NULL
GROUP BY 1
ORDER BY 1;
