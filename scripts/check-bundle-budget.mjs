#!/usr/bin/env node
/**
 * Performance budget gate (plan §8.4). Builds the web app and fails if the JavaScript
 * payload regresses past budget. Complements the token-lint and a11y gates.
 *
 * Budgets (First Load JS, gzipped as Next reports):
 *   - shared-by-all chunk: keeps the baseline every route pays lean
 *   - any single route:    catches a heavy surface sneaking in
 *
 * Usage: node scripts/check-bundle-budget.mjs   (run from repo root)
 */
import { execSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";

const SHARED_BUDGET_KB = 130;
const ROUTE_BUDGET_KB = 210;

const repoRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");

console.log("Building web app for budget check…");
let output;
try {
  output = execSync("pnpm --filter @stackgraph/web build", {
    cwd: repoRoot,
    encoding: "utf8",
    env: { ...process.env, NEXT_PUBLIC_DATA_SOURCE: "fixtures", NEXT_TELEMETRY_DISABLED: "1" },
    stdio: ["ignore", "pipe", "inherit"],
  });
} catch (e) {
  console.error("Build failed; cannot check budget.");
  process.exit(1);
}

const toKb = (s) => {
  const m = s.trim().match(/([\d.]+)\s*(kB|MB|B)/);
  if (!m) return null;
  const n = parseFloat(m[1]);
  return m[2] === "MB" ? n * 1024 : m[2] === "B" ? n / 1024 : n;
};

const lines = output.split("\n");
const failures = [];

// "+ First Load JS shared by all   106 kB"
const sharedLine = lines.find((l) => /First Load JS shared by all/.test(l));
const sharedKb = sharedLine ? toKb(sharedLine.split(/shared by all/)[1] ?? "") : null;
if (sharedKb == null) {
  console.error("Could not parse shared First Load JS from build output.");
  process.exit(1);
}
if (sharedKb > SHARED_BUDGET_KB) failures.push(`shared First Load JS ${sharedKb} kB > ${SHARED_BUDGET_KB} kB`);

// Route rows: "├ ○ /estate   1.4 kB   118 kB" — last kB column is First Load JS.
let maxRoute = { route: "", kb: 0 };
for (const l of lines) {
  const m = l.match(/^[├└]\s+[○ƒλ●]\s+(\/\S*)\s+.*?([\d.]+\s*(?:kB|MB|B))\s*$/);
  if (!m) continue;
  const kb = toKb(m[2]);
  if (kb == null) continue;
  if (kb > maxRoute.kb) maxRoute = { route: m[1], kb };
  if (kb > ROUTE_BUDGET_KB) failures.push(`route ${m[1]} First Load JS ${kb} kB > ${ROUTE_BUDGET_KB} kB`);
}

console.log(`\nBundle budget:`);
console.log(`  shared First Load JS: ${sharedKb} kB (budget ${SHARED_BUDGET_KB} kB)`);
console.log(`  heaviest route: ${maxRoute.route} ${maxRoute.kb} kB (budget ${ROUTE_BUDGET_KB} kB)`);

if (failures.length) {
  console.error(`\n✖ Bundle budget exceeded:`);
  for (const f of failures) console.error(`  - ${f}`);
  process.exit(1);
}
console.log(`\n✓ Bundle within budget.`);
