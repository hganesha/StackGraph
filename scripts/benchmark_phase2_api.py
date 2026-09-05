#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
import os
import statistics
import time
from concurrent.futures import ThreadPoolExecutor
from urllib.request import Request, urlopen


def percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    index = max(0, math.ceil(len(ordered) * fraction) - 1)
    return ordered[index]


def timed_get(url: str, headers: dict[str, str], timeout: float) -> float:
    started = time.perf_counter()
    with urlopen(Request(url, headers=headers), timeout=timeout) as response:
        if response.status != 200:
            raise RuntimeError(f"{url} returned HTTP {response.status}")
        json.load(response)
    return (time.perf_counter() - started) * 1000


def measure(
    *, url: str, headers: dict[str, str], requests: int, concurrency: int,
    timeout: float, p95_limit: float, p99_limit: float,
) -> tuple[dict[str, float | int | str], bool]:
    with ThreadPoolExecutor(max_workers=concurrency) as executor:
        durations = list(executor.map(
            lambda _: timed_get(url, headers, timeout), range(requests),
        ))
    p95 = percentile(durations, 0.95)
    p99 = percentile(durations, 0.99)
    result: dict[str, float | int | str] = {
        "url": url, "requests": requests, "concurrency": concurrency,
        "mean_ms": round(statistics.fmean(durations), 2),
        "p50_ms": round(percentile(durations, 0.50), 2),
        "p95_ms": round(p95, 2), "p99_ms": round(p99, 2),
        "max_ms": round(max(durations), 2),
        "p95_limit_ms": p95_limit, "p99_limit_ms": p99_limit,
    }
    return result, p95 <= p95_limit and p99 <= p99_limit


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run the read-only Phase 2 interactive API latency gates.",
    )
    parser.add_argument("entity_id", help="Canonical Package entity ID")
    parser.add_argument("--simulation-id", help="Optional durable SimulationRun ID")
    parser.add_argument("--base-url", default="http://localhost:8080/api/v1")
    parser.add_argument("--requests", type=int, default=10_000)
    parser.add_argument("--concurrency", type=int, default=20)
    parser.add_argument("--timeout-seconds", type=float, default=10)
    parser.add_argument(
        "--bearer-token", default=os.environ.get("STACKGRAPH_BENCHMARK_BEARER_TOKEN"),
    )
    args = parser.parse_args()
    if args.requests < 100:
        parser.error("--requests must be at least 100 for a meaningful percentile gate")
    if not 1 <= args.concurrency <= 200:
        parser.error("--concurrency must be between 1 and 200")

    base = args.base_url.rstrip("/")
    endpoints = [
        ("action_types", f"{base}/action-types", 250.0, 750.0),
        ("valid_targets", f"{base}/entities/{args.entity_id}/valid-targets", 400.0, 1000.0),
        ("scopes", f"{base}/entities/{args.entity_id}/scopes", 250.0, 750.0),
    ]
    if args.simulation_id:
        endpoints.append((
            "simulation_status", f"{base}/simulations/{args.simulation_id}", 250.0, 750.0,
        ))
    headers = (
        {"Authorization": f"Bearer {args.bearer_token}"} if args.bearer_token else {}
    )
    results = {}
    passed = True
    for name, url, p95_limit, p99_limit in endpoints:
        result, endpoint_passed = measure(
            url=url, headers=headers, requests=args.requests,
            concurrency=args.concurrency, timeout=args.timeout_seconds,
            p95_limit=p95_limit, p99_limit=p99_limit,
        )
        result["passed"] = endpoint_passed
        results[name] = result
        passed = passed and endpoint_passed
    print(json.dumps({
        "schema_version": "phase2-api-benchmark/1.0.0",
        "passed": passed, "results": results,
    }, sort_keys=True))
    if not passed:
        raise SystemExit("one or more Phase 2 API latency gates failed")


if __name__ == "__main__":
    main()
