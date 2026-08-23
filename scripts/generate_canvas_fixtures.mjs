// Generates the fixture-mode Architecture Canvas payloads in
// packages/shared/src/fixtures/.
//
// The reference model, taxonomy, and layout are read from the SERVER's canonical
// catalog (apps/api/app/architecture/stackgraph-reference-v1.json) rather than being
// restated here. Fixture mode is only useful if it is a faithful stand-in for the
// API: an invented parallel catalog is how fixture-only bugs get shipped, and how the
// first version of this file drifted out of alignment with the real contract.
//
// Only the observed data — occupants, states, measures, tray — is authored, and it is
// shaped to exercise every branch the renderer has to handle.
//
// Run: node scripts/generate_canvas_fixtures.mjs
import fs from "node:fs";
import path from "node:path";
import crypto from "node:crypto";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const out = path.join(root, "packages/shared/src/fixtures");
const catalog = JSON.parse(
  fs.readFileSync(path.join(root, "apps/api/app/architecture/stackgraph-reference-v1.json"), "utf8"),
);

const { taxonomy, reference_model: referenceModel, template } = catalog;
const AS_OF = "2026-08-23T09:00:00.000Z";
const METHOD = "architecture-canvas/v1";

const canonical = (value) => JSON.stringify(value, Object.keys(value).sort?.() ?? null);
const sha = (seed) => `sha256:${crypto.createHash("sha256").update(seed).digest("hex")}`;
let counter = 0;
const uuid = (seed) => {
  const digest = crypto.createHash("sha256").update(`${seed}:${counter++}`).digest("hex");
  return [digest.slice(0, 8), digest.slice(8, 12), `4${digest.slice(13, 16)}`,
    `8${digest.slice(17, 20)}`, digest.slice(20, 32)].join("-");
};
const cite = (label, seed) => ({ fact_id: uuid(`fact:${seed}`), label });

const contentHash = (value) => sha(JSON.stringify(value));
const TAXONOMY_HASH = contentHash(taxonomy);
const MODEL_HASH = contentHash(referenceModel);
const TEMPLATE_HASH = contentHash(template);

const cellsByKey = new Map(referenceModel.cells.map((cell) => [cell.key, cell]));
const concernDomain = new Map(taxonomy.concerns.map((c) => [c.key, c.domain_key]));
const domainOf = (cell) => concernDomain.get(cell.concern_key);

// ─── Technologies ────────────────────────────────────────────────────────────

const TECH = new Map();
function tech(name) {
  if (!TECH.has(name)) {
    TECH.set(name, {
      id: uuid(`tech:${name}`),
      kind: "Technology",
      name,
      canonical_key: `stackgraph:technology:${name.toLowerCase().replace(/[^a-z0-9]+/g, "-")}`,
    });
  }
  return TECH.get(name);
}

