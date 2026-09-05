# ADR 0004: Impact traversal is predicate-policy driven

- Status: accepted
- Date: 2026-09-05

Impact is not generic N-hop reachability. Each action/subject pair selects an immutable active ImpactPolicy containing allowed predicates, directions, classifications, evidence/confidence requirements, STOP conditions, and resource budgets.

The initial `UPGRADE Package` policy starts with evidence-backed inbound `DEPENDS_ON` relationships and bounded repository context through `IMPLEMENTED_BY`, `CONTAINS`, `DEPLOYED_AS`, and `USES`. Missing evidence, low confidence, and traversal limits create explicit STOP or limitation records. Policy version and result hash make replay and comparison auditable.

