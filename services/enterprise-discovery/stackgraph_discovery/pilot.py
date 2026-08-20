from __future__ import annotations

import argparse
import hashlib
import json
import statistics
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

from .repository_scanner import SCANNER_KEY, SCANNER_VERSION, scan_repository


DEFAULT_REPOSITORIES = 100


def run_pilot(repository_count: int = DEFAULT_REPOSITORIES) -> dict[str, object]:
    if repository_count < 100:
        raise ValueError("the pilot requires at least 100 repositories")
    started = time.perf_counter()
    durations: list[float] = []
    pass_a_durations: list[float] = []
    pass_b_durations: list[float] = []
    fact_count = 0
    finding_count = 0
    evidence_count = 0
    facts_without_evidence = 0
    complete_count = 0
    failures: list[dict[str, str]] = []
    first_five_seconds: float | None = None

    with tempfile.TemporaryDirectory(prefix="stackgraph-pilot-") as directory:
        root = Path(directory)
        for index in range(repository_count):
            repository = root / f"service-{index:03d}"
            _write_repository(repository, index)
            scan_started = time.perf_counter()
            try:
                result = scan_repository(_request(repository, index))
            except Exception as error:
                failures.append({"repository": repository.name, "error": type(error).__name__})
                continue
            durations.append(time.perf_counter() - scan_started)
            phase_timings = result["stats"].get("phase_timings_ms", {})
            pass_a_durations.append(float(phase_timings.get("pass_a_inventory", 0)) / 1000)
            pass_b_durations.append(float(phase_timings.get("pass_b_refinement", 0)) / 1000)
            complete_count += result["completeness"] == "COMPLETE"
            facts = result["facts"]
            fact_count += len(facts)
            findings = [
                fact for fact in facts
                if fact["predicate"] == "HAS_PROPERTY"
                and isinstance(fact.get("object_value"), dict)
                and fact["object_value"].get("finding_type")
            ]
            finding_count += len(findings)
            evidence_count += sum(len(fact.get("evidence", [])) for fact in facts)
            facts_without_evidence += sum(not fact.get("evidence") for fact in facts)
            if finding_count >= 5 and first_five_seconds is None:
                first_five_seconds = time.perf_counter() - started

    elapsed = time.perf_counter() - started
    p95 = _percentile(durations, 95)
    evidence_ratio = 1.0 if fact_count == 0 else (fact_count - facts_without_evidence) / fact_count
    targets = {
        "repository_count_at_least_100": repository_count >= 100,
        "all_scans_complete": complete_count == repository_count,
        "first_five_findings_under_20_minutes": first_five_seconds is not None and first_five_seconds < 1200,
        "p95_scan_under_2_seconds": p95 < 2.0,
        "evidence_coverage_at_least_99_percent": evidence_ratio >= 0.99,
        "zero_failures": not failures,
        "two_pass_metrics_present": (
            len(pass_a_durations) == repository_count
            and len(pass_b_durations) == repository_count
        ),
    }
    return {
        "schema_version": "1.0.0",
        "generated_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "workload": "synthetic-polyglot-deployment-fixture",
        "scanner": {"key": SCANNER_KEY, "version": SCANNER_VERSION},
        "repositories": repository_count,
        "complete_scans": complete_count,
        "facts": fact_count,
        "findings": finding_count,
        "evidence_items": evidence_count,
        "facts_with_evidence_ratio": round(evidence_ratio, 6),
        "time_to_first_five_findings_seconds": _rounded(first_five_seconds),
        "total_seconds": _rounded(elapsed),
        "per_repository_seconds": {
            "median": _rounded(statistics.median(durations) if durations else None),
            "p95": _rounded(p95),
            "max": _rounded(max(durations) if durations else None),
        },
        "scan_phases": {
            "pass_a": "inventory",
            "pass_b": "evidence_refinement",
            "execution": "sequential_per_repository; downstream intelligence remains asynchronous",
            "pass_a_p95_seconds": _rounded(_percentile(pass_a_durations, 95)),
            "pass_b_p95_seconds": _rounded(_percentile(pass_b_durations, 95)),
        },
        "failures": failures,
        "targets": targets,
        "passed": all(targets.values()),
        "limitations": [
            "This is a deterministic local scanner/load drill, not a claim about GitHub or provider quota latency.",
            "Live tenant, network enrichment, projection, and UI latency require a deployment-specific trace.",
        ],
    }