// [cellKey, technology, placementKeys, classification, confidence, apps, repos, deployments, policyStatus]
const PLACEMENTS = [
  ["cell.experience.ui", "React", ["ui-rendering"], "CURATED", 0.97, 9, 14, 11, "PREFERRED"],
  ["cell.experience.ui", "Vue", ["ui-rendering"], "CATALOG_MATCH", 0.71, 1, 1, 1, "DISCOURAGED"],
  ["cell.experience.web", "Next.js", ["meta-framework"], "CURATED", 0.95, 7, 9, 8, "PREFERRED"],
  ["cell.experience.state", "TanStack Query", ["server-state"], "CURATED", 0.9, 6, 8, 7, "ALLOWED"],
  ["cell.experience.state", "Zustand", ["client-state"], "CURATED", 0.88, 5, 6, 5, "PREFERRED"],
  ["cell.experience.state", "Redux", ["client-state"], "CATALOG_MATCH", 0.66, 2, 2, 2, "DISCOURAGED"],
  ["cell.experience.state", "MobX", ["client-state"], "CATALOG_MATCH", 0.58, 1, 1, 0, "PROHIBITED"],
  ["cell.experience.input", "Zod", ["runtime-validation"], "CURATED", 0.91, 6, 8, 6, "PREFERRED"],
  ["cell.experience.design", "Tailwind CSS", ["css-styling"], "CURATED", 0.86, 4, 5, 4, "ALLOWED"],
  ["cell.experience.design", "Radix UI", ["accessible-ui"], "CURATED", 0.83, 3, 4, 3, "EXEMPTED"],

  ["cell.application.service", "FastAPI", ["http-web-api"], "CURATED", 0.96, 8, 11, 10, "PREFERRED"],
  ["cell.application.service", "Express", ["http-web-api"], "CATALOG_MATCH", 0.74, 3, 4, 3, "ALLOWED"],
  ["cell.application.service", "Flask", ["http-web-api"], "CATALOG_MATCH", 0.69, 2, 2, 1, "DISCOURAGED"],
  ["cell.application.persistence", "SQLAlchemy", ["orm-data-access"], "CURATED", 0.94, 7, 9, 8, "PREFERRED"],
  ["cell.application.persistence", "Prisma", ["orm-data-access"], "CURATED", 0.81, 2, 3, 2, "ALLOWED"],
  ["cell.application.persistence", "Drizzle", ["orm-data-access"], "CATALOG_MATCH", 0.62, 1, 1, 1, "UNGOVERNED"],
  ["cell.application.outbound", "httpx", ["http-client"], "CURATED", 0.89, 6, 8, 7, "ALLOWED"],
  ["cell.application.outbound", "requests", ["http-client"], "CATALOG_MATCH", 0.77, 5, 7, 4, "DISCOURAGED"],
  ["cell.application.background", "Celery", ["background-jobs"], "CURATED", 0.85, 4, 5, 4, "ALLOWED"],
  ["cell.application.runtime", "Python 3.12", ["language-runtime"], "CURATED", 0.98, 9, 12, 11, "PREFERRED"],
  ["cell.application.runtime", "Node.js 22", ["language-runtime"], "CURATED", 0.97, 8, 10, 9, "PREFERRED"],

  ["cell.integration.edge", "NGINX", ["reverse-proxy"], "CURATED", 0.93, 8, 3, 9, "ALLOWED"],
  ["cell.integration.edge", "Kong", ["api-gateway"], "CATALOG_MATCH", 0.7, 2, 1, 2, "UNGOVERNED"],
  ["cell.integration.contract", "OpenAPI", ["api-contract"], "CURATED", 0.95, 9, 12, 0, "PREFERRED"],
  ["cell.integration.messaging", "Redis", ["task-queue"], "DETERMINISTIC", 1, 5, 6, 5, "ALLOWED"],
  ["cell.integration.messaging", "RabbitMQ", ["message-broker"], "CATALOG_MATCH", 0.72, 2, 2, 2, "DISCOURAGED"],
  ["cell.integration.events", "Apache Kafka", ["durable-event-stream"], "CURATED", 0.88, 3, 3, 3, "PREFERRED"],
  ["cell.integration.identity-access", "Keycloak", ["identity-provider"], "CATALOG_MATCH", 0.76, 4, 2, 4, "ALLOWED"],

  ["cell.data.database", "PostgreSQL", ["relational-database"], "DETERMINISTIC", 1, 9, 11, 10, "PREFERRED"],
  ["cell.data.database", "MySQL", ["relational-database"], "DETERMINISTIC", 1, 2, 2, 2, "DISCOURAGED"],
  ["cell.data.cache-session", "Redis", ["cache"], "DETERMINISTIC", 1, 7, 8, 7, "PREFERRED"],
  ["cell.data.object-storage", "Amazon S3", ["object-storage"], "DETERMINISTIC", 1, 6, 5, 6, "PREFERRED"],
  ["cell.data.search", "OpenSearch", ["full-text-search"], "CATALOG_MATCH", 0.68, 2, 2, 2, "UNGOVERNED"],

  ["cell.platform.runtime", "Python 3.12", ["language-runtime"], "CURATED", 0.98, 9, 12, 11, "PREFERRED"],
  ["cell.platform.runtime", "Go 1.22", ["language-runtime"], "CATALOG_MATCH", 0.79, 2, 2, 2, "ALLOWED"],
  ["cell.platform.artifact", "Docker", ["container-runtime"], "CURATED", 0.96, 9, 12, 11, "PREFERRED"],
  ["cell.platform.orchestration", "Kubernetes", ["kubernetes"], "CURATED", 0.94, 8, 4, 10, "PREFERRED"],
  ["cell.platform.network", "NGINX Ingress", ["ingress-controller"], "CATALOG_MATCH", 0.8, 6, 2, 8, "ALLOWED"],
  ["cell.platform.provider", "Amazon RDS", ["cloud-platform-service"], "DETERMINISTIC", 1, 7, 0, 8, "PREFERRED"],

  ["cell.delivery.build", "pnpm", ["package-management"], "CURATED", 0.9, 6, 8, 0, "PREFERRED"],
  ["cell.delivery.build", "uv", ["package-management"], "CURATED", 0.87, 5, 7, 0, "PREFERRED"],
  ["cell.delivery.test", "Playwright", ["e2e-testing"], "CURATED", 0.89, 5, 6, 0, "PREFERRED"],
  ["cell.delivery.test", "pytest", ["unit-testing"], "CURATED", 0.93, 7, 9, 0, "PREFERRED"],
  ["cell.delivery.test", "Jest", ["unit-testing"], "CATALOG_MATCH", 0.6, 2, 2, 0, "DISCOURAGED"],
  ["cell.delivery.observability", "OpenTelemetry", ["telemetry"], "CURATED", 0.86, 6, 7, 7, "PREFERRED"],
  ["cell.delivery.observability", "Prometheus", ["telemetry"], "CATALOG_MATCH", 0.78, 5, 1, 6, "ALLOWED"],
];

