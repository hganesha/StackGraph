#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import statistics
import time
from urllib.parse import urlencode
from urllib.request import Request, urlopen


def percentile(values: list[float], percentage: float) -> float:
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, round((len(ordered) - 1) * percentage)))
    return ordered[index]


def main() -> None:
    parser = argparse.ArgumentParser(description="Benchmark a bounded StackGraph neighborhood read")
    parser.add_argument("center_id")
    parser.add_argument("--base-url", default="http://localhost:8080/api/v1")
    parser.add_argument("--requests", type=int, default=50)
    parser.add_argument("--depth", type=int, choices=(1, 2), default=2)
    parser.add_argument("--max-p95-ms", type=float)
    parser.add_argument(
        "--bearer-token",
        default=os.environ.get("STACKGRAPH_BENCHMARK_BEARER_TOKEN"),
    )
    args = parser.parse_args()
    if args.requests < 1:
        parser.error("--requests must be at least 1")

    query = urlencode({
        "center_id": args.center_id,
        "depth": args.depth,
        "real_node_limit": 50,
    })
    url = f"{args.base_url.rstrip('/')}/graph/neighborhood?{query}"
    headers = {"Authorization": f"Bearer {args.bearer_token}"} if args.bearer_token else {}
    durations = []
    for _ in range(args.requests):
        started = time.perf_counter()
        with urlopen(Request(url, headers=headers), timeout=10) as response:
            payload = json.load(response)
        durations.append((time.perf_counter() - started) * 1000)
        if len(payload["nodes"]) > 50:
            raise SystemExit("bounded graph contract violated: response contains more than 50 nodes")

    result = {
        "requests": args.requests,
        "depth": args.depth,
        "nodes": len(payload["nodes"]),
        "edges": len(payload["edges"]),
        "min_ms": round(min(durations), 2),
        "mean_ms": round(statistics.fmean(durations), 2),
        "p50_ms": round(percentile(durations, 0.50), 2),
        "p95_ms": round(percentile(durations, 0.95), 2),
        "max_ms": round(max(durations), 2),
    }
    print(json.dumps(result, sort_keys=True))
    if args.max_p95_ms is not None and result["p95_ms"] > args.max_p95_ms:
        raise SystemExit(
            f"p95 {result['p95_ms']}ms exceeds the {args.max_p95_ms}ms gate"
        )


if __name__ == "__main__":
    main()
