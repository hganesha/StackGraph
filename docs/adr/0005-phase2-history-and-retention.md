# ADR 0005: Preserve recomputable history with bounded sensitive retention

- Status: accepted
- Date: 2026-09-05

Scanner fact history remains revision-pinned and bitemporal. Repository fingerprints are derived facts per source revision, so history can be inspected without replacing direct evidence. Activity keeps bounded raw provider events and versioned 7/30/90-day aggregates that can be recomputed.

Provider actor identities are classified only from authoritative provider type/login metadata. AI assistance is never inferred from commit text. Human-facing product decisions must use aggregate signals and must not turn contributor activity into individual performance scoring. Ordinary activity uses retention class `BOUNDED_ACTIVITY_120D`; governance and security exceptions require an explicit class and policy.