def _write_repository(root: Path, index: int) -> None:
    root.mkdir(parents=True)
    package = f"service-{index:03d}"
    (root / "package.json").write_text(json.dumps({
        "name": package,
        "version": "1.0.0",
        "dependencies": {"lodash": "^4.17.0", "express": "^5.1.0"},
    }), encoding="utf-8")
    (root / "package-lock.json").write_text(json.dumps({
        "lockfileVersion": 3,
        "packages": {
            "": {"dependencies": {"lodash": "^4.17.0", "express": "^5.1.0"}},
            "node_modules/lodash": {
                "version": "4.17.21",
                "resolved": "https://registry.npmjs.org/lodash/-/lodash-4.17.21.tgz",
                "integrity": "sha512-pilot",
            },
            "node_modules/express": {
                "version": "5.1.0",
                "resolved": "https://registry.npmjs.org/express/-/express-5.1.0.tgz",
                "integrity": "sha512-pilot",
            },
        },
    }), encoding="utf-8")
    (root / "index.ts").write_text(
        "import { get } from 'lodash';\nconsole.log(get({ready: true}, 'ready'));\n",
        encoding="utf-8",
    )
    (root / "Dockerfile").write_text(
        "FROM node:22-alpine\nWORKDIR /app\nCOPY . .\nCMD [\"node\", \"index.js\"]\n",
        encoding="utf-8",
    )
    (root / "compose.yaml").write_text(
        f"services:\n  app:\n    image: registry.example.test/{package}:1.0.0\n",
        encoding="utf-8",
    )
    (root / "deployment.yaml").write_text(
        "apiVersion: apps/v1\nkind: Deployment\nmetadata:\n  name: app\nspec:\n"
        "  template:\n    spec:\n      containers:\n        - name: app\n          image: registry.example.test/app:1.0.0\n",
        encoding="utf-8",
    )
    (root / "main.tf").write_text(
        'resource "aws_ecs_service" "app" {\n  name = "app"\n}\n',
        encoding="utf-8",
    )


def _request(root: Path, index: int) -> dict[str, object]:
    revision = hashlib.sha1(f"pilot-{index}".encode("utf-8"), usedforsecurity=False).hexdigest()
    digest = hashlib.sha256(f"snapshot-{index}".encode("utf-8")).hexdigest()
    return {
        "scanner_contract_version": "1.0.0",
        "run_id": str(uuid5(NAMESPACE_URL, f"stackgraph-pilot-run-{index}")),
        "tenant_key": "pilot-100",
        "target": {
            "provider": "github",
            "repository_id": str(10_000 + index),
            "canonical_key": f"github:repo:{10_000 + index}",
            "name": root.name,
            "default_branch": "main",
        },
        "snapshot": {
            "source_revision": revision,
            "checkout_root": str(root),
            "requested_at": "2026-08-20T12:00:00Z",
            "blob_uri": f"stackgraph-evidence://object/tenants/{'a' * 64}/sha256/{digest}",
            "content_hash": f"sha256:{digest}",
            "content_size_bytes": 4096,
        },
        "limits": {"max_files": 100, "max_bytes": 1_000_000, "deadline_seconds": 30},
    }


def _percentile(values: list[float], percentile: int) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, int((percentile / 100) * len(ordered) + 0.999999) - 1))
    return ordered[index]


def _rounded(value: float | None) -> float | None:
    return None if value is None else round(value, 6)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the deterministic StackGraph 100+ repository pilot")
    parser.add_argument("--repositories", type=int, default=DEFAULT_REPOSITORIES)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    report = run_pilot(args.repositories)
    rendered = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
