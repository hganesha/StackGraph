# ADR 0003: Simulations are durable immutable overlays

- Status: accepted
- Date: 2026-09-05

A SimulationRun is an asynchronous durable job pinned to a ChangeSet fingerprint, estate/projection watermark, ImpactPolicy, provider version, and observed scanner versions. Submission is semantically idempotent. Terminal inputs, findings, interpretations, limitations, and result hashes are immutable.

Simulation creates a hypothetical before/after overlay in finding payloads. It never rewrites authoritative entity or fact tables. Deterministic findings and optional AI interpretation are stored separately. If AI is unavailable, deterministic completion remains successful and the interpretation partition reports that limitation.

