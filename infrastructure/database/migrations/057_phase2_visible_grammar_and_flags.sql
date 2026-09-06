-- Phase 2 §4: make the bounded action grammar visible, and give the scanner-profile flag a job.
--
-- Two loose ends the gap audit found.
--
-- `GET /action-types` returned only UPGRADE, because only one `action_capability` row existed.
-- §4 wants the whole bounded vocabulary surfaced — a user cannot see what the product will do
-- next, and an integrator cannot tell a predicate that is planned from one that will never
-- exist. The compiler already reads `lifecycle`, so a DISABLED row is honest and inert: it
-- appears in the grammar and refuses to compile.
--
-- `SCANNER_PROFILES` was seeded and read by no code at all. It now gates the typed estate
-- profile projection, which is the feature it was named for.

INSERT INTO action_capability(
  tenant_id,predicate,subject_type,ontology_version,target_schema,validation_rules,
  scope_rules,semantic_provider,provider_version,lifecycle
) VALUES
  -- Each row states the target state its predicate will require, so the shape of the eventual
  -- contract is visible before the semantics exist to honour it.
  (NULL,'UPGRADE','Runtime','actions/1.0.0',
   '{"type":"object","required":["version"],"properties":{"version":{"type":"string","minLength":1}}}',
   '{"exact_subject":true,"exact_target":true,"require_observed_scope":true,"max_mutations":20}',
   '{"kinds":["ESTATE","REPOSITORY","COMPONENT"],"requires_evidence":true}',
   'runtime-lifecycle','runtime-lifecycle/0.0.0','DISABLED'),
  (NULL,'UPGRADE','Framework','actions/1.0.0',
   '{"type":"object","required":["version"],"properties":{"version":{"type":"string","minLength":1}}}',
   '{"exact_subject":true,"exact_target":true,"require_observed_scope":true,"max_mutations":20}',
   '{"kinds":["ESTATE","REPOSITORY","COMPONENT"],"requires_evidence":true}',
   'package-registry','package-registry/1.0.0','DISABLED'),
  (NULL,'REPLACE','Package','actions/1.0.0',
   '{"type":"object","required":["package"],"properties":{"package":{"type":"string","minLength":1}}}',
   '{"exact_subject":true,"exact_target":true,"require_observed_scope":true,"max_mutations":20}',
   '{"kinds":["ESTATE","REPOSITORY","COMPONENT"],"requires_evidence":true}',
   'package-registry','package-registry/1.0.0','DISABLED'),
  (NULL,'REMOVE','Package','actions/1.0.0',
   '{"type":"object","properties":{}}',
   '{"exact_subject":true,"exact_target":false,"require_observed_scope":true,"max_mutations":20}',
   '{"kinds":["ESTATE","REPOSITORY","COMPONENT"],"requires_evidence":true}',
   'package-registry','package-registry/1.0.0','DISABLED'),
  (NULL,'DEPRECATE','API','actions/1.0.0',
   '{"type":"object","required":["retire_after"],"properties":{"retire_after":{"type":"string","format":"date-time"}}}',
   '{"exact_subject":true,"exact_target":true,"require_observed_scope":true,"max_mutations":20}',
   '{"kinds":["ESTATE","REPOSITORY"],"requires_evidence":true}',
   'api-contract','api-contract/0.0.0','DISABLED'),
  (NULL,'MIGRATE','Database','actions/1.0.0',
   '{"type":"object","required":["platform"],"properties":{"platform":{"type":"string","minLength":1}}}',
   '{"exact_subject":true,"exact_target":true,"require_observed_scope":true,"max_mutations":20}',
   '{"kinds":["ESTATE","REPOSITORY"],"requires_evidence":true}',
   'platform-catalog','platform-catalog/0.0.0','DISABLED'),
  (NULL,'MOVE','Service','actions/1.0.0',
   '{"type":"object","required":["platform"],"properties":{"platform":{"type":"string","minLength":1}}}',
   '{"exact_subject":true,"exact_target":true,"require_observed_scope":true,"max_mutations":20}',
   '{"kinds":["ESTATE","REPOSITORY"],"requires_evidence":true}',
   'platform-catalog','platform-catalog/0.0.0','DISABLED')
ON CONFLICT DO NOTHING;

-- The projection this flag names now exists, so the flag can default on. Turning it off stops
-- typed profiles being written; the read surfaces already degrade to related entities with an
-- explicit coverage status, which is exactly the behaviour a kill switch should produce.
UPDATE phase2_feature_flag SET enabled=true, updated_by='migration:057'
WHERE tenant_id IS NULL AND flag_key='SCANNER_PROFILES';
