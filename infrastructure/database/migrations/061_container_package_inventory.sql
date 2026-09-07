-- Reading the packages installed inside a container image.
--
-- `estate_container_package` has existed since the container profile did and has never had a
-- writer, so `coverage.os_packages` has always said NOT_COLLECTED. That is honest but thin: an
-- image's OS packages are exactly where a CVE lands, and "we did not look" cannot be acted on.
--
-- Reading them means downloading and opening layer blobs, which is by an order of magnitude the
-- most expensive and most exposed thing StackGraph does over the network. It gets its own flag
-- rather than riding on REGISTRY_ENRICHMENT, because an operator who is willing to let
-- StackGraph read a manifest has not thereby agreed to let it pull hundreds of megabytes of
-- layer per image.

ALTER TABLE phase2_feature_flag DROP CONSTRAINT IF EXISTS phase2_feature_flag_flag_key_check;
ALTER TABLE phase2_feature_flag ADD CONSTRAINT phase2_feature_flag_flag_key_check
  CHECK(flag_key IN (
    'SCANNER_PROFILES','CHANGE_COMPILER','CHANGE_SIMULATION','AI_INTERPRETATION',
    'CHANGE_EXECUTION','REGISTRY_ENRICHMENT','ADVERSARIAL_EVALUATION',
    'CONTAINER_PACKAGE_INVENTORY'
  ));

INSERT INTO phase2_feature_flag(tenant_id,flag_key,enabled,updated_by) VALUES
  (NULL,'CONTAINER_PACKAGE_INVENTORY',false,'migration:061')
ON CONFLICT DO NOTHING;

-- Which database each package came from, so a reader can tell a dpkg entry from a package.json
-- found in an image's node_modules. Without it the two are one undifferentiated list, and an
-- application dependency baked into an image would read as an OS package.
ALTER TABLE estate_container_package
  ADD COLUMN IF NOT EXISTS source text
    CHECK(source IS NULL OR source IN ('dpkg','apk','rpm','python','npm'));

COMMENT ON COLUMN estate_container_package.source IS
  'The package database the record was read from. RPM databases are detected but never parsed: '
  'they are Berkeley DB, ndb, or SQLite depending on the distribution, and a confident wrong '
  'answer about what is installed is worse than a reported gap.';
