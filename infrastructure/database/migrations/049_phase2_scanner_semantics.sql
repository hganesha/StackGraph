-- Phase 2 scanner 1.11: component build and immutable base-image relationships.

INSERT INTO predicate_definition(predicate,object_kind,projects_as_edge,contract_version)
VALUES
  ('BUILDS','ENTITY',true,'1.1.0'),
  ('BASED_ON','ENTITY',true,'1.1.0')
ON CONFLICT(predicate) DO UPDATE SET
  object_kind=EXCLUDED.object_kind,
  projects_as_edge=EXCLUDED.projects_as_edge,
  contract_version=EXCLUDED.contract_version;
