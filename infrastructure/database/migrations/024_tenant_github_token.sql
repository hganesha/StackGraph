-- Tenant-scoped, write-only GitHub development tokens use the existing encrypted
-- secret store. The API never returns ciphertext or plaintext; workers resolve the
-- opaque tenant-secret://github-token reference at acquisition time.

ALTER TABLE tenant_secret
  DROP CONSTRAINT tenant_secret_secret_kind_check;

ALTER TABLE tenant_secret
  ADD CONSTRAINT tenant_secret_secret_kind_check
  CHECK(secret_kind IN ('AI_PROVIDER_KEY','GITHUB_TOKEN'));

CREATE UNIQUE INDEX uq_tenant_secret_github_token
  ON tenant_secret(tenant_id,secret_kind)
  WHERE secret_kind='GITHUB_TOKEN';
