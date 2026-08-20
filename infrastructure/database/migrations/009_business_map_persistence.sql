-- Business Map persistence (Lane C gap closure).
--
-- Moves the Business Map workspace off browser localStorage and into tenant-scoped,
-- RLS-isolated, versioned storage. A map owns its own presentation state (lanes,
-- placements, maturity, shared-group overlays, org units, assignments) and a catalog
-- hierarchy (functions -> processes -> capabilities). Catalog rows carry a nullable
-- entity_id so a map function/process/capability can later be linked to its canonical
-- BUSINESS-namespace ontology entity without reshaping the map. Shared groups persist
-- as overlays that reference map capabilities and a stage span, per the standing plan.

CREATE TABLE business_map (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES tenant(id),
  map_key text NOT NULL CHECK(map_key ~ '^[a-z][a-z0-9_.-]{2,127}$'),
  title text NOT NULL CHECK(title <> ''),
  view_mode text NOT NULL DEFAULT 'VALUE_CHAIN' CHECK(view_mode IN ('VALUE_CHAIN','ORGANIZATION')),
  template_id text NOT NULL DEFAULT 'porter',
  status text NOT NULL DEFAULT 'ACTIVE' CHECK(status IN ('DRAFT','ACTIVE','ARCHIVED')),
  version integer NOT NULL DEFAULT 1 CHECK(version > 0),
  metadata jsonb NOT NULL DEFAULT '{}' CHECK(jsonb_typeof(metadata)='object'),
  created_by text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(tenant_id,map_key)
);
CREATE INDEX idx_business_map_tenant ON business_map(tenant_id,status,updated_at DESC);

-- Value-chain stages and organization units share one lane table, discriminated by lane_kind.
CREATE TABLE business_map_lane (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES tenant(id),
  business_map_id uuid NOT NULL REFERENCES business_map(id) ON DELETE CASCADE,
  lane_kind text NOT NULL CHECK(lane_kind IN ('STAGE','ORG_UNIT')),
  lane_key text NOT NULL CHECK(lane_key <> ''),
  label text NOT NULL CHECK(label <> ''),
  sublabel text NOT NULL DEFAULT '',
  color text NOT NULL DEFAULT '',
  gradient text NOT NULL DEFAULT '',
  icon text NOT NULL DEFAULT '',
  position integer NOT NULL CHECK(position >= 0),
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(business_map_id,lane_kind,lane_key)
);
CREATE INDEX idx_business_map_lane_map ON business_map_lane(tenant_id,business_map_id,lane_kind,position);

CREATE TABLE business_map_function (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES tenant(id),
  business_map_id uuid NOT NULL REFERENCES business_map(id) ON DELETE CASCADE,
  function_key text NOT NULL CHECK(function_key <> ''),
  entity_id uuid REFERENCES entity(id) ON DELETE SET NULL,
  name text NOT NULL CHECK(name <> ''),
  description text NOT NULL DEFAULT '',
  color text NOT NULL DEFAULT '',
  gradient text NOT NULL DEFAULT '',
  icon text NOT NULL DEFAULT '',
  position integer NOT NULL CHECK(position >= 0),
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(business_map_id,function_key)
);
CREATE INDEX idx_business_map_function_map ON business_map_function(tenant_id,business_map_id,position);

CREATE TABLE business_map_process (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES tenant(id),
  business_map_id uuid NOT NULL REFERENCES business_map(id) ON DELETE CASCADE,
  business_map_function_id uuid NOT NULL REFERENCES business_map_function(id) ON DELETE CASCADE,
  process_key text NOT NULL CHECK(process_key <> ''),
  entity_id uuid REFERENCES entity(id) ON DELETE SET NULL,
  name text NOT NULL CHECK(name <> ''),
  description text NOT NULL DEFAULT '',
  position integer NOT NULL CHECK(position >= 0),
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(business_map_id,process_key)
);
CREATE INDEX idx_business_map_process_function
  ON business_map_process(tenant_id,business_map_function_id,position);

CREATE TABLE business_map_capability (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES tenant(id),
  business_map_id uuid NOT NULL REFERENCES business_map(id) ON DELETE CASCADE,
  business_map_process_id uuid NOT NULL REFERENCES business_map_process(id) ON DELETE CASCADE,
  capability_key text NOT NULL CHECK(capability_key <> ''),
  entity_id uuid REFERENCES entity(id) ON DELETE SET NULL,
  name text NOT NULL CHECK(name <> ''),
  description text NOT NULL DEFAULT '',
  tags text[] NOT NULL DEFAULT '{}',
  kpis text[] NOT NULL DEFAULT '{}',
  owner text,
  position integer NOT NULL CHECK(position >= 0),
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(business_map_id,capability_key)
);
CREATE INDEX idx_business_map_capability_process
  ON business_map_capability(tenant_id,business_map_process_id,position);
CREATE INDEX idx_business_map_capability_entity
  ON business_map_capability(tenant_id,entity_id) WHERE entity_id IS NOT NULL;

