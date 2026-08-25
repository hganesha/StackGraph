# User Actions — Gap Analysis & Proposal

**Status:** all five actions (§2.1–§2.5) implemented
**Audience:** business users of StackGraph — CTOs, EAs, platform leads, application owners — as distinct from admins configuring the tenant
**Author context:** StackGraph's read surfaces (Estate, Application/Technology Explorer, Modernization, Ask) are strong, but the app is still mostly a *reporting* tool. A business user who reaches a conclusion on screen ("this recommendation should ship," "this bridge is wrong," "this app's owner changed") today has almost nowhere to act on it. This doc inventories that gap and proposes the missing actions.

This was prompted by three examples the user raised: exporting recommendations for implementation, changing status on review-queue findings, and editing application/repo details. The audit below (of `stackgraph-foundation/contracts/v1`, `apps/api/app/routes.py`, and `apps/web`) turned up a fourth, larger gap in the same family: four of six review-queue finding types have a working backend + client SDK method but **no button anywhere** to use them.

---

## 1. Where StackGraph already gets this right

Worth naming because it's the template to copy, not reinvent:

- **Business Map** (`apps/web/features/business-map/useBusinessMap.ts`) — full CRUD (add/update/delete capability, function, process, org unit), backed by `POST/PUT/DELETE /business-maps`, with `localStorage` only as an offline cache.
- **Identity bridge review** (`UncertainBridge.tsx` on the Reviews queue and in the graph lens) — Confirm/Reject with required rationale, optimistic concurrency (`expected_version`, 409-safe).
- **Application similarity review** (`SimilarityDecision.tsx`) — four-way decision (similar / distinct / consolidate / dismiss).
- **Admin → Architecture Profiles** — clean draft-then-publish lifecycle (`useCreateArchitectureProfile` → `usePublishArchitectureProfile`).

Every proposal below should look like one of these, not invent a new pattern.

---

## 2. Proposed actions

### 2.1 Export a recommendation (or a set of them) for implementation — ✅ implemented

**Shipped:** per-recommendation "Export as Markdown" on `RecommendationFocus.tsx` (`apps/web/lib/exportRecommendation.ts`, `apps/web/app/repositories/[id]/RecommendationFocus.tsx`), generated client-side from data already on the page (title, rationale, migration plan, rollback plan, validation gaps, affected modules) — no new backend endpoint needed. Scoped to the single-recommendation case, where the full detail (migration/rollback plan) is already loaded; the ranked list on `/modernization` only carries summary fields, so a bulk "export selected" would need a fetch loop per item and was left for a follow-up if it turns out to be wanted.

**Original gap:** zero export capability anywhere — no client method, no route, no button (`grep -i export` across `apps/web` and `apps/api/app` is empty).

**Proposal:**
- On the **Modernization Dashboard** (`/modernization`) and on `RecommendationFocus.tsx` (repository-scoped recommendation detail): an **"Export"** action per recommendation and a **"Export selected"** bulk action on the ranked list.
- Format: Markdown, one file per recommendation (or one file with sections for a bulk export) — this is a document a human hands to an engineer or pastes into a ticket, not machine-consumed JSON. Include: title, affected repository/application, rationale, migration plan / steps, rollback plan, evidence citations (as links back to StackGraph), current `review_state`, and confidence.
- Ship as a `GET /modernization-recommendations/{id}/export?format=md` (and a `POST /modernization-recommendations/export` for bulk-by-id-list) that streams the file — keeps the formatting logic server-side, next to the data, instead of duplicating template logic in the client.
- Natural pairing: this is far more useful once §2.2 exists, since "export" only matters for something the user has actually decided to accept.

### 2.2 Wire up the four dormant review-queue actions — ✅ implemented

**Shipped:** `apps/web/lib/reviews.ts` (`useOptimisticReviewMutation` factory + `useReviewModernizationRecommendation`), `apps/web/components/reviews/OptimisticReviewDecision.tsx` (capability inference, duplicate capability, modernization candidate — one shared component, since all three share the exact CONFIRM/REJECT/rationale/expected_version shape), `apps/web/components/reviews/ModernizationRecommendationDecision.tsx` (the 3-way ACCEPT/REJECT/DISMISS), all wired into `/reviews`. The fixture review-queue data (`packages/shared/src/api/client.ts`) previously seeded zero items of the three dormant CONFIRM/REJECT types, so they were never exercisable even in fixture mode — added one fixture item per type so the flow is demoable and was verified end-to-end in the browser (Confirm → "Capability inference confirmed · v2").