for (const [key] of PLACEMENTS) {
  if (!cellsByKey.has(key)) throw new Error(`Placement references unknown cell: ${key}`);
}

// Cells deliberately held in a non-populated state so every treatment is exercised.
// `absence_assertable: false` cells can only ever be UNOBSERVED (spec §4.8).
const STATE_OVERRIDES = {
  "cell.experience.channels": ["NOT_APPLICABLE", "The active profile marks non-browser channels not applicable for this scope.", "NOT_APPLICABLE"],
  "cell.application.logic": ["UNOBSERVED", "Domain logic is not attributable from dependency evidence alone; no code-context scan has completed for 6 of 12 repositories.", "PARTIAL"],
  "cell.application.workflow": ["EMPTY", "All 12 in-scope repositories were observed and no durable-workflow capability was found.", "COMPLETE"],
  "cell.integration.connectivity": ["EMPTY", "All 12 repositories and 11 deployments were observed; no service-mesh or discovery capability was found.", "COMPLETE"],
  "cell.integration.stream-processing": ["UNOBSERVED", "Stream-processing detection requires runtime evidence; no runtime sensor has reported for this scope.", "MISSING"],
  "cell.integration.orchestration": ["UNOBSERVED", "Orchestration detection is unsupported for the CARGO and MAVEN ecosystems present in this scope.", "MISSING"],
  "cell.data.analytics": ["UNOBSERVED", "Warehouse and lake observation depends on a cloud-inventory connector that is not configured.", "MISSING"],
  "cell.data.processing": ["UNOBSERVED", "Batch and streaming processing evidence is stale: the last successful observation is 41 days old.", "PARTIAL"],
  "cell.data.movement": ["UNBOUND", "Change-data-capture and pipeline schedules are not part of any supported sensor.", "MISSING"],
  "cell.platform.compute": ["UNOBSERVED", "Compute-target evidence covers 4 of 11 deployments; the remainder have no infrastructure sensor.", "PARTIAL"],
  "cell.platform.serverless": ["EMPTY", "All 11 deployments were observed; no serverless or provider-managed execution was found.", "COMPLETE"],
  "cell.delivery.cicd": ["UNOBSERVED", "CI/CD workflow parsing is not yet a supported sensor kind for this scope.", "MISSING"],
  "cell.delivery.iac": ["UNOBSERVED", "Infrastructure-as-code detection needs repository file-tree evidence, missing for 9 of 12 repositories.", "PARTIAL"],
  "cell.delivery.configuration": ["UNOBSERVED", "Secret-delivery observation is unsupported without a platform-configuration connector.", "MISSING"],
  "cell.delivery.release": ["EMPTY", "Deployment evidence covered all 11 deployments; no release-management capability was observed.", "COMPLETE"],
  "cell.delivery.reliability": ["UNBOUND", "StackGraph does not yet ingest incident-management or alerting configuration.", "MISSING"],
};

