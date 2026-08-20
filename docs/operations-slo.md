# Operational SLOs and ownership

The executable snapshot is `python -m stackgraph_data.operations`. It reports the queue, lease,
freshness, webhook, projection, dead-letter, intelligence, and AI cost/latency signals used by the
Estate Health product surface and by deployment monitoring.

| Signal | Alert threshold | Owner | Response |
| --- | ---: | --- | --- |
| Oldest pending ingest run | 5 minutes | `discovery-on-call` | Check provider quota/backoff and worker leases. |
| Expired ingest leases | any | `discovery-on-call` | Restart or replace the worker; confirm retry/dead-letter outcome. |
| Unreplayed dead letters | any | `data-platform-on-call` | Classify, correct, and replay with an audit record. |
| Oldest projection event | 2 minutes | `data-platform-on-call` | Check AGE availability, parity fallback, and projection worker health. |
| Oldest intelligence job | 5 minutes | `intelligence-on-call` | Check worker/model policy and provider quota. |
| Failed intelligence jobs | any | `intelligence-on-call` | Inspect bounded error detail and requeue after correction. |
| Webhook processing lag | 1 minute | `discovery-on-call` | Check ingress, signature processing, and database availability. |
| Failed webhooks | any | `discovery-on-call` | Replay from immutable evidence after correction. |
| Stale/error sources | any | `data-quality-owner` | Confirm source availability and freshness limitations. |
| Failed AI calls in 24h | any | `intelligence-on-call` | Check provider/model routing; deterministic results remain authoritative. |
| Active provider throttling/exhaustion | any | `discovery-on-call` | Respect the recorded reset/backoff time; reduce concurrency or request budget before replay. |

The production topology scrapes the API's bearer-protected Prometheus `/metrics` endpoint every
30 seconds. `infrastructure/observability/alerts.yml` evaluates every threshold above and
Alertmanager groups delivery by the named owner. `make production-alert-test` exercises the
configured webhook path. The JSON CLI remains available for ad-hoc snapshots. AI spend and
latency are reported without an alert threshold because budgets are tenant-specific.
