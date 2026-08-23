// Adapter conformance: the wire fixtures are generated from the server's own catalog,
// so if the adapter can round-trip them the renderer is bound to shapes the API
// actually publishes. This is the check that the first version of this feature did
// not have, and the reason it bound to shapes that never existed.
import assert from "node:assert/strict";
import { test } from "node:test";
import { readFileSync } from "node:fs";

const read = (name) =>
  JSON.parse(readFileSync(new URL(`../fixtures/${name}`, import.meta.url), "utf8"));

const catalog = JSON.parse(
  readFileSync(new URL("../../../../apps/api/app/architecture/stackgraph-reference-v1.json", import.meta.url), "utf8"),
);

test("fixtures use the server catalog's cell keys, not a parallel set", () => {
  const canonical = new Set(catalog.reference_model.cells.map((cell) => cell.key));
  for (const name of ["canvas-projection-estate.json", "canvas-projection-application.json", "canvas-projection-target.json"]) {
    const projection = read(name);
    assert.equal(projection.cells.length, canonical.size, `${name} cell count`);
    for (const cell of projection.cells) {
      assert.ok(canonical.has(cell.cell_key), `${name} has unknown cell ${cell.cell_key}`);
    }
  }
});

test("every concern the template lays out resolves to a domain", () => {
  const concernDomain = new Map(catalog.taxonomy.concerns.map((c) => [c.key, c.domain_key]));
  for (const cell of catalog.reference_model.cells) {
    assert.ok(concernDomain.get(cell.concern_key), `cell ${cell.key} has an unmapped concern`);
  }
});

test("projection summary counts agree with the cells they summarise", () => {
  const projection = read("canvas-projection-estate.json");
  const count = (state) => projection.cells.filter((cell) => cell.state === state).length;
  const s = projection.summary;
  assert.equal(s.populated_cells, count("POPULATED"));
  assert.equal(s.empty_cells, count("EMPTY"));
  assert.equal(s.unobserved_cells, count("UNOBSERVED"));
  assert.equal(s.not_applicable_cells, count("NOT_APPLICABLE"));
  assert.equal(s.unbound_cells, count("UNBOUND"));
  assert.equal(
    s.populated_cells + s.empty_cells + s.unobserved_cells + s.not_applicable_cells + s.unbound_cells,
    projection.cells.length,
  );
});

test("EMPTY is never asserted for a cell whose absence cannot be asserted", () => {
  const assertable = new Map(catalog.reference_model.cells.map((c) => [c.key, c.absence_assertable ?? false]));
  const projection = read("canvas-projection-estate.json");
  for (const cell of projection.cells) {
    if (cell.state === "EMPTY") {
      assert.ok(assertable.get(cell.cell_key), `${cell.cell_key} asserts EMPTY but absence is not assertable`);
    }
  }
});

test("every populated occupant carries a citation", () => {
  const projection = read("canvas-projection-estate.json");
  for (const cell of projection.cells) {
    if (cell.state !== "POPULATED") continue;
    for (const occupant of cell.occupants) {
      assert.ok((occupant.citations ?? []).length > 0, `${cell.cell_key}/${occupant.technology.name} has no citation`);
    }
  }
});

test("occupants use the wire's flat adoption fields", () => {
  const projection = read("canvas-projection-estate.json");
  const occupant = projection.cells.flatMap((cell) => cell.occupants)[0];
  assert.equal(typeof occupant.adoption_applications, "number");
  assert.equal(occupant.adoption, undefined, "nested adoption is the view model's shape, not the wire's");
});

test("measures are flat on the wire, not nested under components", () => {
  const projection = read("canvas-projection-estate.json");
  const measures = projection.cells.find((cell) => cell.measures)?.measures;
  assert.ok(measures.coverage, "coverage sits at the top level");
  assert.equal(measures.components, undefined);
});

test("the tray is item-based and its counts match its items", () => {
  const tray = read("canvas-projection-estate.json").classification_tray;
  const count = (reason) => tray.items.filter((item) => item.reason === reason).length;
  assert.equal(tray.unclassified_count, count("UNCLASSIFIED"));
  assert.equal(tray.ambiguous_count, count("AMBIGUOUS"));
  assert.equal(tray.unresolved_policy_count, count("UNRESOLVED_POLICY"));
  assert.equal(tray.filtered_count, count("FILTERED"));
  assert.equal(tray.total_count, tray.items.length);
});

test("comparison cells carry counters and booleans, never a headline verdict", () => {
  const comparison = read("canvas-comparison.json");
  const cell = comparison.cells[0];
  assert.equal(typeof cell.unevaluable, "boolean");
  assert.equal(typeof cell.required_but_absent, "boolean");
  assert.equal(cell.status, undefined, "the verdict is derived in the view layer");
});

test("the profile carries versioned state for optimistic concurrency", () => {
  const profile = read("canvas-architecture-profile.json");
  assert.equal(typeof profile.version, "number");
  assert.ok(profile.state.cell_policies.length > 0);
  assert.equal(profile.state.cell_policies[0].cell_overrides, undefined);
});

