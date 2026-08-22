// Generates the fixture-mode Architecture Canvas payloads in
// packages/shared/src/fixtures/. These are UI-demo fixtures: they exercise every
// cell state, policy status, measure eligibility, and tray condition the renderer
// must handle. The golden contract fixtures live in
// stackgraph-foundation/contracts/v1/fixtures/ and are owned by the API workstream.
//
// Run: node scripts/generate_canvas_fixtures.mjs
import fs from "node:fs";
import path from "node:path";
import crypto from "node:crypto";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const out = path.join(root, "packages/shared/src/fixtures");

const AS_OF = "2026-08-22T09:00:00.000Z";
const TAXONOMY = {
  taxonomy_key: "stackgraph.technical-taxonomy",
  taxonomy_version: "2.0.0",
  taxonomy_content_hash: sha("taxonomy-v2"),
};
const MODEL_KEY = "architecture.stackgraph.reference";
const MODEL_VERSION = "1.0.0";
const TEMPLATE_KEY = "canvas.stackgraph.reference";
const TEMPLATE_VERSION = "1.0.0";
const METHOD = "architecture-canvas/v1";

function sha(seed) {
  return `sha256:${crypto.createHash("sha256").update(seed).digest("hex")}`;
}
let uuidCounter = 0;
function uuid(seed) {
  const digest = crypto.createHash("sha256").update(`${seed}:${uuidCounter++}`).digest("hex");
  return [digest.slice(0, 8), digest.slice(8, 12), `4${digest.slice(13, 16)}`,
    `8${digest.slice(17, 20)}`, digest.slice(20, 32)].join("-");
}
const factId = (seed) => uuid(`fact:${seed}`);
const cite = (label, seed) => ({ fact_id: factId(seed), label });

// ─── Domains and aspects (spec §4.3, §4.5) ──────────────────────────────────

const DOMAINS = [
  ["experience", "Experience & Channels", "How do humans and external clients interact with the system?"],
  ["application", "Application & Services", "Where do application behaviour and service responsibilities execute?"],
  ["integration", "Integration & Messaging", "How do requests, events, and workflows cross boundaries?"],
  ["data", "Data & Information", "How is information stored, retrieved, moved, and processed?"],
  ["platform", "Platform & Runtime", "On what runtime, compute, network, and managed platform does the system operate?"],
  ["delivery", "Delivery & Operations", "How is software built, tested, configured, released, observed, and operated?"],
].map(([key, label, question], order) => ({ key, label, question, order }));

const ASPECTS = [
  ["security-privacy", "Security & privacy", "Controls protecting confidentiality, integrity, and privacy of the system and its data."],
  ["identity-access", "Identity & access", "Authentication, authorization, and credential distribution across the estate."],
  ["governance-compliance", "Governance & compliance", "Policy, standards, audit, and regulatory obligations applied to architecture decisions."],
  ["reliability-resilience", "Reliability & resilience", "Failure containment, recovery, and continuity of service."],
  ["observability", "Observability", "The ability to explain system behaviour from emitted signals."],
  ["developer-experience", "Developer experience", "Feedback speed and friction for the teams changing this system."],
  ["cost-efficiency", "Cost & efficiency", "Resource consumption and unit economics of the architecture."],
  ["data-governance", "Data governance", "Ownership, lineage, classification, and lifecycle of information assets."],
].map(([key, label, definition], order) => ({ key, label, definition, order }));

// ─── Cells (spec §4.4) ───────────────────────────────────────────────────────
// [concern, label, definition, icon, capability bindings, aspects, applicability, min, max, diversity]

