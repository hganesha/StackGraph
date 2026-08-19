\set ON_ERROR_STOP on

DO $$
DECLARE
  target_id uuid;
  fact_total integer;
  evidence_total integer;
  entity_total integer;
BEGIN
  SELECT target.id INTO target_id
  FROM ingest_target target
  JOIN source_system source ON source.id = target.source_system_id
  WHERE source.source_key = 'deps.dev'
    AND target.target_kind = 'PACKAGE_VERSION'
    AND target.target_key = 'pkg:npm/react@18.2.0';

  IF target_id IS NULL THEN
    RAISE EXCEPTION 'React deps.dev target was not created';
  END IF;

  SELECT count(*) INTO fact_total
  FROM current_fact fact
  JOIN source_snapshot snapshot ON snapshot.id = fact.source_snapshot_id
  WHERE snapshot.ingest_target_id = target_id;
  IF fact_total <> 6 THEN
    RAISE EXCEPTION 'expected 6 current deps.dev facts, found %', fact_total;
  END IF;

  SELECT count(*) INTO evidence_total
  FROM evidence item
  JOIN fact_assertion fact ON fact.id = item.fact_assertion_id
  JOIN source_snapshot snapshot ON snapshot.id = fact.source_snapshot_id
  WHERE snapshot.ingest_target_id = target_id
    AND fact.system_to IS NULL;
  IF evidence_total <> 6 THEN
    RAISE EXCEPTION 'expected evidence for all 6 deps.dev facts, found %', evidence_total;
  END IF;

  SELECT count(*) INTO entity_total
  FROM entity
  WHERE canonical_key IN (
    'pkg:npm/react',
    'pkg:npm/react@18.2.0',
    'pkg:npm/loose-envify',
    'pkg:npm/loose-envify@1.4.0',
    'pkg:npm/js-tokens',
    'pkg:npm/js-tokens@4.0.0'
  );
  IF entity_total <> 6 THEN
    RAISE EXCEPTION 'expected 6 React dependency entities, found %', entity_total;
  END IF;

  IF NOT EXISTS (
    SELECT 1
    FROM freshness_state
    WHERE ingest_target_id = target_id
      AND status = 'FRESH'
      AND last_source_revision ~ '^sha256:[a-f0-9]{64}$'
  ) THEN
    RAISE EXCEPTION 'deps.dev freshness state is missing';
  END IF;

  IF NOT EXISTS (
    SELECT 1
    FROM ingest_run
    WHERE ingest_target_id = target_id
      AND status = 'SUCCEEDED'
      AND stats->>'replayed' = 'true'
  ) THEN
    RAISE EXCEPTION 'deps.dev replay run was not recorded';
  END IF;
END $$;

SELECT fact.predicate, count(*)
FROM current_fact fact
JOIN source_snapshot snapshot ON snapshot.id = fact.source_snapshot_id
JOIN ingest_target target ON target.id = snapshot.ingest_target_id
WHERE target.target_key = 'pkg:npm/react@18.2.0'
GROUP BY fact.predicate
ORDER BY fact.predicate;