// ─── Tenant policy ───────────────────────────────────────────────────────────

const POLICY = {
  "cell.experience.ui": ["React is the single approved rendering library; Vue entered through an acquired codebase.", "platform-architecture", "REQUIRED", 1, 2, 2],
  "cell.experience.state": ["Zustand for client state, TanStack Query for server state. Redux is retiring; MobX is prohibited.", "frontend-guild", "RECOMMENDED", 1, 3, 3],
  "cell.experience.design": ["Radix carries a documented exception until the in-house primitives land.", "design-systems", "RECOMMENDED", 1, 2, 2],
  "cell.application.service": ["FastAPI is the standard service framework. Express is allowed for edge workers only.", "platform-architecture", "REQUIRED", 1, 2, 2],
  "cell.data.database": ["PostgreSQL is the standard relational engine across all environments.", "data-platform", "REQUIRED", 1, 2, 2],
  "cell.integration.edge": ["NGINX terminates edge traffic. Kong was introduced without review.", "platform-architecture", "REQUIRED", 1, 2, 2],
  "cell.delivery.observability": ["OpenTelemetry is the standard instrumentation layer; Prometheus remains allowed for infrastructure metrics.", "observability-guild", "REQUIRED", 1, 3, 3],
};

// A governed technology that is nowhere in use: it exercises the id-resolution path,
// because the projection carries no occupant to borrow a name from.
const RETIRED_TECHNOLOGY = tech("Splunk");

function cellPolicy(cellKey, occupants) {
  const entry = POLICY[cellKey];
  if (!entry) return null;
  const [rationale, owner, applicability, min, max, diversity] = entry;
  const ids = (status) =>
    occupants.filter((o) => o.policy_status === status).map((o) => o.technology.id);
  const prohibited = ids("PROHIBITED");
  if (cellKey === "cell.delivery.observability") prohibited.push(RETIRED_TECHNOLOGY.id);
  return {
    cell_key: cellKey,
    applicability,
    minimum_implementations: min,
    maximum_implementations: max,
    allowed_diversity: diversity,
    preferred_technology_ids: ids("PREFERRED"),
    allowed_technology_ids: ids("ALLOWED"),
    discouraged_technology_ids: ids("DISCOURAGED"),
    prohibited_technology_ids: prohibited,
    rationale,
    owner,
    effective_from: "2026-01-01T00:00:00.000Z",
    effective_to: null,
    scope_selector: {},
    exceptions: cellKey === "cell.experience.design"
      ? [{
          key: "radix-until-inhouse",
          rationale: "Radix UI stays until the in-house primitives ship.",
          subject_ids: [],
          effective_from: "2026-04-01T00:00:00.000Z",
          effective_to: "2026-12-31T00:00:00.000Z",
        }]
      : [],
  };
}

// ─── Cells ───────────────────────────────────────────────────────────────────

function observation(cell, status, scale) {
  const inScope = Math.max(1, Math.round(12 * scale));
  const observed = status === "COMPLETE" ? inScope
    : status === "PARTIAL" ? Math.max(1, Math.round(inScope * 0.5))
    : status === "NOT_APPLICABLE" ? inScope : 0;
  return {
    status,
    required_sensor_kinds: cell.required_sensor_kinds ?? [],
    supported_sensor_kinds: status === "MISSING" ? [] : cell.required_sensor_kinds ?? [],
    in_scope_subjects: inScope,
    observed_subjects: observed,
    fresh_subjects: status === "PARTIAL" ? Math.max(0, observed - 2) : observed,
    missing_inputs:
      status === "COMPLETE" || status === "NOT_APPLICABLE" ? []
        : status === "PARTIAL" ? [`${inScope - observed} of ${inScope} subjects unobserved`]
        : ["no supported sensor has reported for this cell"],
    method_version: METHOD,
    input_fingerprint: sha(`observation:${cell.key}:${status}:${scale}`),
  };
}

