# Architecture Canvas — API gaps found during UI integration

Status: findings · Date: 2026-08-23 · Author: canvas frontend

The canvas UI now binds to the published contracts
(`stackgraph-foundation/contracts/v1/openapi.json`) rather than to the shapes the spec
described. Most differences were ergonomic and are absorbed by the adapter in
[view/canvas.ts](../packages/shared/src/view/canvas.ts).

The items below are not ergonomic. Each one costs the product a behaviour the spec
asks for, and none can be fixed from the client without inventing data. They are
ordered by what they block.

---

## 1. A draft profile cannot be previewed — blocks govern mode

`GET /canvas/target-projection` takes `reference_model_key` and `template_key` only. It
always resolves the revision in force.

Governance edits are made against a **draft** (`PUT /admin/architecture-profiles/{id}`
updates a draft, spec §10.2). So while governing, the canvas shows the active
revision's target while the user edits a different one. Every edit appears to do
nothing.

The UI currently states this plainly in a banner rather than implying the target has
moved, which is honest but not what §7.2 describes — golden mode is supposed to render
the target being edited.

**Ask:** a `profile_id` (or `profile_version`) query parameter on
`/canvas/target-projection`, resolving that revision instead of the active one.

## 2. A profile's state cannot be read back — blocks safe editing after reload

`GET /admin/architecture-profiles` returns `ArchitectureProfileSummary`, which has no
`state`. There is no `GET /admin/architecture-profiles/{id}`. Full state is returned
only by create and update.

`PUT` takes a **whole** `ArchitectureProfileStateModel`. So after a page reload the
client holds no authoritative copy of a draft's `cell_policies`, and any write it
composed would silently drop every policy it had not seen.

The UI refuses to write in that situation and says why. That is safe, but it means
governance does not survive a refresh.

**Ask:** `GET /admin/architecture-profiles/{id}` returning `ArchitectureProfileDetail`.
A `PATCH` for a single cell policy would remove the whole-state hazard entirely and is
the better fix if it is on the table.

## 3. Tenant policy carries identifiers without names

`CanvasCellProjectionModel.policy` is a `TenantCellPolicyModel`: four arrays of
technology ids. Names are only resolvable for technologies that also appear as
occupants somewhere in the projection.

A technology that is **prohibited and therefore not in use** is exactly the case that
cannot be resolved — and exactly the one a reviewer most needs to read. The UI renders
`Unnamed technology · a75bc08b` in a muted style with a count and an explanation,
rather than a bare UUID pretending to be a name.

**Ask:** either an `EntitySummary` alongside each decision, or a
`referenced_technologies: EntitySummary[]` block on the projection covering every id
its policies mention.

## 4. Comparison cannot show what changed between two actuals

`CanvasCellComparisonModel` carries counters plus `actual_state` / `baseline_state`. For
`ACTUAL_TO_TARGET` that is sufficient. For `ACTUAL_TO_ACTUAL` it is not: there is no
added/removed technology set, so comparing two applications can say *that* a cell
differs but never *how*.

**Ask:** `added_technologies` / `removed_technologies` (`EntitySummary[]`) on the cell
comparison, populated for `ACTUAL_TO_ACTUAL`.

## 5. Effective expectations carry no provenance

`CellExpectationModel` is four numbers. Spec §7.1 says effective policy is
"deterministic and explainable", and the cell panel wants to say whether an expectation
came from the reference model or the tenant profile, under whose ownership, and from
when.

The UI infers the source: a cell with a `policy` is treated as tenant-governed and
borrows that policy's rationale, owner, and dates. That is right in every case the
fixtures cover, but it is an inference, and it will be wrong for a tenant profile that
sets an expectation without any technology decisions.

**Ask:** `source`, `rationale`, `owner`, `effective_from`, `effective_to` on the
effective expectation, or a documented guarantee that expectation and policy always
travel together.

## 6. Smaller items

- **Observation loses per-sensor detail.** `CellObservationStatusModel` reports
  `required_sensor_kinds` and `supported_sensor_kinds` as flat lists with one overall
  `status`. There is no per-sensor last-observed time and no `unsupported_ecosystems`,
  so the panel can say a cell is `PARTIAL` but not which sensor is behind, or which
  ecosystem is unanalyzable. `fresh_subjects` is a good addition and is rendered.
- **`TIME_TO_TIME` is accepted by the request type and rejected at validation.**
  `CanvasComparisonRequest.comparison_kind` includes it; the server raises. The
  generated client type therefore permits a call that always fails. Narrowing the
  request enum to the two implemented kinds would make that unrepresentable.
- **Cells carry no icon key, correctly.** Presentation does not cross the API boundary
  (§5.2), so the UI derives icons from `concern_key`. Noted only because it means
  concern keys are now a presentation-affecting contract: renaming one silently changes
  a glyph. The UI falls back to a neutral icon rather than breaking.

---

## Not gaps

Recorded so they are not re-raised:

- Flat summary counters, flat occupant adoption, flat measures, and the item-based
  classification tray are all fine. The adapter reshapes them once, and the flat wire
  form is cheaper to produce and to validate.
- Version-based optimistic concurrency is better than the fingerprint scheme the spec
  sketched: it is human-readable in the Admin table and orders naturally.
- `absence_assertable` on the cell definition is a genuinely good addition that the
  spec only implied. The UI now enforces it in its own fixtures: a cell that cannot
  assert absence is never rendered `EMPTY`.
- `EXEMPTED` as an occupant policy status is a real distinction worth having, and is
  rendered separately from `ALLOWED`.