// ─── Contract-constraint conformance ─────────────────────────────────────────
// Shape alone is not enough. A payload can carry every expected field and still be
// rejected: `subject_ids: []` on a policy exception typechecked, round-tripped through
// fixture mode, and 422'd against the real API because the contract sets minItems: 1.
// These validate the fixtures against the published schema, bounds included.

import { validate } from "./schema.mjs";

const openapi = JSON.parse(
  readFileSync(new URL("../../../../stackgraph-foundation/contracts/v1/openapi.json", import.meta.url), "utf8"),
);
const against = (schemaName, value) =>
  validate({ $ref: `#/components/schemas/${schemaName}` }, value, openapi);

test("projection fixtures satisfy the published CanvasProjection schema", () => {
  for (const name of [
    "canvas-projection-estate.json",
    "canvas-projection-application.json",
    "canvas-projection-target.json",
  ]) {
    assert.deepEqual(against("CanvasProjection", read(name)), [], name);
  }
});

test("comparison fixture satisfies the published CanvasComparison schema", () => {
  assert.deepEqual(against("CanvasComparison", read("canvas-comparison.json")), []);
});

test("reference model, taxonomy, and template fixtures satisfy their schemas", () => {
  assert.deepEqual(against("ArchitectureReferenceModel", read("canvas-reference-model.json")), []);
  assert.deepEqual(against("ArchitectureTaxonomyResponse", read("canvas-taxonomy.json")), []);
  assert.deepEqual(against("CanvasTemplateModel", read("canvas-template.json")), []);
});

test("the profile fixture satisfies ArchitectureProfileDetail", () => {
  assert.deepEqual(against("ArchitectureProfileDetail", read("canvas-architecture-profile.json")), []);
});

/**
 * The exact round trip the "new draft from active" button performs: read the effective
 * policies off the target projection, then post them as a create body.
 *
 * This is the path that 422'd for a user. Anything the API can *return* but not
 * *accept* breaks it, and there is no type that catches that — the read and the write
 * share a model name but not its constraints. `subject_ids: []` was returnable in
 * fixture mode and rejected on write, because the contract sets minItems: 1.
 */
function cellPoliciesFromTargetProjection(projection) {
  return projection.cells
    .filter((cell) => cell.policy)
    .map((cell) => {
      const policy = cell.policy;
      return {
        cell_key: cell.cell_key,
        applicability: cell.expectation.applicability,
        minimum_implementations: cell.expectation.minimum_implementations ?? null,
        maximum_implementations: cell.expectation.maximum_implementations ?? null,
        allowed_diversity: cell.expectation.allowed_diversity ?? null,
        preferred_technology_ids: policy.preferred_technology_ids ?? [],
        allowed_technology_ids: policy.allowed_technology_ids ?? [],
        discouraged_technology_ids: policy.discouraged_technology_ids ?? [],
        prohibited_technology_ids: policy.prohibited_technology_ids ?? [],
        rationale: policy.rationale ?? "",
        owner: policy.owner ?? null,
        effective_from: policy.effective_from ?? null,
        effective_to: policy.effective_to ?? null,
        scope_selector: policy.scope_selector ?? {},
        exceptions: policy.exceptions ?? [],
      };
    });
}

test("policies read off the target projection can be posted back unchanged", () => {
  const target = read("canvas-projection-target.json");
  const policies = cellPoliciesFromTargetProjection(target);
  assert.ok(policies.length > 0, "the target projection must carry policies to exercise this");

  const body = {
    profile_key: "enterprise.target.v1",
    state: {
      name: "Enterprise architecture standard (draft)",
      reference_model_key: target.reference_model_key,
      reference_model_version: target.reference_model_version,
      cell_policies: policies,
      extension_cells: [],
    },
  };
  assert.deepEqual(against("ArchitectureProfileCreateRequest", body), []);
});

test("an empty draft — the first-draft case — is also accepted", () => {
  const target = read("canvas-projection-target.json");
  const body = {
    profile_key: "enterprise.target.v1",
    state: {
      name: "Enterprise architecture standard (draft)",
      reference_model_key: target.reference_model_key,
      reference_model_version: target.reference_model_version,
      cell_policies: [],
      extension_cells: [],
    },
  };
  assert.deepEqual(against("ArchitectureProfileCreateRequest", body), []);
});

test("the profile fixture's own policies can be written back", () => {
  const profile = read("canvas-architecture-profile.json");
  const body = {
    profile_key: "enterprise.target.v1",
    state: {
      name: profile.state.name,
      reference_model_key: profile.reference_model_key,
      reference_model_version: profile.reference_model_version,
      cell_policies: profile.state.cell_policies,
      extension_cells: profile.state.extension_cells ?? [],
    },
  };
  assert.deepEqual(against("ArchitectureProfileCreateRequest", body), []);
});
