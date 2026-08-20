-- Persist access/refresh token revocations so logout and refresh rotation work
-- across API replicas and survive process restarts.

CREATE TABLE auth_token_revocation (
  tenant_id uuid NOT NULL REFERENCES tenant(id) ON DELETE CASCADE,
  jti uuid NOT NULL,
  actor_key text NOT NULL CHECK (actor_key <> ''),
  token_type text NOT NULL CHECK (token_type IN ('access','refresh')),
  expires_at timestamptz NOT NULL,
  reason text NOT NULL CHECK (reason <> ''),
  revoked_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (tenant_id,jti)
);

CREATE INDEX idx_auth_token_revocation_expiry
  ON auth_token_revocation(expires_at);

ALTER TABLE auth_token_revocation ENABLE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON auth_token_revocation
  USING (tenant_id=stackgraph_current_tenant_id())
  WITH CHECK (tenant_id=stackgraph_current_tenant_id());

-- Shared fixed-window counters make per-tenant abuse controls consistent across
-- API replicas. Windows are deliberately short-lived and contain no request data.
CREATE TABLE api_rate_limit_window (
  tenant_id uuid NOT NULL REFERENCES tenant(id) ON DELETE CASCADE,
  actor_key text NOT NULL CHECK (actor_key <> ''),
  route_bucket text NOT NULL CHECK (route_bucket IN ('general','ask')),
  window_started_at timestamptz NOT NULL,
  request_count integer NOT NULL DEFAULT 1 CHECK (request_count > 0),
  PRIMARY KEY (tenant_id,actor_key,route_bucket,window_started_at)
);

CREATE INDEX idx_api_rate_limit_window_expiry
  ON api_rate_limit_window(window_started_at);

ALTER TABLE api_rate_limit_window ENABLE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON api_rate_limit_window
  USING (tenant_id=stackgraph_current_tenant_id())
  WITH CHECK (tenant_id=stackgraph_current_tenant_id());
