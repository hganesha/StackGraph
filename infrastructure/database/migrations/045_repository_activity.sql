-- Bounded, tenant-scoped GitHub development activity for repository summaries.

CREATE TABLE IF NOT EXISTS repository_activity_collection (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES tenant(id),
  repository_entity_id uuid NOT NULL REFERENCES entity(id) ON DELETE CASCADE,
  source_key text NOT NULL CHECK(source_key<>''),
  window_started_at timestamptz NOT NULL,
  window_ended_at timestamptz NOT NULL,
  commits_status text NOT NULL CHECK(commits_status IN (
    'AVAILABLE','PARTIAL','NOT_COLLECTED','PERMISSION_REQUIRED','ERROR'
  )),
  pull_requests_status text NOT NULL CHECK(pull_requests_status IN (
    'AVAILABLE','PARTIAL','NOT_COLLECTED','PERMISSION_REQUIRED','ERROR'
  )),
  limitations jsonb NOT NULL DEFAULT '[]' CHECK(jsonb_typeof(limitations)='array'),
  collected_at timestamptz NOT NULL DEFAULT now(),
  CHECK(window_ended_at>=window_started_at),
  UNIQUE(tenant_id,repository_entity_id,source_key)
);

CREATE TABLE IF NOT EXISTS repository_activity_event (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES tenant(id),
  repository_entity_id uuid NOT NULL REFERENCES entity(id) ON DELETE CASCADE,
  provider text NOT NULL CHECK(provider IN ('GITHUB')),
  provider_event_key text NOT NULL CHECK(provider_event_key<>''),
  event_type text NOT NULL CHECK(event_type IN (
    'COMMIT','PULL_REQUEST_OPENED','PULL_REQUEST_MERGED'
  )),
  occurred_at timestamptz NOT NULL,
  title text NOT NULL CHECK(title<>''),
  actor_key text,
  actor_login text,
  actor_avatar_url text,
  actor_is_bot boolean NOT NULL DEFAULT false,
  revision text,
  branch text,
  pull_request_number integer CHECK(pull_request_number IS NULL OR pull_request_number>0),
  source_url text,
  metadata jsonb NOT NULL DEFAULT '{}' CHECK(jsonb_typeof(metadata)='object'),
  observed_at timestamptz NOT NULL DEFAULT now(),
  CHECK((actor_key IS NULL)=(actor_login IS NULL)),
  CHECK(actor_avatar_url IS NULL OR actor_avatar_url ~ '^https://'),
  CHECK(source_url IS NULL OR source_url ~ '^https://'),
  UNIQUE(tenant_id,repository_entity_id,provider,provider_event_key)
);

CREATE INDEX IF NOT EXISTS idx_repository_activity_event_timeline
  ON repository_activity_event(tenant_id,repository_entity_id,occurred_at DESC,id DESC);
CREATE INDEX IF NOT EXISTS idx_repository_activity_event_actor
  ON repository_activity_event(tenant_id,repository_entity_id,actor_key,occurred_at DESC)
  WHERE actor_key IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_repository_activity_collection_freshness
  ON repository_activity_collection(tenant_id,repository_entity_id,collected_at DESC);

ALTER TABLE repository_activity_collection ENABLE ROW LEVEL SECURITY;
ALTER TABLE repository_activity_event ENABLE ROW LEVEL SECURITY;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_policies WHERE schemaname='public'
      AND tablename='repository_activity_collection' AND policyname='tenant_isolation'
  ) THEN
    CREATE POLICY tenant_isolation ON repository_activity_collection
      USING(tenant_id=stackgraph_current_tenant_id())
      WITH CHECK(tenant_id=stackgraph_current_tenant_id());
  END IF;
  IF NOT EXISTS (
    SELECT 1 FROM pg_policies WHERE schemaname='public'
      AND tablename='repository_activity_event' AND policyname='tenant_isolation'
  ) THEN
    CREATE POLICY tenant_isolation ON repository_activity_event
      USING(tenant_id=stackgraph_current_tenant_id())
      WITH CHECK(tenant_id=stackgraph_current_tenant_id());
  END IF;
END $$;