const CELLS = {
  experience: [
    ["ui-rendering", "UI rendering & interaction", "Turn application state into interactive interface for a human.", "ui-rendering", ["ui-rendering", "client-reactivity"], [], "REQUIRED", 1, 2, 2],
    ["web-framework", "Web framework & server rendering", "Deliver and render web application shells, including the server boundary.", "framework", ["server-side-rendering", "meta-framework"], [], "RECOMMENDED", 1, 1, 1],
    ["client-navigation", "Client navigation", "Map URLs and navigation intent to application views.", "route", ["application-routing"], [], "RECOMMENDED", 1, 1, 1],
    ["state-consumption", "Client & server state", "Hold UI-local state and synchronise remote authoritative state.", "state", ["client-state-management", "server-state-management"], [], "RECOMMENDED", 1, 3, 3],
    ["forms-validation", "Forms & input validation", "Collect, validate, and submit user input safely.", "form", ["form-state", "runtime-validation"], ["security-privacy"], "RECOMMENDED", 1, 2, 2],
    ["design-system", "Design system & accessible UI", "Provide consistent, accessible interface primitives and styling.", "palette", ["css-styling", "accessible-ui-primitives"], [], "RECOMMENDED", 1, 2, 2],
    ["channels", "Mobile, desktop & embedded channels", "Deliver the experience to non-browser channels.", "devices", ["mobile-channel", "desktop-channel"], [], "OPTIONAL", null, null, null],
  ],
  application: [
    ["service-api", "Service & API delivery", "Expose application behaviour over a network interface.", "api", ["http-web-api", "rpc-service"], ["security-privacy"], "REQUIRED", 1, 2, 2],
    ["domain-logic", "Domain & application logic", "Execute the business rules the service is responsible for.", "logic", ["domain-logic", "rules-execution"], [], "REQUIRED", 1, null, null],
    ["persistence-adapter", "Data access & persistence adapters", "Translate between application types and storage engines.", "database-cog", ["orm-data-access", "query-builder"], [], "RECOMMENDED", 1, 2, 2],
    ["outbound-clients", "Outbound clients & integration adapters", "Call external and internal services from application code.", "arrow-out", ["http-client", "sdk-client"], ["reliability-resilience"], "RECOMMENDED", 1, 3, 3],
    ["background-jobs", "Background jobs & scheduling", "Run deferred, scheduled, and asynchronous work.", "clock-cog", ["background-jobs", "task-scheduling"], [], "RECOMMENDED", 1, 2, 2],
    ["workflow-execution", "Workflow & process execution", "Coordinate long-running, multi-step business processes.", "workflow", ["durable-workflow", "saga-coordination"], ["reliability-resilience"], "OPTIONAL", null, null, null],
    ["runtime-framework", "Runtime & application frameworks", "The framework and runtime hosting application code.", "box", ["application-framework", "native-runtime-capability"], [], "REQUIRED", 1, 3, 3],
  ],
  integration: [
    ["edge-gateway", "Edge proxy & API gateway", "Terminate, authenticate, and route inbound traffic at the edge.", "gateway", ["reverse-proxy", "api-gateway"], ["security-privacy", "identity-access"], "REQUIRED", 1, 2, 2],
    ["api-contract", "API contracts & interchange", "Define and validate the shape of exchanged messages.", "contract", ["api-contract", "schema-registry"], ["governance-compliance"], "RECOMMENDED", 1, 2, 2],
    ["service-connectivity", "Service-to-service connectivity", "Discover, secure, and route traffic between internal services.", "network", ["service-mesh", "service-discovery"], ["security-privacy", "reliability-resilience"], "OPTIONAL", null, null, null],
    ["message-routing", "Message routing & queues", "Deliver work items between producers and consumers.", "queue", ["message-broker", "task-queue"], ["reliability-resilience"], "RECOMMENDED", 1, 2, 2],
    ["event-stream", "Durable event streams", "Retain an ordered, replayable log of domain events.", "stream", ["durable-event-stream"], ["reliability-resilience"], "OPTIONAL", null, null, null],
    ["stream-processing", "Stream processing", "Transform and aggregate events in motion.", "waveform", ["stream-processing"], [], "OPTIONAL", null, null, null],
    ["integration-orchestration", "Integration orchestration", "Coordinate multi-system integration flows.", "sitemap", ["data-orchestration", "integration-flow"], [], "OPTIONAL", null, null, null],
  ],
  data: [
    ["relational-store", "Relational persistence", "Store authoritative transactional records with relational semantics.", "database", ["relational-database"], ["data-governance"], "REQUIRED", 1, 2, 2],
    ["nonrelational-store", "Document, key-value & graph persistence", "Store records whose access pattern is not relational.", "database-share", ["document-database", "key-value-database", "graph-database"], ["data-governance"], "OPTIONAL", null, null, null],
    ["cache-session", "Cache & session state", "Hold derived or ephemeral state close to the reader.", "bolt", ["cache", "session-store"], ["reliability-resilience"], "RECOMMENDED", 1, 2, 2],
    ["search-retrieval", "Search & vector retrieval", "Retrieve records by relevance rather than by key.", "search", ["full-text-search", "vector-search"], [], "OPTIONAL", null, null, null],
    ["object-storage", "Object & file storage", "Store unstructured blobs and files.", "archive", ["object-storage"], ["data-governance"], "RECOMMENDED", 1, 2, 2],
    ["analytical-store", "Warehouse, lake & lakehouse", "Hold analytical copies of estate data.", "building-warehouse", ["data-warehouse", "data-lake"], ["data-governance", "cost-efficiency"], "OPTIONAL", null, null, null],
    ["data-processing", "Batch & streaming data processing", "Compute derived datasets from stored or streaming inputs.", "cpu", ["batch-processing", "stream-analytics"], [], "OPTIONAL", null, null, null],
    ["data-movement", "Data movement & orchestration", "Move and schedule data between systems.", "transfer", ["data-orchestration", "change-data-capture"], ["data-governance"], "OPTIONAL", null, null, null],
  ],
  platform: [
    ["language-runtime", "Language & runtime", "The language runtime executing deployed code.", "terminal", ["language-runtime"], [], "REQUIRED", 1, 3, 3],
    ["container-runtime", "Container & artifact runtime", "Package and run deployable artifacts.", "container", ["container-runtime", "artifact-format"], [], "RECOMMENDED", 1, 1, 1],
    ["compute-target", "Compute targets", "The machine abstraction application workloads run on.", "server", ["virtual-machine-compute", "bare-metal-compute"], ["cost-efficiency"], "RECOMMENDED", 1, 2, 2],
    ["orchestration", "Container orchestration", "Schedule, scale, and heal containerised workloads.", "orchestration", ["kubernetes-orchestration", "container-scheduler"], ["reliability-resilience"], "OPTIONAL", null, null, null],
    ["managed-compute", "Serverless & managed compute", "Run workloads on provider-managed execution.", "cloud-cog", ["serverless-compute", "managed-runtime"], ["cost-efficiency"], "OPTIONAL", null, null, null],
    ["network-ingress", "Network, ingress & connectivity", "Provide addressability, ingress, and network isolation.", "network-share", ["ingress-controller", "load-balancer", "private-network"], ["security-privacy"], "RECOMMENDED", 1, 2, 2],
    ["platform-services", "Cloud & on-premises platform services", "Provider-managed services the architecture depends on.", "cloud", ["cloud-platform-service"], ["cost-efficiency", "governance-compliance"], "RECOMMENDED", 1, null, null],
  ],
  delivery: [
    ["source-build", "Source, build & package management", "Version, build, and publish deployable artifacts.", "package", ["build-bundling", "package-management"], ["developer-experience"], "REQUIRED", 1, 3, 3],
    ["automated-testing", "Automated testing & quality controls", "Verify behaviour and quality before release.", "test", ["unit-testing", "e2e-testing", "static-analysis"], ["developer-experience"], "REQUIRED", 1, 4, 4],
    ["ci-cd", "CI/CD automation", "Automate the path from commit to running software.", "pipeline", ["ci-automation", "cd-automation"], ["developer-experience", "governance-compliance"], "REQUIRED", 1, 2, 2],
    ["infrastructure-as-code", "Infrastructure as code", "Declare and version infrastructure state.", "file-code", ["infrastructure-as-code"], ["governance-compliance"], "RECOMMENDED", 1, 2, 2],
    ["config-secrets", "Configuration & secret delivery", "Deliver configuration and credentials to running workloads.", "key", ["configuration-management", "secret-management"], ["security-privacy", "identity-access"], "REQUIRED", 1, 2, 2],
    ["release-management", "Release & deployment management", "Control how change reaches each environment.", "rocket", ["release-management", "progressive-delivery"], ["reliability-resilience"], "RECOMMENDED", 1, 2, 2],
    ["telemetry", "Telemetry & observability operations", "Collect, store, and query signals about running systems.", "activity", ["observability-telemetry", "log-aggregation"], ["observability"], "REQUIRED", 1, 3, 3],
    ["incident-ops", "Reliability & incident operations", "Detect, route, and resolve production incidents.", "alert", ["alerting", "incident-response"], ["reliability-resilience", "observability"], "RECOMMENDED", 1, 2, 2],
  ],
};

