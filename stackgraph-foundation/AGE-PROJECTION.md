# Apache AGE Projection

PostgreSQL remains authoritative for scans, facts, evidence, assessments and recommendations. AGE is populated as a projection for graph traversal.

## Write strategy

1. Repository scanner writes a scan snapshot and normalized facts into PostgreSQL staging/authoritative tables.
2. Entity/relationship upserts occur in bulk.
3. Evidence rows are appended.
4. A projection job batches changed entities/edges into AGE.
5. The scan is marked complete only after authoritative writes succeed; AGE projection can retry independently.
6. Read APIs may combine SQL aggregation with AGE traversal.

Avoid per-file or per-import AGE writes during scanning.

## Projection granularity

V1 graph nodes:
- business entities
- application/service/component/repository
- package/package version/framework/runtime/language/database
- deployment/environment/compute/cloud/region/infrastructure
- OSS projects/repos/releases/licenses/reference implementations/migration patterns
- vulnerabilities/findings/recommendations

Do not create file/function/class/symbol nodes in V1. Those remain evidence locators.

## Physical V1 mapping

The V1 projection deliberately uses stable generic labels rather than creating a physical AGE label for every ontology type:

- `Entity` vertices are keyed by the canonical PostgreSQL entity UUID and carry namespace, entity type, canonical key, name, temporal fields, tenant scope, and serialized source properties.
- `Relationship` edges are keyed by the fact `logical_key` and carry the current fact UUID, predicate as `relationship_type`, confidence, assertion class, temporal fields, source snapshot, and evidence fact IDs.
- `HAS_PROPERTY` facts refresh their subject vertex but do not create graph edges.
- A complete snapshot emits `CLOSE` outbox entries for facts it closes. The projection worker removes the corresponding edge; it does not delete the canonical entity vertex.
- Projection jobs claim `projection_outbox` rows with leases and `FOR UPDATE SKIP LOCKED`. AGE writes and outbox acknowledgement commit in the same PostgreSQL transaction.

The generic mapping keeps graph traversal independent of Cypher label interpolation and lets the ontology evolve without graph DDL for each new entity or predicate. API read models still expose the canonical ontology types and predicates, not the generic physical labels.

## Temporal model

Every projected edge should carry:
- `first_seen_at`
- `last_seen_at`
- `confidence`
- `assertion_class`
- optional `scan_id`
- optional `evidence_fact_ids`

This allows “what changed?” queries without turning every scan into a wholly separate graph.