**Original gap:** the review-queue ("findings") has six types. Two — identity assertion, application similarity — have working Confirm/Reject UI. The other four have a finished backend endpoint *and* a finished client SDK method, and are never called from any component:

| Finding type | Backend | Client method | UI |
|---|---|---|---|
| Capability inference | `POST /capability-inferences/{id}/review` | `client.ts:1022` | none |
| Duplicate capability candidate | `POST /duplicate-capability-candidates/{id}/review` | `client.ts:1026` | none |
| Modernization candidate | `POST /modernization-candidates/{id}/review` | `client.ts:1034` | none |
| Modernization recommendation | `POST /modernization-recommendations/{id}/review` | `client.ts:1038` | none |

Today these render as a plain text row in `/reviews` with a "go to repository" link and no decision control — a business user sees the finding but the app gives them no way to act on it.

**Proposal:** extend the existing `UncertainBridge`/`SimilarityDecision` pattern to these four types:
- Capability inference & duplicate capability candidate: 2-way `CONFIRM | REJECT`, same shape as identity assertion review.
- Modernization candidate: 2-way `CONFIRM | REJECT`.
- Modernization recommendation: 3-way `ACCEPT | REJECT | DISMISS` — this is the one that should also drive recommendation `status` (`PROPOSED → ACCEPTED/REJECTED/DISMISSED`), and `ACCEPT` is the natural moment to surface the export action from §2.1 ("Accepted — export for implementation").

This is the single highest-leverage item in this doc: no backend work needed, just UI.

### 2.3 Close the loop: did the recommendation actually work? — ✅ implemented

**Shipped:** `apps/web/components/reviews/ValidationOutcome.tsx`, shown on `RecommendationFocus.tsx` only once the recommendation is `ACCEPTED` (tracked via an `onResolved` callback from the Decision control so it appears immediately after accepting, without a page reload — the parent's initial fetch wouldn't otherwise know about a decision made after load). SUCCEEDED / PARTIAL / FAILED with required notes, via the existing `recordModernizationValidationOutcome` endpoint.

**Original gap:** `POST /modernization-recommendations/{id}/validation-outcomes` (`SUCCEEDED | PARTIAL | FAILED`) exists on the backend and in the client SDK, entirely unused.

**Proposal:** once a recommendation is `ACCEPTED` (§2.2) and presumably implemented, let the owner mark the outcome — a simple 3-state control on `RecommendationFocus.tsx`. This is what turns Modernization from a one-shot list into a feedback loop that can eventually inform recommendation quality/confidence. Lower priority than 2.1/2.2, but cheap once those exist.

### 2.4 Edit application and repository details — ✅ implemented

**Shipped, full stack:**
- **Contract:** `EntityDescriptionUpdateRequest` (new schema, `apps/api/app/models.py`) plus `PUT /applications/{id}` (`updateApplication`) and `PUT /repositories/{id}` (`updateRepository`), both returning `EntitySummary` — no change to the frozen `EntitySummary` shape itself, since it already carried a writable-in-spirit `summary` field that nothing ever wrote to. `stackgraph-foundation/contracts/v1/openapi.json` was regenerated from the live FastAPI app via `scripts/export_openapi.py` (not hand-edited) and `packages/shared/src/contracts/openapi.generated.ts` regenerated via `pnpm contracts:generate`; `pnpm contracts:check` and `node stackgraph-foundation/scripts/validate-contracts.mjs` both confirm the two stay in sync.
- **Storage:** no migration needed. `entity.properties` is already a flexible JSONB column; the new `curated_description` key inside it is checked *first* in `_entity()`'s summary resolution (`apps/api/app/read_models.py`), ahead of the discovered `purpose`/`definition`/`catalog_metadata.description` fallbacks — so a human correction always wins over the next rescan, without ever touching what discovery wrote. Deliberately does **not** touch `entity.updated_at`, since that feeds the freshness indicator (`FRESH`/`STALE`) elsewhere, which should reflect scan recency, not annotation recency.
- **Access:** gated at the `execute` capability (same tier as Business Map writes), not `admin` — this is a curation action, not tenant configuration.
- **UI:** `apps/web/components/entity/DescriptionEditor.tsx`, a shared inline editor (click to edit, textarea, Save/Cancel) used on both the Application detail header and the Repository detail header. On the repository page it sits clearly separate from "What this repository does" (the evidence-backed, citation-linked, read-only declared-intent section) so the discovered vs. human-curated distinction stays visible, not just enforced server-side.
- **Tests:** `apps/api/tests/test_api.py` covers both routes (success + a 403 capability-gating case, matching the existing Business Map test pattern) — 161 backend tests pass. Frontend verified in the browser end-to-end (add → save → displays → edit again) for both applications and repositories.
- Owner/team metadata (mentioned in the original proposal below) was **not** added — no such concept exists anywhere in the contract yet for applications/repositories, and inventing one (a free-text field? a link to a business-map assignment?) is a product decision, not implied by "let a human fix the description." Scoped to description only, per this doc's own "scope modestly" guidance.

