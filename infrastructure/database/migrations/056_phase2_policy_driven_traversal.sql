-- Phase 2 M1/M2: make the impact policy the thing that actually decides traversal.
--
-- Until now `impact_policy` was read only to pin an id, version, and content hash onto a run.
-- Its configuration — edges, directions, depths, confidence floor, stop conditions — was never
-- read, and traversal was hardcoded SQL. Two consequences the plan does not allow:
--
--   * A second predicate meant writing new SQL rather than seeding a policy row, so M1's
--     "use different policies for package upgrade, API deprecation, runtime change, database
--     migration, service move" was structurally unreachable.
--   * Editing a policy changed the pinned hash without changing behaviour, so the determinism
--     claim in §9.1 held by accident rather than by construction.
--
-- The version 1 configuration also named `SUPPORTS` and `BELONGS_TO`, neither of which exists
-- in `predicate_definition`. Nothing caught it precisely because the configuration was inert.
-- A validation trigger now makes that class of mistake impossible to commit.

-- 1. Curated provenance -------------------------------------------------------------------
--
-- Business capability impact is the plan's headline (§22, §44), but the capability-to-
-- application relationship is a curated business map revision, not a fact assertion, so it
-- cannot be cited through `evidence_fact_ids` and its foreign key. Recording it as a fact
-- would misrepresent curation as observation. It gets its own column, and findings that carry
-- it must say so.

ALTER TABLE simulation_finding
  ADD COLUMN curated_evidence jsonb NOT NULL DEFAULT '[]'
    CHECK(jsonb_typeof(curated_evidence)='array');

COMMENT ON COLUMN simulation_finding.curated_evidence IS
  'Non-fact provenance: curated sources such as a business map revision. Kept separate from '
  'evidence_fact_ids so curation is never displayed as observed evidence.';

-- 2. Policy predicate validation ----------------------------------------------------------

CREATE FUNCTION stackgraph_validate_impact_policy()
RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
  unknown_predicate text;
  bad_classification text;
  bad_direction text;
BEGIN
  SELECT edge->>'predicate' INTO unknown_predicate
  FROM jsonb_array_elements(coalesce(NEW.configuration->'edges','[]'::jsonb)) edge
  WHERE NOT EXISTS(
    SELECT 1 FROM predicate_definition
    WHERE predicate=edge->>'predicate' AND projects_as_edge
  )
  LIMIT 1;
  IF unknown_predicate IS NOT NULL THEN
    RAISE EXCEPTION
      'impact policy % references predicate % which is not a projectable ontology predicate',
      NEW.policy_key, unknown_predicate;
  END IF;

  SELECT edge->>'classification' INTO bad_classification
  FROM jsonb_array_elements(coalesce(NEW.configuration->'edges','[]'::jsonb)) edge
  WHERE coalesce(edge->>'classification','') NOT IN
    ('DIRECT','TRANSITIVE','CONTEXT','STOP','INFORMATIONAL')
  LIMIT 1;
  IF bad_classification IS NOT NULL THEN
    RAISE EXCEPTION 'impact policy % uses unknown classification %',
      NEW.policy_key, bad_classification;
  END IF;

  SELECT edge->>'direction' INTO bad_direction
  FROM jsonb_array_elements(coalesce(NEW.configuration->'edges','[]'::jsonb)) edge
  WHERE coalesce(edge->>'direction','') NOT IN ('INBOUND','OUTBOUND')
  LIMIT 1;
  IF bad_direction IS NOT NULL THEN
    RAISE EXCEPTION 'impact policy % uses unknown direction %', NEW.policy_key, bad_direction;
  END IF;

  RETURN NEW;
END $$;

CREATE TRIGGER trg_validate_impact_policy
  BEFORE INSERT OR UPDATE ON impact_policy
  FOR EACH ROW EXECUTE FUNCTION stackgraph_validate_impact_policy();

-- 3. Retire the inert version 1 and activate a policy the engine reads ---------------------

UPDATE impact_policy SET status='SUPERSEDED'
WHERE tenant_id IS NULL AND policy_key='upgrade-package' AND version=1;

