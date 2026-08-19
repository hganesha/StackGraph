# StackGraph ingestion sizing and pull plan

**Date:** 2026-08-18  
**Status:** deferred research for a possible future ecosystem/migration program; **not recommended for V0 dependency discovery**  
**Companion:** `stackgraph-implementation-plan.md`

## 1. Recommendation

For V0, use `stackgraph-dependency-ingestion-plan.md` instead. Identifying dependencies does not require consuming GH Archive or bringing down public source code. The sizing below is retained only to inform a later decision about adoption cohorts, ecosystem trajectories, or migration mining.

If a future ecosystem/migration program is approved, consume the complete hourly GH Archive stream, but do **not** load the complete event stream into PostgreSQL or hydrate every repository it mentions.

Use three progressively smaller layers:

1. **Raw landing:** every hourly compressed archive, content-addressed and replayable.
2. **Discovery/activity:** compact daily aggregates for a capped candidate repository cohort.
3. **Authoritative hydration:** current GitHub/package/source data only for curated, customer-relevant, high-quality reference, and migration-candidate repositories.

This gives StackGraph global discovery coverage at a manageable raw volume while concentrating graph/storage/API spend on evidence that can affect a customer decision.

## 2. Measured GH Archive volume

GH Archive publishes one gzip-compressed JSON event file per hour and exposes its history through BigQuery. Its site says archives begin in 2011 and the BigQuery dataset updates hourly: [GH Archive](https://www.gharchive.org/).

### Recent complete-day samples

The following sizes came from HTTP `Content-Length` headers for all 24 hourly files on each date:

| UTC date | Compressed bytes | Decimal MB/day |
|---|---:|---:|
| 2026-08-14 | 508,117,200 | 508.1 MB |
| 2026-08-16 | 495,511,463 | 495.5 MB |
| 2026-08-17 | 391,624,713 | 391.6 MB |
| **Observed mean** | **465,084,459** | **465.1 MB** |

Observed hourly files ranged from approximately 5.6 MB to 23.8 MB compressed.

### Event and compression sample

Four hours from 2026-08-17—00, 06, 12, and 18 UTC—were downloaded and parsed:

| Measure | Observed value |
|---|---:|
| Compressed bytes | 68,176,099 |
| Uncompressed bytes | 337,151,132 |
| Compression expansion | 4.95× |
| Events | 540,076 |
| Events per compressed MB | approximately 7,921 |
| Unique repositories across the four sampled hours | 107,240 |
| Unique actors across the four sampled hours | 66,482 |
| Push events | 516,362 / 95.6% |

The event-type mix is a point-in-time sample, not a permanent invariant. It is useful for capacity planning and demonstrates why persisting every push event as a canonical graph fact would be wasteful.

### Planning range

Using the measured files and adding headroom:

| Horizon | Compressed raw | Expanded processing bytes | Events |
|---|---:|---:|---:|
| Day | 0.4–0.6 GB | 2–3 GB | 3–4.8 million |
| 30 days | 12–18 GB | 60–90 GB | 90–145 million |
| Year | 150–220 GB | 0.75–1.1 TB | 1.1–1.75 billion |

These are ingestion-capacity estimates, not claims about future GitHub growth. Recalculate them from a rolling seven-day measurement before production sizing.

## 3. What not to ingest

Avoid these tempting but expensive interpretations:

- Do not store 1–2 billion full event JSON objects per year in PostgreSQL.
- Do not convert each push, watch, fork, issue, or PR event into an AGE node/edge.
- Do not hydrate every repository observed in GH Archive.
- Do not clone every candidate repository or retain every source snapshot.
- Do not ingest every package/version in npm or PyPI merely because deps.dev exposes it.
- Do not treat event-active repositories as an unbiased sample of all GitHub repositories.

If every raw event were normalized into an indexed relational row, a reasonable 300–700 bytes per row including indexes would produce roughly **0.4–1.2 TB of PostgreSQL growth per year**. That data is mostly unnecessary for StackGraph's product questions.

## 4. Recommended retained volumes

### 4.1 Raw archive landing

Retain compressed hourly objects, never expanded copies.

| Policy | Approximate retained size |
|---|---:|
| 30-day hot/replay window | 12–18 GB |
| 90-day hot/replay window | 36–54 GB |
| One complete year | 150–220 GB |

Recommended lifecycle:

- standard object storage for 30 days;
- colder storage through 13 months if replay independence is valuable;
- retain the hourly manifest, checksums, watermarks, parser versions, and selected evidence events indefinitely;
- expired global raw archives can be recovered from GH Archive/BigQuery if source availability risk is acceptable.

### 4.2 Candidate repository activity

Cap the bootstrap candidate table at **100,000 repositories**. Keep daily aggregates rather than raw events:

- push count and last head/default-branch signal;
- releases;
- PR/issue/review activity;
- unique active actors using bounded/sketchable aggregation where appropriate;
- forks/watches;
- first/last observed activity;
- cohort and score components.

Assuming 20,000–50,000 active candidate repositories per day and 400–800 bytes per aggregate row including indexes, this is approximately **3–15 GB/year**, with **5–20 GB/year** reserved after table/index overhead and revisions.

### 4.3 Tracked event evidence

For the first **10,000 hydrated public repositories**, retain only events that support a product conclusion or trigger a refresh. Budget **2–15 GB/year** depending on activity and how much payload evidence is retained.

### 4.4 GitHub hydration

Initial public-repository budget:

| Hydration level | Repository count | Estimated transfer/raw retention |
|---|---:|---:|
| Repository metadata and current state | 10,000 | 0.1–0.5 GB |
| Tree + selected manifests/configuration | 10,000 | 0.5–5 GB |
| Full default-branch source snapshot | at most 1,000 targeted repos | 5–20 GB typical planning range; enforce a 50 GB hard budget |
| Targeted history/diffs for migrations | 100–1,000 repos in V1 | budget separately after sampling |

Repository sizes have a heavy tail. Every fetch must have byte/file/time limits, and oversized repositories should fall back to selected-file hydration.

### 4.5 Package and dependency intelligence

MVP capacity target:

- 25,000–150,000 package versions discovered from the first customer/pilot estates;
- database budget for up to **250,000 package versions**;
- dependency-edge budget up to **5 million resolved edges**;
- one- or two-hop neighborhoods hydrated eagerly only around observed packages;
- deeper dependency graphs hydrated on demand;
- OSV checks only for observed/resolved versions;
- project/Scorecard/GitHub enrichment once per canonical project, not once per tenant.

Plan **5–20 GB** for canonical packages, versions, dependency edges, identities, indexes, and current external assessments at this initial ceiling. Keep 2–10 GB of compressed external raw observations depending on response retention.

### 4.6 Combined MVP envelope

| Store | Initial practical target | First-year planning envelope |
|---|---:|---:|
| Raw/object storage | 25–75 GB | 200–350 GB |
| PostgreSQL authoritative/current data | 20–60 GB | 50–150 GB |
| AGE projection | measure after vertical slice | reserve 25–100 GB, then resize from edge/node density |

The AGE estimate has the widest uncertainty because projection properties and indexes have not been implemented. Load-test the golden slice at 1×, 10×, and 100× before selecting production storage.

## 5. Historical bootstrap plan

Do not download the raw archive back to 2011. Use BigQuery to aggregate history close to the source.

### Bootstrap A — 24-month activity baseline

Purpose: health, trajectory, discovery, and reference-repository scoring.

1. Query day/month tables for the last 24 complete months.
2. Select only `repo.id`, `repo.name`, `actor.id`, `type`, `created_at`, and the small type-specific fields needed for action/head/release state.
3. Aggregate to repository-day or repository-month before exporting.
4. Keep only:
   - repositories associated with atomized curated technologies;
   - repositories discovered from customer package identities;
   - the highest-scoring active repositories by explicit cohort;
   - a bounded random/stratified comparison sample.
5. Cap the first exported candidate cohort at 100,000 repositories.

Planning assumption: **200–500 GB of BigQuery bytes processed** for a carefully column-pruned 24-month bootstrap, with **2–10 GB exported** after aggregation. Use a BigQuery dry run and maximum-bytes-billed guard before execution. GH Archive recommends restricting date ranges and notes that payload remains JSON because event shapes vary.

### Bootstrap B — curated technology/project resolution

1. Atomize the 192 curated seed rows into approximately 250–400 real technology/project candidates.
2. Attach purl, registry, project, and repository identities.
3. Pull 24-month activity for those repositories regardless of global candidate rank.
4. Hydrate current GitHub/deps.dev/OSV/Scorecard state.

This is the first high-quality OSS graph and should precede broad candidate hydration.

### Bootstrap C — customer-observed expansion

For every new customer scan:

1. Extract direct and locked package versions.
2. Resolve canonical purls and projects.
3. Query existing global OSS data.
4. Enqueue only missing/stale global identities.
5. Pull historical activity for newly linked projects.
6. Expand transitive neighborhoods within the configured depth/edge budget.

The OSS graph compounds globally; the same React/FastAPI/PostgreSQL project data is not fetched separately for every customer.

### Bootstrap D — migration cohorts, later

After V0, select 100–1,000 repositories with strong before/after technology signals. Use GH Archive push/head timestamps to locate candidate windows, then fetch targeted GitHub commits/diffs/manifests. Do not download full history for the global candidate set.

## 6. Continuous pull plan

### Hourly GH Archive consumer

1. Scheduler creates one work item for UTC hour `H` at `H+10 minutes`.
2. Fetch `YYYY-MM-DD-H.json.gz` with conditional headers.
3. If unavailable, retry at approximately +5, +15, +30, and +60 minutes, then move to delayed reconciliation.
4. Verify gzip integrity, content length/hash, and archive-hour envelope.
5. Persist the compressed object and immutable raw-observation metadata.
6. Stream-decompress; never materialize the expanded file on disk in production.
7. Validate event envelope and deduplicate by event ID.
8. Route in one pass:
   - tracked repository change triggers;
   - candidate repository daily aggregates;
   - curated/customer-linked evidence events;
   - discard/unretained events after counters and audit stats.
9. Commit the hourly watermark only after raw storage and aggregate/trigger writes succeed.
10. Seal/reconcile the prior day after 24 hours and report missing/changed hourly objects.

At the observed mean, an hour contains about 150,000 events and 19 MB compressed. A worker sustaining only 2,000 events/second processes an average hour in roughly 75 seconds. Two modest workers provide sufficient MVP throughput and restart capacity; benchmark the real parser/database batch path before fixing instance sizes.

### Daily work

- Close the prior UTC day and verify 24 hourly watermarks.
- Merge repository-day aggregates.
- Recompute candidate scores and cohort membership.
- Enqueue newly qualified repositories within the daily hydration budget.
- Refresh stale hot OSS identities and affected package-version assessments.
- Publish freshness, lag, rejected-event, and byte/event-count metrics.

### Weekly work

- Refresh warm project/repository/Scorecard observations.
- Re-evaluate curated/reference cohorts.
- Compact old staging partitions and apply object-storage lifecycle rules.
- Sample false-positive/false-negative candidate scoring.
- Reconcile measured volume against this capacity model.

### Monthly work

- Rebuild bounded trajectory windows from daily aggregates.
- Re-run a small BigQuery reconciliation/backfill for missed events or changed cohort membership.
- Recalculate retention forecasts and storage/index bloat.
- Review source schema drift, quotas, adapter versions, and provenance completeness.

## 7. Hydration budgets and backpressure

Initial configurable limits:

| Budget | Starting value |
|---|---:|
| Candidate cohort | 100,000 repositories |
| Fully hydrated public repositories | 10,000 |
| New public repository hydrations | 500–1,000/day |
| Full source snapshots | 1,000 total before review |
| Maximum individual source snapshot | 50 MB compressed, otherwise selected-file mode |
| Package versions | 250,000 |
| Resolved dependency edges | 5 million |
| Graph Explore real-node result | approximately 50 |

Workers must stop scheduling lower-priority hydration when any of these occurs:

- provider rate budget falls below its reserve;
- oldest customer/hot work exceeds its lag target;
- raw landing or database storage crosses a warning threshold;
- dead-letter/schema-drift rate exceeds threshold;
- dependency expansion reaches node/edge/depth budget;
- a repository exceeds size/time/file limits.

Customer and curated hot targets always outrank global discovery.

## 8. Pull implementation sequence

### Cycle 0 — seven-day benchmark

- Run header/size collection for every hourly archive.
- Download and parse a rotating sample of hours.
- Measure event types, event size, unique repos, parse speed, rejected events, and hourly lateness.
- Replace the planning ranges above with p50/p95/p99 values.

### Cycle 1 — raw and aggregate pipeline

- Implement hourly watermark, retries, checksum, raw object retention, streaming parser, event dedupe, and daily repository aggregates.
- Run continuously without any GitHub hydration for one week.
- Prove restart/replay produces identical aggregates.

### Cycle 2 — curated bootstrap

- Execute the 24-month BigQuery aggregate for the atomized curated cohort.
- Hydrate current state for approximately 250–400 projects/repositories.
- Enrich associated packages and versions.
- Feed the first live Technology Explorer.

### Cycle 3 — bounded public expansion

- Build and score the 100,000-repository candidate cohort.
- Hydrate the top 10,000 gradually at 500–1,000/day.
- Retain tree/manifests by default; full source only for reference/migration candidates.

### Cycle 4 — customer-driven compounding

- Connect enterprise scanners.
- Promote customer-observed packages/projects to hot priority.
- Fill missing dependency/health data and project it once globally.
- Measure time from customer scan to enriched evidence.

## 9. Required dashboards

- Hourly archive availability, size, checksum, lateness, and watermark.
- Events/second, bytes/second, event-type mix, dedupe/reject rate.
- Candidate/tracked/discarded event routing counts.
- Candidate cohort size and daily churn.
- GitHub/deps.dev/OSV/Scorecard quota, latency, cache/conditional hit rate, and freshness.
- Hydration queue depth and oldest work by priority.
- Object storage, Postgres, and AGE growth by source/entity/edge type.
- Facts without evidence, identity-resolution uncertainty, and projection lag.
- Actual versus forecast daily/monthly volume.

## 10. Sizing decision after the benchmark

The initial design is intentionally small:

- two streaming workers for GH Archive;
- PostgreSQL leasing/scheduling;
- one object-storage bucket with lifecycle rules;
- date-partitioned raw-observation metadata and repository-day aggregates;
- separate GitHub and external-enrichment worker pools with strict rate budgets.

Do not introduce Kafka, Spark, or a distributed lakehouse for the measured MVP volume. Reconsider only if the seven-day benchmark or the first 100,000-repository cohort shows sustained throughput, replay, or analytical requirements that PostgreSQL/object storage cannot meet.
