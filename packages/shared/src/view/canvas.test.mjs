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
