# ADR 0001: Phase 2 contracts evolve additively

- Status: accepted
- Date: 2026-09-05

The scanner remains on result contract `1.0.0` while its extractor advances from `1.10.0` to `1.11.0`. New facts, predicates, value-record kinds, and optional API response fields are additive. Existing repository-level dependency facts remain available while component-owned facts are introduced. A major contract version is required only when a required field, meaning, or accepted value is removed or changed incompatibly.

Consumers must ignore unknown value-record fields, use the ontology registry for predicates, and key scanner replay by extractor version plus source revision. OpenAPI and generated TypeScript types are checked in and regenerated together.