const measure = (value, status, inputs, facts = []) => ({
  value, status, inputs, supporting_fact_ids: facts, method_version: METHOD,
});

function measures(cell, occupants) {
  if (!occupants.length) return null;
  const unique = new Set(occupants.map((o) => o.technology.id)).size;
  const max = cell.default_expectation?.maximum_implementations;
  const prohibited = occupants.filter((o) => o.policy_status === "PROHIBITED").length;
  const discouraged = occupants.filter((o) => o.policy_status === "DISCOURAGED").length;
  const governed = occupants.some((o) => o.policy_status !== "UNGOVERNED");
  const coverage = measure(1, "ELIGIBLE", ["occupant count", "minimum implementations"], [uuid(`cov:${cell.key}`)]);
  const standardisation = unique <= 1
    ? measure(null, "INSUFFICIENT_DATA", ["adoption population below comparison threshold"])
    : measure(Math.max(0, 1 - (unique - 1) / Math.max(1, max ?? unique)), "ELIGIBLE",
        ["unique technology placements", "allowed diversity"], [uuid(`std:${cell.key}`)]);
  const currency = measure(
    Math.min(1, 0.55 + occupants.filter((o) => o.classification === "CURATED").length * 0.12),
    "ELIGIBLE", ["resolved versions", "deprecation metadata"], [uuid(`cur:${cell.key}`)]);
  const risk = measure(Math.max(0, 1 - (prohibited * 0.4 + discouraged * 0.15)), "ELIGIBLE",
    ["attributed deterministic insights", "advisory matches"], [uuid(`risk:${cell.key}`)]);
  const conformance = governed
    ? measure(Math.max(0, 1 - (prohibited * 0.5 + discouraged * 0.2)), "ELIGIBLE",
        ["effective tenant policy", "resolved placements"], [uuid(`conf:${cell.key}`)])
    : measure(null, "NOT_CONFIGURED", ["no effective target policy for this cell"]);
  const eligible = [coverage, standardisation, currency, risk, conformance]
    .filter((m) => m.status === "ELIGIBLE" && m.value !== null);
  const overall = eligible.length >= 3
    ? Math.round((eligible.reduce((sum, m) => sum + m.value, 0) / eligible.length) * 100)
    : null;
  const band = overall === null ? null
    : overall >= 82 ? "STRONG" : overall >= 64 ? "ADEQUATE" : overall >= 45 ? "WEAK" : "AT_RISK";
  const confidence = Math.min(...occupants.map((o) => o.confidence));
  return {
    posture_band: band,
    overall_score: overall,
    coverage, standardisation, currency, risk, conformance,
    confidence,
    confidence_label: confidence >= 0.85 ? "HIGH" : confidence >= 0.6 ? "MEDIUM" : "LOW",
    method_version: METHOD,
    missing_inputs: [
      ...(standardisation.status === "INSUFFICIENT_DATA" ? ["comparison population for standardisation"] : []),
      ...(conformance.status === "NOT_CONFIGURED" ? ["target policy for this cell"] : []),
    ],
  };
}

function occupantsFor(cellKey, scale) {
  return PLACEMENTS.filter((row) => row[0] === cellKey).map((row) => {
    const [, name, keys, classification, confidence, apps, repos, deployments, status] = row;
    const at = (value) => (scale === 1 ? value : Math.max(value ? 1 : 0, Math.round(value * scale)));
    return {
      technology: tech(name),
      placement_keys: keys,
      classification,
      confidence,
      confidence_label: confidence >= 0.85 ? "HIGH" : confidence >= 0.6 ? "MEDIUM" : "LOW",
      adoption_applications: at(apps),
      adoption_repositories: at(repos),
      adoption_deployments: at(deployments),
      policy_status: status,
      policy_reference: status === "EXEMPTED" ? "radix-until-inhouse" : null,
      citations: [cite(`${name} detected in dependency manifest`, `${name}:${cellKey}`)],
    };
  });
}