-- One placement per capability on the canvas; lane_id NULL means the capability is
-- in the library but not yet placed on a stage.
CREATE TABLE business_map_placement (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES tenant(id),
  business_map_id uuid NOT NULL REFERENCES business_map(id) ON DELETE CASCADE,
  business_map_capability_id uuid NOT NULL
    REFERENCES business_map_capability(id) ON DELETE CASCADE,
  lane_id uuid REFERENCES business_map_lane(id) ON DELETE SET NULL,
  source_function_id uuid REFERENCES business_map_function(id) ON DELETE SET NULL,
  maturity smallint NOT NULL DEFAULT 2 CHECK(maturity BETWEEN 1 AND 5),
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(business_map_id,business_map_capability_id)
);
CREATE INDEX idx_business_map_placement_lane
  ON business_map_placement(tenant_id,business_map_id,lane_id);

-- Shared-capability overlays: a named span across stages that references map capabilities.
CREATE TABLE business_map_shared_group (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES tenant(id),
  business_map_id uuid NOT NULL REFERENCES business_map(id) ON DELETE CASCADE,
  group_key text NOT NULL CHECK(group_key <> ''),
  name text NOT NULL CHECK(name <> ''),
  description text NOT NULL DEFAULT '',
  start_lane_id uuid REFERENCES business_map_lane(id) ON DELETE CASCADE,
  end_lane_id uuid REFERENCES business_map_lane(id) ON DELETE CASCADE,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(business_map_id,group_key)
);
CREATE INDEX idx_business_map_shared_group_map
  ON business_map_shared_group(tenant_id,business_map_id);

CREATE TABLE business_map_shared_group_member (
  tenant_id uuid NOT NULL REFERENCES tenant(id),
  shared_group_id uuid NOT NULL
    REFERENCES business_map_shared_group(id) ON DELETE CASCADE,
  business_map_capability_id uuid NOT NULL
    REFERENCES business_map_capability(id) ON DELETE CASCADE,
  PRIMARY KEY(shared_group_id,business_map_capability_id)
);

-- Function -> organization-unit assignment (lane_id must reference an ORG_UNIT lane;
-- enforced in the service layer since a partial FK cannot span the discriminator).
CREATE TABLE business_map_function_assignment (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES tenant(id),
  business_map_id uuid NOT NULL REFERENCES business_map(id) ON DELETE CASCADE,
  business_map_function_id uuid NOT NULL
    REFERENCES business_map_function(id) ON DELETE CASCADE,
  lane_id uuid REFERENCES business_map_lane(id) ON DELETE CASCADE,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(business_map_id,business_map_function_id)
);
CREATE INDEX idx_business_map_assignment_lane
  ON business_map_function_assignment(tenant_id,lane_id);

-- Optimistic-concurrency audit trail: one immutable snapshot per saved version.
CREATE TABLE business_map_revision (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES tenant(id),
  business_map_id uuid NOT NULL REFERENCES business_map(id) ON DELETE CASCADE,
  version integer NOT NULL CHECK(version > 0),
  snapshot jsonb NOT NULL CHECK(jsonb_typeof(snapshot)='object'),
  actor_key text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(business_map_id,version)
);
CREATE INDEX idx_business_map_revision_map
  ON business_map_revision(tenant_id,business_map_id,version DESC);

ALTER TABLE business_map ENABLE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON business_map
  USING(tenant_id=stackgraph_current_tenant_id())
  WITH CHECK(tenant_id=stackgraph_current_tenant_id());
ALTER TABLE business_map_lane ENABLE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON business_map_lane
  USING(tenant_id=stackgraph_current_tenant_id())
  WITH CHECK(tenant_id=stackgraph_current_tenant_id());
ALTER TABLE business_map_function ENABLE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON business_map_function
  USING(tenant_id=stackgraph_current_tenant_id())
  WITH CHECK(tenant_id=stackgraph_current_tenant_id());
ALTER TABLE business_map_process ENABLE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON business_map_process
  USING(tenant_id=stackgraph_current_tenant_id())
  WITH CHECK(tenant_id=stackgraph_current_tenant_id());
ALTER TABLE business_map_capability ENABLE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON business_map_capability
  USING(tenant_id=stackgraph_current_tenant_id())
  WITH CHECK(tenant_id=stackgraph_current_tenant_id());
ALTER TABLE business_map_placement ENABLE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON business_map_placement
  USING(tenant_id=stackgraph_current_tenant_id())
  WITH CHECK(tenant_id=stackgraph_current_tenant_id());
ALTER TABLE business_map_shared_group ENABLE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON business_map_shared_group
  USING(tenant_id=stackgraph_current_tenant_id())
  WITH CHECK(tenant_id=stackgraph_current_tenant_id());
ALTER TABLE business_map_shared_group_member ENABLE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON business_map_shared_group_member
  USING(tenant_id=stackgraph_current_tenant_id())
  WITH CHECK(tenant_id=stackgraph_current_tenant_id());
ALTER TABLE business_map_function_assignment ENABLE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON business_map_function_assignment
  USING(tenant_id=stackgraph_current_tenant_id())
  WITH CHECK(tenant_id=stackgraph_current_tenant_id());
ALTER TABLE business_map_revision ENABLE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON business_map_revision
  USING(tenant_id=stackgraph_current_tenant_id())
  WITH CHECK(tenant_id=stackgraph_current_tenant_id());
