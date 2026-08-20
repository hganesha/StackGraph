-- Admin surfaces and the cross-estate review queue (Lane admin + reviews gap closure).
--
-- Two related gaps closed together:
--   * The Admin workspace (Members/RBAC, Connections, Scan & Refresh) was entirely mock
--     `useState` in the web app with no backend representation. This adds the tenant-scoped,
--     RLS-isolated tables the admin API writes: the member roster + role tier, registered
--     connectors, per-tenant scan policy, idempotent rescan jobs, per-provider quota/backoff
--     read state, and an append-only admin audit trail.
--   * The Reviews page synthesized its queue from one demo neighborhood. No new storage is
--     needed for the queue itself -- it aggregates the five existing reviewable tables -- but
--     this migration adds the partial indexes that make the "pending items, newest first,
--     keyset-paginated" query cheap on each source.

-- tenant_member: the workspace roster and each member's role on the capability ladder
-- (view -> review -> execute -> admin, each tier implying the earlier ones; mirrors
-- apps/api/app/auth.py CAPABILITY_LADDER). This is the RBAC management surface; the signed
-- session in auth.py remains the enforcement point at request time.
CREATE TABLE tenant_member (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES tenant(id),
  actor_key text NOT NULL CHECK(actor_key <> ''),
  display_name text NOT NULL DEFAULT '',
  email text NOT NULL DEFAULT '',
  role text NOT NULL DEFAULT 'view' CHECK(role IN ('view','review','execute','admin')),
  status text NOT NULL DEFAULT 'INVITED' CHECK(status IN ('INVITED','ACTIVE','SUSPENDED')),
  created_by text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(tenant_id,actor_key)
);
CREATE INDEX idx_tenant_member_tenant ON tenant_member(tenant_id,role,status);

-- connector: an admin-registered source/registry connection. Stores only an opaque
-- credential_reference (a pointer into the secret store) -- never a raw token, PAT, or
-- password; the service layer rejects secret-looking values and the reference is never
-- returned in an API response. Distinct from the ingestion-internal source_system /
-- connector_account plumbing: this is the tenant-facing onboarding record that the
-- Admin > Connections surface manages.
CREATE TABLE connector (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES tenant(id),
  provider text NOT NULL CHECK(provider IN ('GITHUB_APP','PACKAGE_REGISTRY','DEPS_DEV','OSV','OTHER')),
  display_name text NOT NULL CHECK(display_name <> ''),
  external_account_key text NOT NULL DEFAULT '',
  credential_reference text NOT NULL DEFAULT '',
  scopes text[] NOT NULL DEFAULT '{}',
  status text NOT NULL DEFAULT 'CONNECTED'
    CHECK(status IN ('CONNECTED','NEEDS_REAUTH','DISABLED','REVOKED')),
  last_synced_at timestamptz,
  last_error text,
  metadata jsonb NOT NULL DEFAULT '{}' CHECK(jsonb_typeof(metadata)='object'),
  created_by text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(tenant_id,provider,external_account_key)
);
CREATE INDEX idx_connector_tenant ON connector(tenant_id,status,updated_at DESC);