function buildCells(scale) {
  return referenceModel.cells.map((cell) => {
    const occupants = occupantsFor(cell.key, scale);
    const override = STATE_OVERRIDES[cell.key];
    // A cell whose absence cannot be safely asserted can only ever be UNOBSERVED —
    // "we looked and found nothing" is a claim the reference model has to license
    // (spec §4.8, §6.2). Enforced here so the fixtures cannot state it either.
    const assertable = cell.absence_assertable ?? false;
    let state = override ? override[0] : occupants.length ? "POPULATED" : "EMPTY";
    let observationStatus = override ? override[2] : "COMPLETE";
    if (state === "EMPTY" && !assertable) {
      state = "UNOBSERVED";
      observationStatus = "MISSING";
    }
    const visible = state === "POPULATED" ? occupants : [];
    const policy = cellPolicy(cell.key, visible);
    return {
      cell_key: cell.key,
      state,
      state_reason:
        override && state === override[0]
          ? override[1]
          : visible.length
            ? `${visible.length} placement${visible.length === 1 ? "" : "s"} with supporting evidence.`
            : state === "EMPTY"
              ? "All in-scope subjects were observed and no implementation was found."
              : "Absence cannot be asserted for this concern, so nothing found is reported as not observed.",
      occupants: visible,
      occupant_total: visible.length,
      unique_technology_total: new Set(visible.map((o) => o.technology.id)).size,
      observation: observation(cell, observationStatus, scale),
      expectation: policy
        ? {
            applicability: policy.applicability,
            minimum_implementations: policy.minimum_implementations,
            maximum_implementations: policy.maximum_implementations,
            allowed_diversity: policy.allowed_diversity,
          }
        : cell.default_expectation,
      measures: state === "POPULATED" ? measures(cell, visible) : null,
      policy,
      insight_refs: visible.some((o) => o.policy_status === "PROHIBITED" || o.policy_status === "DISCOURAGED")
        ? [uuid(`insight:${cell.key}`)]
        : [],
      citations: visible.length ? [cite(`${cell.label} evidence`, `cell:${cell.key}`)] : [],
    };
  });
}

// ─── Tray ────────────────────────────────────────────────────────────────────

const TRAY_ITEMS = [
  ["internal-billing-sdk", "UNCLASSIFIED", "No catalog match and no capability inference above the confidence floor. Ecosystem PYPI."],
  ["acme-telemetry-shim", "UNCLASSIFIED", "Private registry package; no public metadata available. Ecosystem NPM."],
  ["legacy-soap-bridge", "UNCLASSIFIED", "Ecosystem MAVEN is not yet analyzable."],
  ["Redis", "AMBIGUOUS", "Cache and task-queue capabilities are both evidenced; the placements are not mutually exclusive but must not be double-counted."],
  ["NGINX", "AMBIGUOUS", "Reverse-proxy and ingress-controller roles both match the observed configuration."],
  ["Style Dictionary", "UNRESOLVED_POLICY", "Custom governed function 'tenant-design-tokens' has no mapping to a canonical or extension cell."],
  ["Theo", "UNRESOLVED_POLICY", "Custom governed function 'tenant-design-tokens' has no mapping to a canonical or extension cell."],
  ["Crystal Reports", "FILTERED", "Withheld by the active confidence filter."],
];

const tray = {
  items: TRAY_ITEMS.map(([name, reason, detail]) => ({
    entity: tech(name),
    reason,
    detail,
    citations: [cite(`${name} observation`, `tray:${name}`)],
  })),
  unclassified_count: TRAY_ITEMS.filter(([, r]) => r === "UNCLASSIFIED").length,
  ambiguous_count: TRAY_ITEMS.filter(([, r]) => r === "AMBIGUOUS").length,
  unresolved_policy_count: TRAY_ITEMS.filter(([, r]) => r === "UNRESOLVED_POLICY").length,
  filtered_count: TRAY_ITEMS.filter(([, r]) => r === "FILTERED").length,
  total_count: TRAY_ITEMS.length,
  truncated: false,
};

// ─── Projection ──────────────────────────────────────────────────────────────