const cellDefinitions = [];
const cellIndex = new Map();
for (const domain of DOMAINS) {
  for (const row of CELLS[domain.key]) {
    const [concern, label, definition, icon, capabilities, aspects, applicability, min, max, diversity] = row;
    const key = `cell.${domain.key}.${concern}`;
    const bindings = capabilities.length
      ? [{ kind: "capability", capability_keys: capabilities }]
      : [{ kind: "unbound", reason: "No supported sensor produces evidence for this concern yet." }];
    const cell = {
      key,
      concern_key: `concern.${domain.key}.${concern}`,
      domain_key: domain.key,
      label,
      definition,
      bindings,
      aspect_keys: aspects,
      default_expectation: {
        applicability,
        minimum_implementations: min,
        maximum_implementations: max,
        allowed_diversity: diversity,
      },
      observation_rule_key: `observation.${domain.key}.${concern}`,
      icon,
    };
    cellDefinitions.push(cell);
    cellIndex.set(key, cell);
  }
}

// Two cells are deliberately unbound so the renderer's UNBOUND treatment is exercised.
for (const key of ["cell.delivery.incident-ops", "cell.data.data-movement"]) {
  cellIndex.get(key).bindings = [{
    kind: "unbound",
    reason: key.endsWith("incident-ops")
      ? "StackGraph does not yet ingest incident-management or alerting configuration."
      : "Change-data-capture and pipeline schedules are not part of any supported sensor.",
  }];
}

const referenceModel = {
  contract_version: "1.0.0",
  key: MODEL_KEY,
  version: MODEL_VERSION,
  name: "StackGraph reference architecture",
  description:
    "Canonical six-domain technical reference model covering experience, application, integration, data, platform, and delivery concerns.",
  ...TAXONOMY,
  content_hash: sha(`${MODEL_KEY}:${MODEL_VERSION}`),
  domains: DOMAINS,
  aspects: ASPECTS,
  cells: cellDefinitions,
};

const template = {
  contract_version: "1.0.0",
  key: TEMPLATE_KEY,
  version: TEMPLATE_VERSION,
  name: "Reference layout",
  reference_model_key: MODEL_KEY,
  reference_model_version: MODEL_VERSION,
  content_hash: sha(`${TEMPLATE_KEY}:${TEMPLATE_VERSION}`),
  bands: DOMAINS.map((domain) => ({
    domain_key: domain.key,
    order: domain.order,
    columns: 4,
    cells: cellDefinitions
      .filter((cell) => cell.domain_key === domain.key)
      .map((cell) => ({ cell_key: cell.key })),
  })),
  aspect_rail: ASPECTS.map((aspect) => aspect.key),
};

// ─── Occupant catalogue ──────────────────────────────────────────────────────

const TECH = {};
function tech(name, kind = "Technology") {
  if (!TECH[name]) {
    TECH[name] = {
      id: uuid(`tech:${name}`),
      kind,
      name,
      canonical_key: `stackgraph:technology:${name.toLowerCase().replace(/[^a-z0-9]+/g, "-")}`,
    };
  }
  return TECH[name];
}