-- scan_policy: one row per tenant. Controls how often connected sources are rescanned.
-- The scheduler reads this to create work; workers never invent their own loops.
CREATE TABLE scan_policy (
  tenant_id uuid PRIMARY KEY REFERENCES tenant(id),
  cadence text NOT NULL DEFAULT 'DAILY' CHECK(cadence IN ('HOURLY','DAILY','WEEKLY','MANUAL')),
  enabled boolean NOT NULL DEFAULT true,
  updated_by text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

-- rescan_job: an operator-requested refresh. Creation is idempotent per
-- (tenant, idempotency_key): a repeated key returns the existing job instead of
-- enqueueing a duplicate. A NULL connector_id means a full-estate rescan. The
-- scheduler/worker fleet advances status; the API only creates and reads.
CREATE TABLE rescan_job (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES tenant(id),
  connector_id uuid REFERENCES connector(id) ON DELETE SET NULL,
  idempotency_key text NOT NULL CHECK(idempotency_key <> ''),
  status text NOT NULL DEFAULT 'PENDING'
    CHECK(status IN ('PENDING','RUNNING','SUCCEEDED','FAILED')),
  reason text NOT NULL DEFAULT '',
  requested_by text NOT NULL,
  last_error text,
  created_at timestamptz NOT NULL DEFAULT now(),
  started_at timestamptz,
  completed_at timestamptz,
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(tenant_id,idempotency_key)
);
CREATE INDEX idx_rescan_job_tenant ON rescan_job(tenant_id,created_at DESC,id DESC);

-- connector_quota: per-provider rate-limit and backoff state, written by the ingestion
-- workers and read by Admin > Scan & Refresh so throttling reads as intentional rather
-- than as failure. One row per (tenant, provider); limit_value NULL means "unmetered".
CREATE TABLE connector_quota (
  tenant_id uuid NOT NULL REFERENCES tenant(id),
  provider text NOT NULL CHECK(provider IN ('GITHUB_APP','PACKAGE_REGISTRY','DEPS_DEV','OSV','OTHER')),
  used integer NOT NULL DEFAULT 0 CHECK(used >= 0),
  limit_value integer CHECK(limit_value IS NULL OR limit_value >= 0),
  status text NOT NULL DEFAULT 'OK' CHECK(status IN ('OK','THROTTLED','EXHAUSTED')),
  resets_at timestamptz,
  backoff_until timestamptz,
  observed_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY(tenant_id,provider)
);

-- admin_audit_log: append-only trail for every admin mutation (member, connector, policy,
-- rescan). The Admin surface promises that "every change here is audited".
CREATE TABLE admin_audit_log (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES tenant(id),
  actor_key text NOT NULL,
  action text NOT NULL CHECK(action <> ''),
  target_kind text NOT NULL,
  target_id text NOT NULL DEFAULT '',
  detail jsonb NOT NULL DEFAULT '{}' CHECK(jsonb_typeof(detail)='object'),
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX idx_admin_audit_log_tenant ON admin_audit_log(tenant_id,created_at DESC,id DESC);

ALTER TABLE tenant_member ENABLE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON tenant_member
  USING(tenant_id=stackgraph_current_tenant_id())
  WITH CHECK(tenant_id=stackgraph_current_tenant_id());
ALTER TABLE connector ENABLE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON connector
  USING(tenant_id=stackgraph_current_tenant_id())
  WITH CHECK(tenant_id=stackgraph_current_tenant_id());
ALTER TABLE scan_policy ENABLE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON scan_policy
  USING(tenant_id=stackgraph_current_tenant_id())
  WITH CHECK(tenant_id=stackgraph_current_tenant_id());
ALTER TABLE rescan_job ENABLE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON rescan_job
  USING(tenant_id=stackgraph_current_tenant_id())
  WITH CHECK(tenant_id=stackgraph_current_tenant_id());
ALTER TABLE connector_quota ENABLE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON connector_quota
  USING(tenant_id=stackgraph_current_tenant_id())
  WITH CHECK(tenant_id=stackgraph_current_tenant_id());
ALTER TABLE admin_audit_log ENABLE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON admin_audit_log
  USING(tenant_id=stackgraph_current_tenant_id())
  WITH CHECK(tenant_id=stackgraph_current_tenant_id());

-- Review-queue accelerators: each source is filtered to its pending state and ordered
-- newest-first with a keyset tiebreak on id, matching GET /reviews/queue. Partial indexes
-- keep them small -- only the not-yet-reviewed rows -- and shrink as items are decided.
CREATE INDEX idx_identity_assertion_review_queue
  ON identity_assertion(created_at DESC,id DESC) WHERE review_state='POSSIBLE';
CREATE INDEX idx_capability_inference_review_queue
  ON capability_inference(created_at DESC,id DESC) WHERE review_state='UNREVIEWED';
CREATE INDEX idx_duplicate_capability_review_queue
  ON duplicate_capability_candidate(created_at DESC,id DESC) WHERE review_state='UNREVIEWED';
CREATE INDEX idx_modernization_candidate_review_queue
  ON modernization_candidate(created_at DESC,id DESC) WHERE review_state='UNREVIEWED';
CREATE INDEX idx_modernization_recommendation_review_queue
  ON modernization_recommendation(created_at DESC,id DESC) WHERE review_state='UNREVIEWED';