function summarise(cells) {
  const count = (state) => cells.filter((c) => c.state === state).length;
  const band = (name) => cells.filter((c) => c.measures?.posture_band === name).length;
  const unique = new Set();
  let placements = 0;
  let violations = 0;
  for (const cell of cells) {
    if (cell.occupants.some((o) => o.policy_status === "PROHIBITED")) violations += 1;
    for (const occupant of cell.occupants) {
      unique.add(occupant.technology.id);
      placements += 1;
    }
  }
  return {
    populated_cells: count("POPULATED"),
    empty_cells: count("EMPTY"),
    not_applicable_cells: count("NOT_APPLICABLE"),
    unobserved_cells: count("UNOBSERVED"),
    unbound_cells: count("UNBOUND"),
    strong: band("STRONG"),
    adequate: band("ADEQUATE"),
    weak: band("WEAK"),
    at_risk: band("AT_RISK"),
    governed_cells: cells.filter((c) => c.policy).length,
    cells_with_violations: violations,
    unique_technologies: unique.size,
    technology_cell_placements: placements,
  };
}

function projection(scope, subject, cells) {
  return {
    contract_version: "1.0.0",
    as_of: AS_OF,
    method_version: METHOD,
    taxonomy_key: taxonomy.key,
    taxonomy_version: taxonomy.version,
    taxonomy_content_hash: TAXONOMY_HASH,
    reference_model_key: referenceModel.key,
    reference_model_version: referenceModel.version,
    reference_model_content_hash: MODEL_HASH,
    template_key: template.key,
    template_version: template.version,
    tenant_profile_fingerprint: PROFILE_FINGERPRINT,
    scope,
    subject,
    cells,
    classification_tray: tray,
    summary: summarise(cells),
    input_fingerprint: sha(`projection:${scope}:${subject?.id ?? "tenant"}`),
  };
}

const PROFILE_ID = uuid("profile");
const PROFILE_FINGERPRINT = sha("profile:v3");
const estateCells = buildCells(1);
const applicationSubject = {
  id: "00000000-0000-4000-8000-000000000101",
  kind: "Application",
  name: "Helios Storefront",
  canonical_key: "stackgraph:application:helios-storefront",
};
const applicationCells = buildCells(0.34);

// ─── Target projection ───────────────────────────────────────────────────────

function targetCells() {
  return referenceModel.cells.map((cell) => {
    const base = estateCells.find((c) => c.cell_key === cell.key);
    const policy = base.policy;
    const notApplicable = base.expectation.applicability === "NOT_APPLICABLE";
    const decisions = policy
      ? [
          ...policy.preferred_technology_ids.map((id) => [id, "PREFERRED"]),
          ...policy.allowed_technology_ids.map((id) => [id, "ALLOWED"]),
          ...policy.discouraged_technology_ids.map((id) => [id, "DISCOURAGED"]),
          ...policy.prohibited_technology_ids.map((id) => [id, "PROHIBITED"]),
        ]
      : [];
    const byId = new Map([...TECH.values()].map((entity) => [entity.id, entity]));
    return {
      cell_key: cell.key,
      state: notApplicable ? "NOT_APPLICABLE" : decisions.length ? "POPULATED" : "EMPTY",
      state_reason: notApplicable
        ? "The active profile marks this concern not applicable for this scope."
        : decisions.length
          ? `${decisions.length} governed technology decision${decisions.length === 1 ? "" : "s"}.`
          : "No target decision has been recorded for this concern.",
      occupants: decisions.map(([id, decision]) => ({
        technology: byId.get(id) ?? { id, kind: "Technology", name: id },
        placement_keys: [],
        classification: "CURATED",
        confidence: 1,
        confidence_label: "HIGH",
        adoption_applications: 0,
        adoption_repositories: 0,
        adoption_deployments: 0,
        policy_status: decision,
        policy_reference: null,
        citations: [cite("Tenant architecture profile decision", `target:${cell.key}:${id}`)],
      })),
      occupant_total: decisions.length,
      unique_technology_total: decisions.length,
      observation: observation(cell, "NOT_APPLICABLE", 1),
      expectation: base.expectation,
      measures: null,
      policy,
      insight_refs: [],
      citations: policy ? [cite("Tenant architecture profile", `target:${cell.key}`)] : [],
    };
  });
}

const targetProjectionCells = targetCells();

// ─── Comparison ──────────────────────────────────────────────────────────────

