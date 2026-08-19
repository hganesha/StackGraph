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

## Temporal model

Every projected edge should carry:
- `first_seen_at`
- `last_seen_at`
- `confidence`
- `assertion_class`
- optional `scan_id`
- optional `evidence_fact_ids`

This allows “what changed?” queries without turning every scan into a wholly separate graph.
