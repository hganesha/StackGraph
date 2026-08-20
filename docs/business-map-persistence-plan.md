# Business Map persistence — schema + API plan

**Updated:** 2026-08-19
**Status:** Implemented and verified — schema (migration 009), API routes, persistence layer,
typed shared client (fixture + live), and the workspace UI swap are all built.

## Verification

- Schema: full-`schema.sql` apply + incremental 009 delta on the prior baseline + cross-tenant RLS
  isolation (read and `WITH CHECK`) under a non-superuser role.
- API/persistence: in-process ASGI E2E — create (201), list, get, save with optimistic
  `expected_version` (200 + version bump), stale save (`409 VERSION_CONFLICT`), dangling reference
  (`422 BUSINESS_MAP_INVALID_REFERENCE`), revisions history, duplicate key (`409`), archive (soft) +
  archived-edit rejection.
- Contract: the three frozen-OpenAPI/schema conformance tests still pass (new routes are additive).
- Web: `@stackgraph/shared` and `@stackgraph/web` typecheck clean; the workspace renders API-backed
  state in fixture mode with no console/server errors.

Closes the Lane C gap where the Business Map workspace had browser-`localStorage`-only CRUD
([`useBusinessMap.ts`](../apps/web/features/business-map/useBusinessMap.ts), key
`stackgraph.business-map.v3`) with no server persistence, tenancy, or audit.

## Delivered: schema (migration 009)

[`009_business_map_persistence.sql`](../infrastructure/database/migrations/009_business_map_persistence.sql),
folded into [`schema.sql`](../stackgraph-foundation/schema.sql) and registered
(`checksum 9d32af5f…`). Verified: full-schema apply, incremental delta apply on the prior
baseline, and cross-tenant RLS isolation (read + `WITH CHECK`) under a non-superuser role.

Ten tenant-scoped, RLS-isolated tables:

| Table | Holds | Client state mapped |
| --- | --- | --- |
| `business_map` | Map aggregate + `version` (optimistic concurrency) | `title`, `viewMode`, `templateId` |
| `business_map_lane` | Stages **and** org units (`lane_kind`) | `stages[]`, `organizationUnits[]` |
| `business_map_function` | Catalog function; nullable `entity_id` → canonical `BusinessFunction` | `catalog[]` |
| `business_map_process` | Catalog process; nullable `entity_id` → `BusinessProcess` | `catalog[].processes[]` |
| `business_map_capability` | Catalog capability; nullable `entity_id` → `BusinessCapability` | `…capabilities[]` |
| `business_map_placement` | Capability on a lane + `maturity` (1–5); `lane_id` NULL = unplaced | `placements[]` |
| `business_map_shared_group` | Overlay with a stage span (`start_lane_id`…`end_lane_id`) | `sharedGroups[]` |
| `business_map_shared_group_member` | Overlay ↔ capability membership | `sharedGroups[].capabilityIds` |
| `business_map_function_assignment` | Function → org-unit lane | `functionAssignments[]` |
| `business_map_revision` | Immutable per-version snapshot (audit) | — |

**Design choices**
- `entity_id` FKs are **nullable** so the client-seeded catalog persists today and can later be
  linked to canonical BUSINESS-namespace ontology entities without reshaping the map.
- Shared groups are **overlays** referencing map capabilities + a stage span (per the standing
  recommendation), not new ontology types.
- Client-side ids (`porter:0`, `function:uuid`) persist as `*_key` columns; DB rows get their own
  UUIDs. The service maps `key ↔ id` so the UI contract is unchanged.
- `view_mode` stored uppercase (`VALUE_CHAIN`/`ORGANIZATION`) per DB enum convention; layer maps to
  the UI's `value-chain`/`organization`.

## Planned: API routes

The API today has **no domain-mutation convention** — only read + "review" verbs. Business Map is
the first true CRUD aggregate. Proposed routes (mounted on the same `/api/v1` router):

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/business-maps` | List maps for the tenant (cursor-paginated) |
| POST | `/business-maps` | Create a map (seed default stages/catalog server-side) |
| GET | `/business-maps/{id}` | Full map state (single hydrated payload the workspace loads) |
| PUT | `/business-maps/{id}` | Replace map state with optimistic `expected_version`; writes a `business_map_revision` and bumps `version` |
| DELETE | `/business-maps/{id}` | Archive (soft: `status='ARCHIVED'`) |
| GET | `/business-maps/{id}/revisions` | Revision history |

A whole-map `PUT` (read-modify-write with `expected_version`) matches how the workspace already
holds the entire map in memory and debounce-saves it — simpler and less chatty than per-entity CRUD,
and it maps 1:1 onto the current `setMap` reducer. Per-entity routes can be added later if partial
saves are needed.

**Concurrency:** reuse the `identity_assertion` pattern
([`read_models.py:1494`](../apps/api/app/read_models.py)) — `SELECT … FOR UPDATE`, compare
`version` to `expected_version`, `409 VERSION_CONFLICT` on mismatch, else write revision + bump.

## Planned: persistence + models + client

1. **`models.py`** — `BusinessMapSummary`, `BusinessMapDetail` (+ nested lane/function/process/
   capability/placement/shared-group/assignment models), `BusinessMapSaveRequest` with
   `expected_version`.
2. **`read_models.py`** — `list_business_maps`, `business_map_detail`, `create_business_map`,
   `save_business_map` (transactional replace: diff or delete-and-reinsert children under the map,
   all inside `database.session(tenant_id)`), `archive_business_map`.
3. **`routes.py`** — six handlers following the `_principal`/`_store` pattern.
4. **`packages/shared`** — extend `StackGraphClient` (fixture + live) with the six methods; add a
   `business-map-detail.json` fixture.
5. **`useBusinessMap.ts`** — swap the `localStorage` effect for `GET` hydrate + debounced `PUT`,
   keeping `localStorage` as an offline draft cache. No change to the reducer/UI.

## RBAC gate (implemented)

Capabilities follow a graded ladder **view → review → execute → admin** (each tier implies the
earlier ones), enforced identically on both ends:

- `Principal` ([auth.py](../apps/api/app/auth.py)) now carries `capabilities: frozenset[str]` with a
  `has_capability(tier)` ladder check. Development mode grants `admin`; a signed session reads
  `capabilities` from the token (`create_session_token` accepts them) and defaults to `{"view"}`
  (least privilege) when absent.
- Business Map routes ([routes.py](../apps/api/app/routes.py)) gate through `_require(principal, …)`:
  reads (`list`/`get`/`revisions`) require `view`; writes (`create`/`save`/`archive`) require
  `execute`. A lacking capability returns `403 FORBIDDEN` with `details.required_capability` before
  the store is touched. Existing read/review routes are unchanged.
- The web session model ([session.ts](../apps/web/lib/session.ts)) uses the same ladder, and
  `useBusinessMap` only creates/saves on the server when the session can `execute` — a view-only
  session stays on the local draft. Backend tests cover both the 403 and the allowed path.

## Follow-ups (separate Lane C gaps, not this slice)

- A `GET /session` (or `/me`) endpoint so the web `session.ts` mock is replaced by real
  server-issued capabilities; extend the same gate to the existing review routes.
- Projection: emit `business_map` changes to `projection_outbox` only if maps should appear in the
  graph — likely **not** needed; the map is a presentation aggregate, not canonical facts.