// [cell, technology, placementKeys, classification, confidence, apps, repos, deployments, policyStatus]
const PLACEMENTS = [
  ["cell.experience.ui-rendering", "React", ["ui-rendering"], "CURATED", 0.97, 9, 14, 11, "PREFERRED"],
  ["cell.experience.ui-rendering", "Vue", ["ui-rendering"], "CATALOG_MATCH", 0.71, 1, 1, 1, "DISCOURAGED"],
  ["cell.experience.web-framework", "Next.js", ["meta-framework", "server-side-rendering"], "CURATED", 0.95, 7, 9, 8, "PREFERRED"],
  ["cell.experience.client-navigation", "Next.js", ["application-routing"], "CURATED", 0.92, 7, 9, 8, "PREFERRED"],
  ["cell.experience.state-consumption", "TanStack Query", ["server-state-management"], "CURATED", 0.9, 6, 8, 7, "ALLOWED"],
  ["cell.experience.state-consumption", "Zustand", ["client-state-management"], "CURATED", 0.88, 5, 6, 5, "PREFERRED"],
  ["cell.experience.state-consumption", "Redux", ["client-state-management"], "CATALOG_MATCH", 0.66, 2, 2, 2, "DISCOURAGED"],
  ["cell.experience.state-consumption", "MobX", ["client-state-management"], "CATALOG_MATCH", 0.58, 1, 1, 0, "PROHIBITED"],
  ["cell.experience.forms-validation", "Zod", ["runtime-validation"], "CURATED", 0.91, 6, 8, 6, "PREFERRED"],
  ["cell.experience.design-system", "Tailwind CSS", ["css-styling"], "CURATED", 0.86, 4, 5, 4, "ALLOWED"],
  ["cell.experience.design-system", "Radix UI", ["accessible-ui-primitives"], "CURATED", 0.83, 3, 4, 3, "ALLOWED"],

  ["cell.application.service-api", "FastAPI", ["http-web-api"], "CURATED", 0.96, 8, 11, 10, "PREFERRED"],
  ["cell.application.service-api", "Express", ["http-web-api"], "CATALOG_MATCH", 0.74, 3, 4, 3, "ALLOWED"],
  ["cell.application.service-api", "Flask", ["http-web-api"], "CATALOG_MATCH", 0.69, 2, 2, 1, "DISCOURAGED"],
  ["cell.application.persistence-adapter", "SQLAlchemy", ["orm-data-access"], "CURATED", 0.94, 7, 9, 8, "PREFERRED"],
  ["cell.application.persistence-adapter", "Prisma", ["orm-data-access"], "CURATED", 0.81, 2, 3, 2, "ALLOWED"],
  ["cell.application.persistence-adapter", "Drizzle", ["orm-data-access"], "CATALOG_MATCH", 0.62, 1, 1, 1, "UNGOVERNED"],
  ["cell.application.outbound-clients", "httpx", ["http-client"], "CURATED", 0.89, 6, 8, 7, "ALLOWED"],
  ["cell.application.outbound-clients", "requests", ["http-client"], "CATALOG_MATCH", 0.77, 5, 7, 4, "DISCOURAGED"],
  ["cell.application.background-jobs", "Celery", ["background-jobs"], "CURATED", 0.85, 4, 5, 4, "ALLOWED"],
  ["cell.application.runtime-framework", "Python 3.12", ["language-runtime", "application-framework"], "CURATED", 0.98, 9, 12, 11, "PREFERRED"],
  ["cell.application.runtime-framework", "Node.js 22", ["language-runtime", "application-framework"], "CURATED", 0.97, 8, 10, 9, "PREFERRED"],

  ["cell.integration.edge-gateway", "NGINX", ["reverse-proxy"], "CURATED", 0.93, 8, 3, 9, "ALLOWED"],
  ["cell.integration.edge-gateway", "Kong", ["api-gateway"], "CATALOG_MATCH", 0.7, 2, 1, 2, "UNGOVERNED"],
  ["cell.integration.api-contract", "OpenAPI", ["api-contract"], "CURATED", 0.95, 9, 12, 0, "PREFERRED"],
  ["cell.integration.api-contract", "Protobuf", ["api-contract"], "CATALOG_MATCH", 0.64, 1, 2, 1, "ALLOWED"],
  ["cell.integration.message-routing", "Redis", ["task-queue"], "DETERMINISTIC", 1, 5, 6, 5, "ALLOWED"],
  ["cell.integration.message-routing", "RabbitMQ", ["message-broker"], "CATALOG_MATCH", 0.72, 2, 2, 2, "DISCOURAGED"],
  ["cell.integration.event-stream", "Apache Kafka", ["durable-event-stream"], "CURATED", 0.88, 3, 3, 3, "PREFERRED"],

  ["cell.data.relational-store", "PostgreSQL", ["relational-database"], "DETERMINISTIC", 1, 9, 11, 10, "PREFERRED"],
  ["cell.data.relational-store", "MySQL", ["relational-database"], "DETERMINISTIC", 1, 2, 2, 2, "DISCOURAGED"],
  ["cell.data.cache-session", "Redis", ["cache", "session-store"], "DETERMINISTIC", 1, 7, 8, 7, "PREFERRED"],
  ["cell.data.object-storage", "Amazon S3", ["object-storage"], "DETERMINISTIC", 1, 6, 5, 6, "PREFERRED"],
  ["cell.data.search-retrieval", "OpenSearch", ["full-text-search"], "CATALOG_MATCH", 0.68, 2, 2, 2, "UNGOVERNED"],
  ["cell.data.search-retrieval", "pgvector", ["vector-search"], "DETERMINISTIC", 1, 1, 1, 1, "ALLOWED"],

  ["cell.platform.language-runtime", "Python 3.12", ["language-runtime"], "CURATED", 0.98, 9, 12, 11, "PREFERRED"],
  ["cell.platform.language-runtime", "Node.js 22", ["language-runtime"], "CURATED", 0.97, 8, 10, 9, "PREFERRED"],
  ["cell.platform.language-runtime", "Go 1.22", ["language-runtime"], "CATALOG_MATCH", 0.79, 2, 2, 2, "ALLOWED"],
  ["cell.platform.container-runtime", "Docker", ["container-runtime"], "CURATED", 0.96, 9, 12, 11, "PREFERRED"],
  ["cell.platform.orchestration", "Kubernetes", ["kubernetes-orchestration"], "CURATED", 0.94, 8, 4, 10, "PREFERRED"],
  ["cell.platform.network-ingress", "NGINX Ingress", ["ingress-controller"], "CATALOG_MATCH", 0.8, 6, 2, 8, "ALLOWED"],
  ["cell.platform.platform-services", "Amazon RDS", ["cloud-platform-service"], "DETERMINISTIC", 1, 7, 0, 8, "PREFERRED"],
  ["cell.platform.platform-services", "Amazon ElastiCache", ["cloud-platform-service"], "DETERMINISTIC", 1, 5, 0, 6, "ALLOWED"],

  ["cell.delivery.source-build", "pnpm", ["package-management"], "CURATED", 0.9, 6, 8, 0, "PREFERRED"],
  ["cell.delivery.source-build", "uv", ["package-management"], "CURATED", 0.87, 5, 7, 0, "PREFERRED"],
  ["cell.delivery.source-build", "Vite", ["build-bundling"], "CURATED", 0.84, 4, 5, 0, "ALLOWED"],
  ["cell.delivery.automated-testing", "Playwright", ["e2e-testing"], "CURATED", 0.89, 5, 6, 0, "PREFERRED"],
  ["cell.delivery.automated-testing", "pytest", ["unit-testing"], "CURATED", 0.93, 7, 9, 0, "PREFERRED"],
  ["cell.delivery.automated-testing", "Jest", ["unit-testing"], "CATALOG_MATCH", 0.6, 2, 2, 0, "DISCOURAGED"],
  ["cell.delivery.telemetry", "OpenTelemetry", ["observability-telemetry"], "CURATED", 0.86, 6, 7, 7, "PREFERRED"],
  ["cell.delivery.telemetry", "Prometheus", ["observability-telemetry"], "CATALOG_MATCH", 0.78, 5, 1, 6, "ALLOWED"],
];

function occupant(row) {
  const [, name, placementKeys, classification, confidence, apps, repos, deployments, policyStatus] = row;
  return {
    technology: tech(name),
    placement_keys: placementKeys,
    classification,
    confidence,
    confidence_label: confidence >= 0.85 ? "HIGH" : confidence >= 0.6 ? "MEDIUM" : "LOW",
    adoption: { applications: apps, repositories: repos, deployments },
    policy_status: policyStatus,
    citations: [cite(`${name} detected in dependency manifest`, `${name}:manifest`)],
  };
}

