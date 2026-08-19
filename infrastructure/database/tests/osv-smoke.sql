\set ON_ERROR_STOP on

DO $$
DECLARE
  target_id uuid;
  fact_total integer;
  evidence_total integer;
  vulnerability_total integer;
BEGIN
  SELECT target.id INTO target_id
  FROM ingest_target target
  JOIN source_system source ON source.id = target.source_system_id
  WHERE source.source_key = 'osv.dev'
    AND target.target_kind = 'PACKAGE_VERSION'
    AND target.target_key = 'pkg:npm/lodash@4.17.20';

  IF target_id IS NULL THEN
    RAISE EXCEPTION 'lodash OSV target was not created';
  END IF;

  SELECT count(*) INTO fact_total
  FROM current_fact fact
  JOIN source_snapshot snapshot ON snapshot.id = fact.source_snapshot_id
  WHERE snapshot.ingest_target_id = target_id
    AND fact.predicate = 'AFFECTED_BY';
  IF fact_total < 1 THEN
    RAISE EXCEPTION 'expected at least one current lodash vulnerability fact';
  END IF;

  SELECT count(*) INTO evidence_total
  FROM evidence item
  JOIN fact_assertion fact ON fact.id = item.fact_assertion_id
  JOIN source_snapshot snapshot ON snapshot.id = fact.source_snapshot_id
  WHERE snapshot.ingest_target_id = target_id
    AND fact.system_to IS NULL
    AND item.excerpt_hash ~ '^sha256:[a-f0-9]{64}$';
  IF evidence_total < fact_total * 2 THEN
    RAISE EXCEPTION 'expected at least two exact evidence records per OSV fact, found % for % facts', evidence_total, fact_total;
  END IF;

  SELECT count(DISTINCT fact.object_entity_id) INTO vulnerability_total
  FROM current_fact fact
  JOIN source_snapshot snapshot ON snapshot.id = fact.source_snapshot_id
  JOIN entity vulnerability ON vulnerability.id = fact.object_entity_id
  JOIN entity_identity identity ON identity.entity_id = vulnerability.id
  WHERE snapshot.ingest_target_id = target_id
    AND fact.predicate = 'AFFECTED_BY'
    AND vulnerability.namespace = 'INTELLIGENCE'
    AND vulnerability.entity_type = 'Vulnerability'
    AND identity.scheme = 'OSV';
  IF vulnerability_total <> fact_total THEN
    RAISE EXCEPTION 'OSV identities are missing for one or more vulnerability entities';
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM freshness_state
    WHERE ingest_target_id = target_id
      AND status = 'FRESH'
      AND last_source_revision ~ '^sha256:[a-f0-9]{64}$'
  ) THEN
    RAISE EXCEPTION 'OSV freshness state is missing';
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM ingest_run
    WHERE ingest_target_id = target_id
      AND status = 'SUCCEEDED'
      AND stats->>'replayed' = 'true'
  ) THEN
    RAISE EXCEPTION 'OSV replay run was not recorded';
  END IF;
END $$;

SELECT fact.predicate, count(*)
FROM current_fact fact
JOIN source_snapshot snapshot ON snapshot.id = fact.source_snapshot_id
JOIN ingest_target target ON target.id = snapshot.ingest_target_id
WHERE target.target_key = 'pkg:npm/lodash@4.17.20'
  AND fact.predicate = 'AFFECTED_BY'
GROUP BY fact.predicate;
