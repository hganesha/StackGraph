-- The worker resolves encrypted tenant_secret rows in production and env:// references locally.
-- Do not accept external-secret reference schemes until a concrete resolver is installed.

ALTER TABLE tenant_graph_deployment
  ADD CONSTRAINT tenant_graph_deployment_supported_credential_reference
  CHECK(credential_reference IS NULL OR credential_reference ~ '^env://[A-Za-z0-9_]+$');