// ─── Per-cell state script ───────────────────────────────────────────────────
// Cells not listed here derive their state from whether placements exist.

const STATE_OVERRIDES = {
  "cell.experience.channels": ["NOT_APPLICABLE", "The active profile marks non-browser channels not applicable for this scope.", "COMPLETE"],
  "cell.application.domain-logic": ["UNOBSERVED", "Domain logic is not attributable from dependency evidence alone; no code-context scan has completed for 6 of 12 repositories.", "PARTIAL"],
  "cell.application.workflow-execution": ["EMPTY", "All 12 in-scope repositories were scanned and no durable-workflow capability was observed.", "COMPLETE"],
  "cell.integration.service-connectivity": ["EMPTY", "All 12 in-scope repositories and 11 deployments were observed; no service-mesh or discovery capability was found.", "COMPLETE"],
  "cell.integration.stream-processing": ["UNOBSERVED", "Stream-processing detection requires runtime evidence; no runtime sensor has reported for this scope.", "ABSENT"],
  "cell.integration.integration-orchestration": ["UNOBSERVED", "Orchestration detection is unsupported for the CARGO and MAVEN ecosystems present in this scope.", "UNSUPPORTED"],
  "cell.data.nonrelational-store": ["EMPTY", "Infrastructure evidence covered all 11 deployments; no document, key-value, or graph engine was observed.", "COMPLETE"],
  "cell.data.analytical-store": ["UNOBSERVED", "Warehouse and lake observations depend on a cloud-inventory connector that is not configured.", "ABSENT"],
  "cell.data.data-processing": ["UNOBSERVED", "Batch and streaming processing evidence is stale: last successful observation is 41 days old.", "STALE"],
  "cell.data.data-movement": ["UNBOUND", "Change-data-capture and pipeline schedules are not part of any supported sensor.", "ABSENT"],
  "cell.platform.compute-target": ["UNOBSERVED", "Compute-target evidence covers 4 of 11 deployments; the remainder have no infrastructure sensor.", "PARTIAL"],
  "cell.platform.managed-compute": ["EMPTY", "All 11 deployments were observed; no serverless or provider-managed execution was found.", "COMPLETE"],
  "cell.delivery.ci-cd": ["UNOBSERVED", "CI/CD workflow parsing is not yet a supported sensor kind for this scope.", "UNSUPPORTED"],
  "cell.delivery.infrastructure-as-code": ["UNOBSERVED", "Infrastructure-as-code detection requires repository file-tree evidence, which is missing for 9 of 12 repositories.", "PARTIAL"],
  "cell.delivery.config-secrets": ["UNOBSERVED", "Secret-delivery observation is unsupported without a platform-configuration connector.", "UNSUPPORTED"],
  "cell.delivery.release-management": ["EMPTY", "Deployment evidence covered all 11 deployments; no progressive-delivery or release-management capability was observed.", "COMPLETE"],
  "cell.delivery.incident-ops": ["UNBOUND", "StackGraph does not yet ingest incident-management or alerting configuration.", "ABSENT"],
};

const SENSOR_KINDS = {
  experience: ["dependency-manifest", "lockfile-resolution"],
  application: ["dependency-manifest", "lockfile-resolution", "code-context"],
  integration: ["dependency-manifest", "infrastructure-config", "runtime-observation"],
  data: ["infrastructure-config", "runtime-observation"],
  platform: ["infrastructure-config", "deployment-manifest"],
  delivery: ["dependency-manifest", "repository-file-tree"],
};

function observation(cell, status, subjectsInScope, subjectsObserved) {
  const required = SENSOR_KINDS[cell.domain_key];
  const supported = status === "UNSUPPORTED" ? required.slice(0, 1) : required;
  return {
    rule_key: cell.observation_rule_key,
    status,
    required_sensor_kinds: required,
    supported_sensor_kinds: supported,
    sensors: required.map((kind) => ({
      sensor_kind: kind,
      supported: supported.includes(kind),
      last_observed_at: supported.includes(kind)
        ? (status === "STALE" ? "2026-07-12T04:15:00.000Z" : "2026-08-22T04:15:00.000Z")
        : null,
      freshness: supported.includes(kind)
        ? {
            observed_at: status === "STALE" ? "2026-07-12T04:15:00.000Z" : "2026-08-22T04:15:00.000Z",
            status: status === "STALE" ? "STALE" : "FRESH",
            source_key: kind,
          }
        : null,
    })),
    subjects_in_scope: subjectsInScope,
    subjects_observed: subjectsObserved,
    freshness_status: status === "STALE" ? "STALE" : status === "ABSENT" ? "UNKNOWN" : "FRESH",
    unsupported_ecosystems: status === "UNSUPPORTED" ? ["CARGO", "MAVEN"] : [],
    missing_inputs:
      status === "COMPLETE"
        ? []
        : status === "PARTIAL"
          ? [`${subjectsInScope - subjectsObserved} of ${subjectsInScope} subjects unobserved`]
          : status === "STALE"
            ? ["last successful observation is older than the 30-day freshness budget"]
            : status === "UNSUPPORTED"
              ? ["required sensor kind is not supported for this scope"]
              : ["no sensor has reported for this cell"],
    method_version: METHOD,
    input_fingerprint: sha(`observation:${cell.key}:${status}`),
  };
}

function measure(value, status, inputs, facts = []) {
  return { value, status, inputs, supporting_fact_ids: facts, method_version: METHOD };
}

