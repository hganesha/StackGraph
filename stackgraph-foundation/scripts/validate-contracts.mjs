import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import Ajv2020 from "ajv/dist/2020.js";
import addFormats from "ajv-formats";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const schemaDir = path.join(root, "contracts/v1/schemas");
const fixtureDir = path.join(root, "contracts/v1/fixtures");
const read = (relative) => JSON.parse(fs.readFileSync(path.join(root, relative), "utf8"));

const ajv = new Ajv2020({ allErrors: true, strict: true, strictRequired: false });
addFormats(ajv);
for (const name of fs.readdirSync(schemaDir).filter((name) => name.endsWith(".json"))) {
  ajv.addSchema(read(`contracts/v1/schemas/${name}`));
}

const cases = [
  ["contracts/v1/ontology.registry.json", "https://stackgraph.dev/contracts/v1/schemas/ontology-registry.schema.json"],
  ["contracts/v1/fixtures/scanner-request.json", "https://stackgraph.dev/contracts/v1/schemas/scanner-request.schema.json"],
  ["contracts/v1/fixtures/scanner-result.complete.json", "https://stackgraph.dev/contracts/v1/schemas/scanner-result.schema.json"],
  ["contracts/v1/fixtures/scanner-result.partial.json", "https://stackgraph.dev/contracts/v1/schemas/scanner-result.schema.json"],
  ["contracts/v1/fixtures/raw-observation.json", "https://stackgraph.dev/contracts/v1/schemas/raw-observation.schema.json"],
  ["contracts/v1/fixtures/raw-observation.npm-registry.json", "https://stackgraph.dev/contracts/v1/schemas/raw-observation.schema.json"],
  ["contracts/v1/fixtures/npm-resolution.private.json", "https://stackgraph.dev/contracts/v1/schemas/npm-resolution.schema.json#/$defs/dependencyProperties"],
  ["contracts/v1/fixtures/estate-summary.json", "https://stackgraph.dev/contracts/v1/schemas/read-models.schema.json#/$defs/estateSummary"],
  ["contracts/v1/fixtures/application-detail.json", "https://stackgraph.dev/contracts/v1/schemas/read-models.schema.json#/$defs/applicationDetail"],
  ["contracts/v1/fixtures/technology-detail.json", "https://stackgraph.dev/contracts/v1/schemas/read-models.schema.json#/$defs/technologyDetail"],
  ["contracts/v1/fixtures/modernization-list.json", "https://stackgraph.dev/contracts/v1/schemas/read-models.schema.json#/$defs/modernizationList"],
  ["contracts/v1/fixtures/graph-neighborhood.json", "https://stackgraph.dev/contracts/v1/schemas/read-models.schema.json#/$defs/graphNeighborhood"],
  ["contracts/v1/fixtures/evidence-detail.json", "https://stackgraph.dev/contracts/v1/schemas/read-models.schema.json#/$defs/evidenceDetail"],
  ["contracts/v1/fixtures/ask-response.json", "https://stackgraph.dev/contracts/v1/schemas/read-models.schema.json#/$defs/askResponse"],
  ["contracts/v1/fixtures/identity-review-result.json", "https://stackgraph.dev/contracts/v1/schemas/read-models.schema.json#/$defs/identityReviewResult"]
];

let failed = false;
for (const [fixture, schemaId] of cases) {
  const valid = ajv.validate(schemaId, read(fixture));
  if (!valid) {
    failed = true;
    console.error(`${fixture}: invalid`);
    console.error(ajv.errorsText(ajv.errors, { separator: "\n" }));
  } else {
    console.log(`${fixture}: valid`);
  }
}

for (const relative of ["contracts/v1/openapi.json", ...fs.readdirSync(fixtureDir).map((name) => `contracts/v1/fixtures/${name}`)]) {
  read(relative);
}

const openapi = read("contracts/v1/openapi.json");
const visit = (value) => {
  if (!value || typeof value !== "object") return;
  if (typeof value.$ref === "string" && value.$ref.startsWith("#/")) {
    const target = value.$ref.slice(2).split("/").reduce((current, key) => current?.[key], openapi);
    if (target === undefined) {
      failed = true;
      console.error(`OpenAPI reference does not resolve: ${value.$ref}`);
    }
  }
  for (const child of Object.values(value)) visit(child);
};
visit(openapi);

const factValidator = ajv.getSchema("https://stackgraph.dev/contracts/v1/schemas/fact.schema.json");
const validFact = read("contracts/v1/fixtures/scanner-result.complete.json").facts[0];
for (const invalid of [
  {...validFact, object_value: "ambiguous"},
  Object.fromEntries(Object.entries(validFact).filter(([key]) => key !== "object_entity")),
  {...validFact, evidence: []}
]) {
  if (factValidator(invalid)) {
    failed = true;
    console.error("negative fact-contract case was incorrectly accepted");
  }
}

for (const invalid of [
  {...validFact, properties: {...validFact.properties, registry_resolution: undefined}},
  {
    ...validFact,
    properties: {
      ...validFact.properties,
      registry_resolution: {...validFact.properties.registry_resolution, origin: "https://token@registry.npmjs.org/"}
    }
  },
  {
    ...validFact,
    properties: {
      ...validFact.properties,
      artifact: {...validFact.properties.artifact, resolved_uri: "https://token@registry.npmjs.org/axios.tgz"}
    }
  }
]) {
  const sanitized = JSON.parse(JSON.stringify(invalid));
  if (factValidator(sanitized)) {
    failed = true;
    console.error("invalid npm registry-resolution case was incorrectly accepted");
  }
}

const yarnFact = {...validFact, extractor: {...validFact.extractor, key: "yarn-lock"}};
if (!factValidator(yarnFact)) {
  failed = true;
  console.error("valid Yarn registry-resolution fact was incorrectly rejected");
}
const yarnWithoutRegistry = JSON.parse(JSON.stringify(yarnFact));
delete yarnWithoutRegistry.properties.registry_resolution;
if (factValidator(yarnWithoutRegistry)) {
  failed = true;
  console.error("Yarn dependency without registry resolution was incorrectly accepted");
}

const sql = fs.readFileSync(path.join(root, "schema.sql"), "utf8");
for (const requiredSql of [
  "CREATE TABLE package_registry (",
  "CREATE TABLE package_registry_scope (",
  "CREATE TABLE package_registry_identity (",
  "CREATE TABLE dependency_resolution (",
  "CREATE TRIGGER trg_validate_dependency_resolution_scope"
]) {
  if (!sql.includes(requiredSql)) {
    failed = true;
    console.error(`schema.sql is missing required npm registry substrate: ${requiredSql}`);
  }
}
if (failed) process.exit(1);
