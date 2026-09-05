# ADR 0002: Deterministic Mutation IR is the change boundary

- Status: accepted
- Date: 2026-09-05

Every supported change entry point compiles into the same versioned Mutation IR and ordered ChangeSet. Deterministic engines consume only persisted canonical IDs, exact targets, observed scopes, constraints, and provenance; they never consume natural-language intent directly.

Mutation and ChangeSet fingerprints are canonical SHA-256 values. A tenant has one semantic ChangeSet per input fingerprint, independent of request idempotency keys. Ambiguous identity, unknown targets/scopes, unsupported actions, and no-effect changes produce named blocking gates. Validated or otherwise terminal Mutation rows are immutable.