function measuresFor(cell, occupants) {
  if (!occupants.length) return null;
  const unique = new Set(occupants.map((o) => o.technology.id)).size;
  const max = cell.default_expectation.maximum_implementations;
  const discouraged = occupants.filter((o) => o.policy_status === "DISCOURAGED").length;
  const prohibited = occupants.filter((o) => o.policy_status === "PROHIBITED").length;
  const governed = occupants.some((o) => o.policy_status !== "UNGOVERNED");
  const coverage = measure(1, "ELIGIBLE", ["occupant count", "minimum implementations"],
    [factId(`coverage:${cell.key}`)]);
  const standardisation = unique <= 1
    ? measure(null, "INSUFFICIENT_DATA", ["adoption population below comparison threshold"])
    : measure(Math.max(0, 1 - (unique - 1) / Math.max(1, (max ?? unique))), "ELIGIBLE",
      ["unique technology placements", "allowed diversity"], [factId(`std:${cell.key}`)]);
  const currency = measure(
    Math.min(1, 0.55 + occupants.filter((o) => o.classification === "CURATED").length * 0.12),
    "ELIGIBLE", ["resolved versions", "deprecation metadata"], [factId(`cur:${cell.key}`)]);
  const risk = measure(Math.max(0, 1 - (prohibited * 0.4 + discouraged * 0.15)), "ELIGIBLE",
    ["attributed deterministic insights", "advisory matches"], [factId(`risk:${cell.key}`)]);
  const conformance = governed
    ? measure(Math.max(0, 1 - (prohibited * 0.5 + discouraged * 0.2)), "ELIGIBLE",
      ["effective tenant policy", "resolved placements"], [factId(`conf:${cell.key}`)])
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
    components: { coverage, standardisation, currency, risk, conformance },
    confidence,
    confidence_label: confidence >= 0.85 ? "HIGH" : confidence >= 0.6 ? "MEDIUM" : "LOW",
    method_version: METHOD,
    missing_inputs: [
      ...(standardisation.status === "INSUFFICIENT_DATA" ? ["comparison population for standardisation"] : []),
      ...(conformance.status === "NOT_CONFIGURED" ? ["target policy for this cell"] : []),
    ],
  };
}

const POLICY_RATIONALE = {
  "cell.experience.ui-rendering": ["React is the single approved rendering library; Vue entered through an acquired codebase.", "platform-architecture"],
  "cell.experience.state-consumption": ["Zustand for client state, TanStack Query for server state. Redux is being retired; MobX is prohibited.", "frontend-guild"],
  "cell.application.service-api": ["FastAPI is the standard service framework. Express is allowed for edge workers only.", "platform-architecture"],
  "cell.data.relational-store": ["PostgreSQL is the standard relational engine across all environments.", "data-platform"],
  "cell.integration.edge-gateway": ["NGINX terminates edge traffic. Kong was introduced without review and is unresolved.", "platform-architecture"],
  "cell.delivery.telemetry": ["OpenTelemetry is the standard instrumentation layer; Prometheus remains allowed for infrastructure metrics.", "observability-guild"],
};

function policyFor(cell, occupants) {
  const entry = POLICY_RATIONALE[cell.key];
  const governedOccupants = occupants.filter((o) => o.policy_status !== "UNGOVERNED");
  if (!entry && !governedOccupants.length) return null;
  return {
    governed: true,
    profile_id: PROFILE_ID,
    profile_version: 3,
    decisions: governedOccupants.map((o) => ({
      technology: o.technology,
      decision: o.policy_status,
      rationale: null,
    })),
    exceptions: cell.key === "cell.experience.ui-rendering"
      ? [{
          id: uuid(`exception:${cell.key}`),
          scope_selector: { application_ids: [], description: "Acquired Helios storefront, until migration completes" },
          rationale: "Vue remains in place until the Helios storefront migration lands.",
          owner: "platform-architecture",
          effective_from: "2026-04-01T00:00:00.000Z",
          effective_to: "2026-12-31T00:00:00.000Z",
        }]
      : [],
    rationale: entry ? entry[0] : null,
    owner: entry ? entry[1] : null,
    effective_from: "2026-01-01T00:00:00.000Z",
    effective_to: null,
    migrated_function_keys: cell.key === "cell.experience.state-consumption" ? ["client-state-management"] : [],
    fingerprint: sha(`policy:${cell.key}`),
  };
}

const PROFILE_ID = uuid("profile");

function buildCells(scale) {
  return cellDefinitions.map((cell) => {
    const rows = PLACEMENTS.filter((row) => row[0] === cell.key);
    const occupants = rows.map(occupant).map((o) => scale === 1 ? o : ({
      ...o,
      adoption: {
        applications: Math.max(o.adoption.applications ? 1 : 0, Math.round(o.adoption.applications * scale)),
        repositories: Math.max(o.adoption.repositories ? 1 : 0, Math.round(o.adoption.repositories * scale)),
        deployments: Math.max(o.adoption.deployments ? 1 : 0, Math.round(o.adoption.deployments * scale)),
      },
    }));
    const override = STATE_OVERRIDES[cell.key];
    const state = override ? override[0] : occupants.length ? "POPULATED" : "EMPTY";
    const stateReason = override
      ? override[1]
      : occupants.length
        ? `${occupants.length} placement${occupants.length === 1 ? "" : "s"} with supporting evidence.`
        : "All in-scope subjects were observed and no implementation was found.";
    const observationStatus = override ? override[2] : "COMPLETE";
    const visible = state === "POPULATED" ? occupants : [];
    const measures = state === "POPULATED" ? measuresFor(cell, visible) : null;
    const policy = policyFor(cell, visible);
    const expectationSource = POLICY_RATIONALE[cell.key] ? "TENANT_PROFILE" : "REFERENCE_MODEL";
    return {
      cell_key: cell.key,
      state,
      state_reason: stateReason,
      occupants: visible,
      occupant_total: visible.length,
      unique_technology_total: new Set(visible.map((o) => o.technology.id)).size,
      observation: observation(cell, observationStatus, 12, observationStatus === "COMPLETE" ? 12
        : observationStatus === "PARTIAL" ? 6 : observationStatus === "STALE" ? 12 : 0),
      expectation: {
        ...cell.default_expectation,
        applicability: state === "NOT_APPLICABLE" ? "NOT_APPLICABLE" : cell.default_expectation.applicability,
        source: state === "NOT_APPLICABLE" ? "TENANT_PROFILE" : expectationSource,
        scope_selector: state === "NOT_APPLICABLE"
          ? { description: "Web-only product line" } : null,
        rationale: state === "NOT_APPLICABLE"
          ? "This product line ships web only; native channels are out of scope."
          : POLICY_RATIONALE[cell.key]?.[0] ?? null,
        owner: state === "NOT_APPLICABLE" ? "platform-architecture" : POLICY_RATIONALE[cell.key]?.[1] ?? null,
        effective_from: expectationSource === "TENANT_PROFILE" ? "2026-01-01T00:00:00.000Z" : null,
        effective_to: null,
      },
      measures,
      policy,
      insight_refs: state === "POPULATED" && visible.some((o) => o.policy_status === "PROHIBITED" || o.policy_status === "DISCOURAGED")
        ? [uuid(`insight:${cell.key}`)]
        : [],
      citations: visible.length
        ? [cite(`${cell.label} evidence`, `cell:${cell.key}`)]
        : [],
    };
  });
}