**Original gap:** `GET /applications/{id}` and `GET /repositories/{id}` exist; there is no `PUT`/`PATCH` counterpart, and no edit form in `apps/web/app/applications` or `apps/web/app/repositories`. Unlike §2.2, this needs backend work too — `entitySummary` is `additionalProperties: false` in the contract today, so a writable description needs a contract change, not just a route.

**Proposal:**
- Add an editable **description** field to `entitySummary` (contract change) plus owner/team metadata if not already present elsewhere.
- `PUT /applications/{id}` / `PUT /repositories/{id}` accepting a small, explicit field set (description, owner, business criticality tag) — not a generic PATCH-anything endpoint. Keep discovered/inferred fields (name, technologies, deployments) read-only; this action is scoped to the human-curated fields only, so it can't silently overwrite discovery output.
- UI: inline edit affordance on the application/repository detail header, same interaction weight as a form field, not a full page.
- Scope this modestly at first (description + owner) rather than turning the whole entity editable — most of the value here is "let the human correct/annotate the record," not "let the human override what was discovered."

### 2.5 Members & Roles — replace the mock with the real, already-built flow — ✅ implemented

**Shipped:** `apps/web/components/admin/MembersSection.tsx` rewritten against `listMembers`/`inviteMember`/`updateMember`/`removeMember` — invite form (email + optional name + role), per-row role select, Suspend/Reactivate, and Remove with an inline confirm step. `actor_key` (the field the backend uses as the member's unique identity) defaults to the invited email, since there's no SSO subject to key off yet. Verified end-to-end in the browser: invited a member, changed a role, removed a member. The "Configure SSO / OIDC" button was left as-is — it wasn't part of this gap and SSO configuration is a separate, larger piece of work.

**Original gap:** not one of the user's three examples, but the same shape of problem and arguably the biggest single gap found. `MembersSection.tsx` renders a **hardcoded fake array** (including a literal fake row for the current user) — no query, no mutation, no `stackGraphClient` import at all. The "Configure SSO" button has no handler. Meanwhile `POST/PUT/DELETE /admin/members` and `listMembers/inviteMember/updateMember/removeMember` are fully built and unused.

**Proposal:** wire the existing section to the existing client methods — invite by email + role, change a member's role, remove a member. This is pure UI work, zero backend, and it's currently shipping a fake screen to admins.

### 2.6 Deterministic findings — explicitly out of scope

The rule-derived findings panel (`DeterministicInsightsPanel.tsx`) is read-only *by design* ("AI may explain these results, but it does not decide whether a finding exists"). Recommend leaving it that way rather than bolting a status/dismiss action onto it — if a business user wants to act on a deterministic finding, the action belongs on the modernization recommendation or capability inference it feeds into (§2.2), not on the raw rule output. Flagging this so it isn't mistaken for a gap.

---

## 3. Suggested priority order

1. **✅ §2.2 Wire the four dormant review actions** — no backend work, directly closes the "changing status on observations" gap the user asked about, and is the prerequisite for 2.1's "export what I accepted" framing.
2. **✅ §2.1 Export recommendation to Markdown** — small, self-contained, high perceived value (this is the artifact a business user hands to an engineering team).
3. **✅ §2.5 Members & Roles real wiring** — no backend work, currently showing fake data to admins.
4. **✅ §2.4 Application/repository description edit** — the only item needing a contract change + new backend endpoints; done last, scoped to description only (no owner field — nothing to hang it on yet).
5. **✅ §2.3 Validation outcome feedback loop** — done alongside 2.1/2.2 since it was cheap once they existed.

## 4. Explicitly not proposed here

- **MCP server management** — already shipped (`b08d7e6`, "Manage the MCP server from Admin -> Services & health"). It's registered as a `CORE` service (`service_key='mcp'`) in the admin read model and controlled through the existing generic `ServicesSection` stop/start + heartbeat UI, same as any other service — no dedicated MCP screen because none is needed. (An earlier draft of this doc listed this as a gap; it isn't — the code is data-driven off the services list, which is why a literal text search for "mcp" in the frontend found nothing.)
- Making discovered/inferred fields (technologies, deployments, detected repos) editable — those should stay derived-from-evidence; editability is scoped to human-curated annotation fields only (§2.4).
