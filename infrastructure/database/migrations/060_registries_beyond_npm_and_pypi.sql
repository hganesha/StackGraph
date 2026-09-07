-- Registry coverage beyond npm and PyPI.
--
-- `package_registry.ecosystem` admitted NPM, PYPI, MAVEN, CARGO, and OTHER. A Go module or a
-- NuGet package could only be recorded as OTHER, which is a shape the catalogue enumerator
-- cannot act on: it has to know which registry protocol to speak. Recording an ecosystem as
-- "other" and then reporting its packages as having no upgrade targets is the failure this
-- migration removes.
--
-- OTHER is kept. A registry StackGraph has no adapter for is a real thing to record, and
-- recording it as OTHER is the honest answer — the catalogue then reports it uncollected
-- rather than reporting the package as having two releases.

ALTER TABLE package_registry DROP CONSTRAINT IF EXISTS package_registry_ecosystem_check;
ALTER TABLE package_registry ADD CONSTRAINT package_registry_ecosystem_check
  CHECK(ecosystem IN ('NPM','PYPI','MAVEN','CARGO','NUGET','GO','OTHER'));

-- `package_version_catalog` already admitted every one of these ecosystems and already carries
-- the lookup index. Nothing ever wrote a row for them because no dependency carried the
-- registry identity to enumerate from; that is fixed in the ingest, not here.

COMMENT ON CONSTRAINT package_registry_ecosystem_check ON package_registry IS
  'The ecosystems StackGraph holds a registry adapter for, plus OTHER for a registry it can '
  'record but not enumerate. A package in an OTHER registry reports its catalogue as '
  'uncollected rather than empty.';