function summarise(cells) {
  const byState = { POPULATED: 0, EMPTY: 0, NOT_APPLICABLE: 0, UNOBSERVED: 0, UNBOUND: 0 };
  const byBand = { STRONG: 0, ADEQUATE: 0, WEAK: 0, AT_RISK: 0, UNSCORED: 0 };
  const byPolicy = { PREFERRED: 0, ALLOWED: 0, DISCOURAGED: 0, PROHIBITED: 0, UNGOVERNED: 0 };
  const unique = new Set();
  let placements = 0;
  let governed = 0;
  for (const cell of cells) {
    byState[cell.state] += 1;
    if (cell.measures?.posture_band) byBand[cell.measures.posture_band] += 1;
    else if (cell.state === "POPULATED") byBand.UNSCORED += 1;
    if (cell.policy?.governed) governed += 1;
    for (const occupant of cell.occupants) {
      byPolicy[occupant.policy_status] += 1;
      unique.add(occupant.technology.id);
      placements += 1;
    }
  }
  return {
    cells_total: cells.length,
    by_state: byState,
    by_posture_band: byBand,
    by_policy_status: byPolicy,
    unique_technologies: unique.size,
    placements_total: placements,
    governed_cells: governed,
    unmapped_observations: 3,
    ambiguous_observations: 2,
    unresolved_policies: 2,
  };
}

const tray = {
  unclassified_technologies: [
    { technology: tech("internal-billing-sdk"), reason: "No catalog match and no capability inference above the confidence floor.", ecosystem: "PYPI", citations: [cite("Declared in pyproject.toml", "unclassified:billing")] },
    { technology: tech("acme-telemetry-shim"), reason: "Private registry package; no public metadata available.", ecosystem: "NPM", citations: [cite("Declared in package.json", "unclassified:shim")] },
    { technology: tech("legacy-soap-bridge"), reason: "Ecosystem MAVEN is not yet analyzable.", ecosystem: "MAVEN", citations: [cite("Declared in pom.xml", "unclassified:soap")] },
  ],
  ambiguous_observations: [
    { technology: tech("Redis"), candidate_cell_keys: ["cell.data.cache-session", "cell.integration.message-routing"], reason: "Cache and task-queue capabilities are both evidenced; the placements are not mutually exclusive but the adoption counts must not be double-counted.", citations: [cite("Redis client and broker configuration observed", "ambiguous:redis")] },
    { technology: tech("NGINX"), candidate_cell_keys: ["cell.integration.edge-gateway", "cell.platform.network-ingress"], reason: "Reverse-proxy and ingress-controller roles both match the observed configuration.", citations: [cite("NGINX configuration observed in two deployments", "ambiguous:nginx")] },
  ],
  unresolved_policies: [
    {
      policy_key: "tenant-design-tokens", label: "Tenant design tokens", source: "CUSTOM",
      reason: "Custom governed function has no mapping to a canonical cell or tenant extension cell.",
      technology_count: 2,
      technologies: [
        { technology: tech("Style Dictionary"), decision: "PREFERRED", rationale: null },
        { technology: tech("Theo"), decision: "PROHIBITED", rationale: null },
      ],
    },
    {
      policy_key: "legacy-reporting-stack", label: "Legacy reporting stack", source: "CUSTOM",
      reason: "Migrated from code policies; awaiting an architecture-cell decision.",
      technology_count: 3,
      technologies: [
        { technology: tech("Crystal Reports"), decision: "DISCOURAGED", rationale: null },
        { technology: tech("JasperReports"), decision: "ALLOWED", rationale: null },
        { technology: tech("Apache Superset"), decision: "PREFERRED", rationale: null },
      ],
    },
  ],
  filtered_out_total: 0,
};

function projection(scope, subject, cells, profileFingerprint) {
  return {
    contract_version: "1.0.0",
    as_of: AS_OF,
    method_version: METHOD,
    ...TAXONOMY,
    reference_model_key: MODEL_KEY,
    reference_model_version: MODEL_VERSION,
    reference_model_content_hash: referenceModel.content_hash,
    template_key: TEMPLATE_KEY,
    template_version: TEMPLATE_VERSION,
    tenant_profile_fingerprint: profileFingerprint,
    scope,
    subject,
    cells,
    classification_tray: tray,
    summary: summarise(cells),
    input_fingerprint: sha(`projection:${scope}:${subject?.id ?? "tenant"}`),
  };
}

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
  return cellDefinitions.map((cell) => {
    const base = estateCells.find((c) => c.cell_key === cell.key);
    const policy = base.policy;
    const applicable = base.expectation.applicability !== "NOT_APPLICABLE";
    const state = !applicable ? "NOT_APPLICABLE" : policy ? "POPULATED" : "EMPTY";
    return {
      cell_key: cell.key,
      state,
      state_reason: !applicable
        ? "The active profile marks this concern not applicable for this scope."
        : policy
          ? `${policy.decisions.length} governed technology decision${policy.decisions.length === 1 ? "" : "s"}.`
          : "No target decision has been recorded for this concern.",
      occupants: policy
        ? policy.decisions.map((decision) => ({
            technology: decision.technology,
            placement_keys: [],
            classification: "CURATED",
            confidence: 1,
            confidence_label: "HIGH",
            adoption: { applications: 0, repositories: 0, deployments: 0 },
            policy_status: decision.decision,
            citations: [cite("Tenant architecture profile decision", `target:${cell.key}:${decision.technology.name}`)],
          }))
        : [],
      occupant_total: policy ? policy.decisions.length : 0,
      unique_technology_total: policy ? policy.decisions.length : 0,
      observation: observation(cell, "COMPLETE", 0, 0),
      expectation: base.expectation,
      measures: null,
      policy,
      insight_refs: [],
      citations: policy ? [cite("Tenant architecture profile", `target:${cell.key}`)] : [],
    };
  });
}

