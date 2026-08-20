# Failure and recovery drills

Milestones 1–4 use executable drills instead of an operator-only checklist.

| Failure | Automated evidence | Expected invariant |
| --- | --- | --- |
| Worker dies after lease | `test_github_control_loop.py` expired-lease/dead-letter cases | Another worker retries; exhausted work is durable and replayable. |
| Duplicate webhook | `test_github_installation_integration.py` webhook replay case | One provider delivery produces at most one scheduled semantic run. |
| Provider rate limit or drift | `test_github_acquisition.py`, deps.dev/OSV adapter tests | Backoff is bounded; invalid response shapes never become facts. |
| Corrupted evidence object | local and S3 evidence-store tests | Read/replay fails checksum validation; corrupt bytes are never trusted. |
| Partial/truncated repository | acquisition and scanner partial tests | Partial input cannot close complete state or assert absence. |
| Projection unavailable/lagging | API graph aggregation tests | Bounded SQL fallback serves the read; parity/lag counters identify it. |
| Database loss | `make recovery-drill` | A fresh database restores equal authoritative counts. |
| AGE projection loss | `make recovery-drill` | AGE is recreated solely from authoritative PostgreSQL outbox state. |
| 100+ repository load | `make pilot-100` | Targets and limitations are emitted to a durable JSON artifact. |

`make recovery-drill` creates uniquely named ephemeral databases, restores and validates them, rebuilds
the graph projection, writes `artifacts/recovery/recovery-*.json`, and removes only those ephemeral databases.
The object-store adapter separately verifies content-addressed replay and governed tenant deletion. A deployment
must additionally exercise its cloud bucket replication and key-recovery procedure because those controls are
provider/account-specific.

OpenSSF Scorecard and broad public-GitHub polling are not V0 sources. They remain deferred until a pilot owner
defines target selection, quota budgets, staleness semantics, and ranking effects. OSV and deps.dev are the
bounded V0 public enrichment sources.
