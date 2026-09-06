#!/usr/bin/env python3
"""Measure scanner latency, memory, and throughput against the golden corpus.

§9.2 sets scanner objectives — p95 scan duration under 90 s for a standard repository, peak RSS
under 1 GiB, at least 60 standard repositories per hour per worker — that had no executable
benchmark. This is that benchmark. It reports per-case and aggregate percentiles so a
regression is attributable to a repository shape rather than to an average.

    scripts/benchmark_scanner.py --iterations 5 --output artifacts/scanner-benchmark.json
    scripts/benchmark_scanner.py --compare artifacts/scanner-benchmark.json

Peak RSS is sampled with `resource.getrusage`, which reports the high-water mark for the whole
process. Scans run in-process and sequentially, so the figure is the maximum reached across the
run rather than an attribution to any single case; per-case memory is reported as the delta in
that high-water mark, which is a lower bound and is labelled as such.
"""

from __future__ import annotations

import argparse
import json
import resource
import statistics
import sys
import time
from pathlib import Path
from tempfile import TemporaryDirectory

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "services" / "enterprise-discovery"))
sys.path.insert(0, str(REPOSITORY_ROOT / "services" / "enterprise-discovery" / "tests"))

from golden_corpus import load_cases, materialize  # noqa: E402
from stackgraph_discovery.repository_scanner import (  # noqa: E402
    SCANNER_KEY,
    SCANNER_VERSION,
    scan_repository,
)

# §9.2 objectives, expressed so a breach is a failure rather than a note in a log.
STANDARD_REPOSITORY_P95_SECONDS = 90.0
PEAK_RSS_LIMIT_BYTES = 1024 * 1024 * 1024
MINIMUM_REPOSITORIES_PER_HOUR = 60.0
REGRESSION_MARGIN = 1.5  # a p95 may not grow by more than half again before it is a regression


def _peak_rss_bytes() -> int:
    usage = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    # Linux reports kilobytes; macOS reports bytes.
    return usage * 1024 if sys.platform != "darwin" else usage


def _percentile(values: list[float], fraction: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, round(fraction * (len(ordered) - 1))))
    return ordered[index]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--iterations", type=int, default=3)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--compare", type=Path)
    arguments = parser.parse_args()

    cases = load_cases()
    per_case: list[dict[str, object]] = []
    durations: list[float] = []

    with TemporaryDirectory() as workspace:
        checkouts = {case.identifier: materialize(case, Path(workspace)) for case in cases}
        for case in cases:
            request = case.request(checkouts[case.identifier])
            samples: list[float] = []
            facts = 0
            files = 0
            rss_before = _peak_rss_bytes()
            for _ in range(arguments.iterations):
                started = time.perf_counter()
                result = scan_repository(request)
                samples.append(time.perf_counter() - started)
                facts = len(result.get("facts") or ())
                files = int((result.get("stats") or {}).get("files_scanned") or 0)
            durations.extend(samples)
            per_case.append({
                "id": case.identifier,
                "iterations": arguments.iterations,
                "files_scanned": files,
                "facts_emitted": facts,
                "seconds_min": round(min(samples), 6),
                "seconds_p50": round(_percentile(samples, 0.50), 6),
                "seconds_p95": round(_percentile(samples, 0.95), 6),
                "seconds_max": round(max(samples), 6),
                "peak_rss_growth_bytes": max(0, _peak_rss_bytes() - rss_before),
            })

    total_seconds = sum(durations)
    scans = len(durations)
    report = {
        "benchmark_version": "scanner-benchmark/1.0.0",
        "scanner": {"key": SCANNER_KEY, "version": SCANNER_VERSION},
        "corpus_cases": len(cases),
        "iterations_per_case": arguments.iterations,
        "seconds_p50": round(_percentile(durations, 0.50), 6),
        "seconds_p95": round(_percentile(durations, 0.95), 6),
        "seconds_p99": round(_percentile(durations, 0.99), 6),
        "seconds_max": round(max(durations), 6) if durations else 0.0,
        "peak_rss_bytes": _peak_rss_bytes(),
        "repositories_per_hour": round(scans / total_seconds * 3600, 2) if total_seconds else 0.0,
        "objectives": {
            "seconds_p95_limit": STANDARD_REPOSITORY_P95_SECONDS,
            "peak_rss_limit_bytes": PEAK_RSS_LIMIT_BYTES,
            "repositories_per_hour_minimum": MINIMUM_REPOSITORIES_PER_HOUR,
        },
        "per_case": per_case,
    }

    if arguments.output:
        arguments.output.parent.mkdir(parents=True, exist_ok=True)
        arguments.output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({key: report[key] for key in (
        "seconds_p50", "seconds_p95", "seconds_p99", "peak_rss_bytes", "repositories_per_hour",
    )}, indent=2))

    failures: list[str] = []
    if report["seconds_p95"] > STANDARD_REPOSITORY_P95_SECONDS:
        failures.append(
            f"p95 scan {report['seconds_p95']}s exceeds the {STANDARD_REPOSITORY_P95_SECONDS}s objective"
        )
    if report["peak_rss_bytes"] > PEAK_RSS_LIMIT_BYTES:
        failures.append(
            f"peak RSS {report['peak_rss_bytes']} exceeds the {PEAK_RSS_LIMIT_BYTES} byte objective"
        )
    if report["repositories_per_hour"] < MINIMUM_REPOSITORIES_PER_HOUR:
        failures.append(
            f"throughput {report['repositories_per_hour']}/hour is below the "
            f"{MINIMUM_REPOSITORIES_PER_HOUR}/hour objective"
        )

    if arguments.compare and arguments.compare.exists():
        baseline = json.loads(arguments.compare.read_text())
        limit = baseline["seconds_p95"] * REGRESSION_MARGIN
        # A baseline recorded on an idle machine can be microseconds; only compare once the
        # measurement is large enough for the ratio to mean anything.
        if baseline["seconds_p95"] > 0.05 and report["seconds_p95"] > limit:
            failures.append(
                f"p95 scan regressed from {baseline['seconds_p95']}s to {report['seconds_p95']}s"
            )

    for failure in failures:
        print(failure, file=sys.stderr)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