// ─── Comparison ──────────────────────────────────────────────────────────────

function comparison(actualCells, targetProjectionCells) {
  const cells = cellDefinitions.map((cell) => {
    const actual = actualCells.find((c) => c.cell_key === cell.key);
    const target = targetProjectionCells.find((c) => c.cell_key === cell.key);
    const counts = {
      preferred_in_use: actual.occupants.filter((o) => o.policy_status === "PREFERRED").length,
      allowed_in_use: actual.occupants.filter((o) => o.policy_status === "ALLOWED").length,
      discouraged_in_use: actual.occupants.filter((o) => o.policy_status === "DISCOURAGED").length,
      prohibited_in_use: actual.occupants.filter((o) => o.policy_status === "PROHIBITED").length,
      required_absent: 0,
    };
    let status;
    let reason;
    let unevaluable = null;
    if (actual.state === "UNOBSERVED" || actual.state === "UNBOUND") {
      status = "UNEVALUABLE";
      reason = "Observation is incomplete, so conformance cannot be asserted.";
      unevaluable = actual.observation.missing_inputs[0] ?? actual.state_reason;
    } else if (actual.expectation.applicability === "NOT_APPLICABLE") {
      status = "NOT_APPLICABLE";
      reason = actual.expectation.rationale ?? "The concern does not apply to this scope.";
    } else if (!target.policy) {
      status = "UNGOVERNED";
      reason = "No target decision exists for this concern.";
    } else if (counts.prohibited_in_use > 0) {
      status = "PROHIBITED_IN_USE";
      reason = `${counts.prohibited_in_use} prohibited technology in use.`;
    } else if (counts.discouraged_in_use > 0) {
      status = "DISCOURAGED_IN_USE";
      reason = `${counts.discouraged_in_use} discouraged technology still in use.`;
    } else if (actual.state === "EMPTY" && actual.expectation.applicability === "REQUIRED") {
      status = "REQUIRED_ABSENT";
      counts.required_absent = 1;
      reason = "A required concern has no observed implementation.";
    } else if (counts.preferred_in_use > 0 && counts.allowed_in_use === 0) {
      status = "PREFERRED_IN_USE";
      reason = "Only preferred technologies are in use.";
    } else if (counts.allowed_in_use > 0) {
      status = "ALLOWED_IN_USE";
      reason = "In use technologies are allowed but not preferred.";
    } else {
      status = "ALIGNED";
      reason = "Observed state matches the target.";
    }
    return {
      cell_key: cell.key,
      status,
      status_reason: reason,
      counts,
      added_technologies: [],
      removed_technologies: [],
      unevaluable_reason: unevaluable,
    };
  });
  const byStatus = {
    ALIGNED: 0, PREFERRED_IN_USE: 0, ALLOWED_IN_USE: 0, DISCOURAGED_IN_USE: 0,
    PROHIBITED_IN_USE: 0, REQUIRED_ABSENT: 0, NOT_APPLICABLE: 0, UNGOVERNED: 0, UNEVALUABLE: 0,
  };
  for (const cell of cells) byStatus[cell.status] += 1;
  return {
    contract_version: "1.0.0",
    comparison_kind: "ACTUAL_TO_TARGET",
    actual_projection_fingerprint: sha("projection:ESTATE:tenant"),
    baseline_projection_fingerprint: sha("projection:TARGET:tenant"),
    cells,
    summary: {
      cells_total: cells.length,
      by_status: byStatus,
      incompatible_cells: [],
      excluded_extension_cells: [],
    },
    method_version: METHOD,
    input_fingerprint: sha("comparison:estate-to-target"),
  };
}

const targetProjectionCells = targetCells();

// ─── Tenant profile ──────────────────────────────────────────────────────────

const profile = {
  contract_version: "1.0.0",
  id: PROFILE_ID,
  name: "Enterprise architecture standard",
  reference_model_key: MODEL_KEY,
  reference_model_version: MODEL_VERSION,
  version: 3,
  status: "ACTIVE",
  cell_overrides: Object.entries(POLICY_RATIONALE).map(([cellKey, [rationale, owner]]) => {
    const cell = cellIndex.get(cellKey);
    const decisions = estateCells.find((c) => c.cell_key === cellKey)?.policy?.decisions ?? [];
    const ids = (decision) => decisions.filter((d) => d.decision === decision).map((d) => d.technology.id);
    return {
      cell_key: cellKey,
      ...cell.default_expectation,
      scope_selector: {},
      preferred_technology_ids: ids("PREFERRED"),
      allowed_technology_ids: ids("ALLOWED"),
      discouraged_technology_ids: ids("DISCOURAGED"),
      prohibited_technology_ids: ids("PROHIBITED"),
      rationale,
      owner,
      effective_from: "2026-01-01T00:00:00.000Z",
      effective_to: null,
      exceptions: [],
    };
  }),
  extension_cells: [],
  fingerprint: PROFILE_FINGERPRINT,
  updated_by: "platform-architecture",
  updated_at: "2026-08-18T10:30:00.000Z",
};

// ─── Emit ────────────────────────────────────────────────────────────────────

const files = {
  "canvas-reference-model.json": referenceModel,
  "canvas-template.json": template,
  "canvas-projection-estate.json": projection("ESTATE", null, estateCells, PROFILE_FINGERPRINT),
  "canvas-projection-application.json": projection("APPLICATION", applicationSubject, applicationCells, PROFILE_FINGERPRINT),
  "canvas-projection-target.json": projection("TARGET", null, targetProjectionCells, PROFILE_FINGERPRINT),
  "canvas-comparison.json": comparison(estateCells, targetProjectionCells),
  "canvas-architecture-profile.json": profile,
};

for (const [name, value] of Object.entries(files)) {
  fs.writeFileSync(path.join(out, name), `${JSON.stringify(value, null, 2)}\n`);
  console.log(`wrote ${name}`);
}