WITH configuration AS (
  SELECT '{
    "schema_version": "impact-policy/2.0.0",
    "max_depth": 4,
    "max_nodes": 100000,
    "max_edges": 500000,
    "minimum_confidence": 0.80,
    "seed": {
      "kind": "PACKAGE_DEPENDENTS",
      "subject_types": ["Repository"],
      "classification": "DIRECT"
    },
    "edges": [
      {"predicate":"IMPLEMENTED_BY","direction":"INBOUND","from_types":["Repository"],
       "to_types":["Application","Service"],"classification":"TRANSITIVE","max_depth":2,
       "weight":0.9},
      {"predicate":"CONTAINS","direction":"OUTBOUND","from_types":["Application"],
       "to_types":["Service"],"classification":"TRANSITIVE","max_depth":3,"weight":0.8},
      {"predicate":"DEPENDS_ON","direction":"INBOUND","from_types":["Application","Service"],
       "to_types":["Application","Service"],"classification":"TRANSITIVE","max_depth":3,
       "weight":0.7},
      {"predicate":"EXPOSES","direction":"OUTBOUND","from_types":["Application","Service"],
       "to_types":["API"],"classification":"TRANSITIVE","max_depth":4,"weight":0.85},
      {"predicate":"CONTAINS","direction":"OUTBOUND","from_types":["Repository"],
       "to_types":["Component"],"classification":"CONTEXT","max_depth":2,"weight":0.5},
      {"predicate":"DEPLOYED_AS","direction":"OUTBOUND","from_types":["Repository","Service"],
       "to_types":["Deployment"],"classification":"CONTEXT","max_depth":3,"weight":0.5},
      {"predicate":"USES","direction":"OUTBOUND","from_types":["Repository"],
       "to_types":["Database","InfrastructureResource"],"classification":"CONTEXT",
       "max_depth":2,"weight":0.4}
    ],
    "capability_rule": {
      "classification": "TRANSITIVE",
      "from_types": ["Application"],
      "max_depth": 4,
      "tier_zero_criticality": 1
    },
    "stop_conditions": [
      "LOW_CONFIDENCE","UNRESOLVED_IDENTITY","PARTIAL_SOURCE","TRAVERSAL_BUDGET","MAX_DEPTH"
    ]
  }'::jsonb AS value
)
INSERT INTO impact_policy(
  tenant_id,policy_key,predicate,subject_type,version,status,configuration,content_hash,
  created_by,activated_at
)
SELECT NULL,'upgrade-package','UPGRADE','Package',2,'ACTIVE',value,
       'sha256:'||encode(digest(value::text,'sha256'),'hex'),'migration:056',now()
FROM configuration;

-- 4. Interpretation remediation and quarantine detail --------------------------------------
--
-- M2 lists remediation alongside risk, explanation, rollout, and verification, and requires
-- an uncited claim to be visibly quarantined rather than blended into the result. The table
-- could record a QUARANTINED status but had nowhere to put the claim that caused it, so the
-- reason would have been lost.

ALTER TABLE simulation_interpretation
  ADD COLUMN remediation jsonb NOT NULL DEFAULT '[]'
    CHECK(jsonb_typeof(remediation)='array'),
  ADD COLUMN quarantined_claims jsonb NOT NULL DEFAULT '[]'
    CHECK(jsonb_typeof(quarantined_claims)='array');

COMMENT ON COLUMN simulation_interpretation.quarantined_claims IS
  'Interpretation output that cited no finding, kept visible and separate. §9.1 requires an '
  'uncited claim to be quarantined rather than hidden or allowed to affect gate or risk facts.';

-- 5. Dependency-change coverage ------------------------------------------------------------
--
-- The activity aggregate has counted DEPENDENCY_CHANGE since migration 050, but no collector
-- ever produced one, so the column was structurally zero and H1's change memory could never
-- fill itself from observed activity. The collector now detects manifest and lockfile moves on
-- merged pull requests, which needs a coverage status of its own: a repository where detection
-- was never attempted must not read the same as one where it ran and found nothing.

ALTER TABLE repository_activity_collection
  ADD COLUMN dependency_changes_status text NOT NULL DEFAULT 'NOT_COLLECTED'
    CHECK(dependency_changes_status IN (
      'NOT_COLLECTED','AVAILABLE','PARTIAL','PERMISSION_REQUIRED','ERROR'
    ));