function comparison(actualCells, baselineCells, kind) {
  const cells = referenceModel.cells.map((cell) => {
    const actual = actualCells.find((c) => c.cell_key === cell.key);
    const baseline = baselineCells.find((c) => c.cell_key === cell.key);
    const count = (status) => actual.occupants.filter((o) => o.policy_status === status).length;
    const unevaluable = actual.state === "UNOBSERVED" || actual.state === "UNBOUND";
    return {
      cell_key: cell.key,
      actual_state: actual.state,
      baseline_state: baseline.state,
      preferred_in_use: count("PREFERRED"),
      allowed_in_use: count("ALLOWED") + count("EXEMPTED"),
      discouraged_in_use: count("DISCOURAGED"),
      prohibited_in_use: count("PROHIBITED"),
      ungoverned_in_use: count("UNGOVERNED"),
      required_but_absent:
        !unevaluable && actual.state === "EMPTY" && actual.expectation.applicability === "REQUIRED",
      unevaluable,
    };
  });
  return {
    contract_version: "1.0.0",
    comparison_kind: kind,
    actual_projection_fingerprint: sha("projection:ESTATE:tenant"),
    baseline_projection_fingerprint: sha(`projection:${kind}:baseline`),
    cells,
    summary: {
      compared_cells: cells.length,
      aligned_cells: cells.filter((c) => !c.unevaluable && !c.required_but_absent
        && c.prohibited_in_use === 0 && c.discouraged_in_use === 0).length,
      cells_with_violations: cells.filter((c) => c.prohibited_in_use > 0).length,
      required_but_absent_cells: cells.filter((c) => c.required_but_absent).length,
      unevaluable_cells: cells.filter((c) => c.unevaluable).length,
      ungoverned_cells: cells.filter((c) => c.ungoverned_in_use > 0).length,
    },
    method_version: METHOD,
    input_fingerprint: sha(`comparison:${kind}`),
  };
}

// ─── Profile ─────────────────────────────────────────────────────────────────

const profileState = {
  name: "Enterprise architecture standard",
  reference_model_key: referenceModel.key,
  reference_model_version: referenceModel.version,
  cell_policies: Object.keys(POLICY)
    .map((cellKey) => estateCells.find((c) => c.cell_key === cellKey)?.policy)
    .filter(Boolean),
  extension_cells: [],
};

const profile = {
  id: PROFILE_ID,
  profile_key: "enterprise.target",
  name: profileState.name,
  reference_model_key: referenceModel.key,
  reference_model_version: referenceModel.version,
  version: 3,
  status: "ACTIVE",
  fingerprint: PROFILE_FINGERPRINT,
  created_at: "2026-06-01T09:00:00.000Z",
  updated_at: "2026-08-18T10:30:00.000Z",
  state: profileState,
};

// ─── Emit ────────────────────────────────────────────────────────────────────

const files = {
  "canvas-taxonomy.json": { contract_version: "1.0.0", ...taxonomy, content_hash: TAXONOMY_HASH },
  "canvas-reference-model.json": {
    contract_version: "1.0.0",
    ...referenceModel,
    taxonomy_key: taxonomy.key,
    taxonomy_version: taxonomy.version,
    taxonomy_content_hash: TAXONOMY_HASH,
    content_hash: MODEL_HASH,
  },
  "canvas-template.json": {
    contract_version: "1.0.0",
    ...template,
    reference_model_key: referenceModel.key,
    reference_model_version: referenceModel.version,
    content_hash: TEMPLATE_HASH,
  },
  "canvas-projection-estate.json": projection("ESTATE", null, estateCells),
  "canvas-projection-application.json": projection("APPLICATION", applicationSubject, applicationCells),
  "canvas-projection-target.json": projection("TARGET", null, targetProjectionCells),
  "canvas-comparison.json": comparison(estateCells, targetProjectionCells, "ACTUAL_TO_TARGET"),
  "canvas-architecture-profile.json": profile,
};

for (const [name, value] of Object.entries(files)) {
  fs.writeFileSync(path.join(out, name), `${JSON.stringify(value, null, 2)}\n`);
  console.log(`wrote ${name}`);
}
