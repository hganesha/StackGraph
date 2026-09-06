#!/usr/bin/env python3
"""Score the scanner against the golden repository corpus and emit a baseline artifact.

The Phase 2 plan's correctness objectives are stated as deltas — precision above 99%, no
regression beyond a quarter of a percentage point. A delta needs a stored baseline, so this
script writes one and can compare against it.

    scripts/golden_corpus_report.py --output artifacts/golden-corpus.json
    scripts/golden_corpus_report.py --compare artifacts/golden-corpus.json

`--compare` exits non-zero when precision or recall drops by more than the allowed margin, so
CI can fail on a correctness regression rather than on a changed fact count.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "services" / "enterprise-discovery"))
sys.path.insert(0, str(REPOSITORY_ROOT / "services" / "enterprise-discovery" / "tests"))

from golden_corpus import evaluate, load_cases, score  # noqa: E402

# §9.1: canonical entity precision must not regress by more than a quarter of a point.
REGRESSION_MARGIN = 0.0025


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, help="write the scored report to this path")
    parser.add_argument("--compare", type=Path, help="fail if the score regresses against this baseline")
    parser.add_argument("--quiet", action="store_true")
    arguments = parser.parse_args()

    with TemporaryDirectory() as workspace:
        results = [evaluate(case, Path(workspace)) for case in load_cases()]
    report = score(results)

    if arguments.output:
        arguments.output.parent.mkdir(parents=True, exist_ok=True)
        arguments.output.write_text(json.dumps(report, indent=2) + "\n")

    if not arguments.quiet:
        print(json.dumps({key: report[key] for key in (
            "cases", "cases_passed", "labelled_expectations", "labelled_false_positive_probes",
            "true_positives", "false_negatives", "false_positives", "recall", "precision",
        )}, indent=2))
        for case in report["per_case"]:
            if not case["passed"]:
                print(f"  FAIL {case['id']}", file=sys.stderr)
                for item in case["missing"]:
                    print(f"    missing: {item}", file=sys.stderr)
                for item in case["unexpected"]:
                    print(f"    false positive: {item}", file=sys.stderr)

    if arguments.compare:
        baseline = json.loads(arguments.compare.read_text())
        for metric in ("precision", "recall"):
            drop = baseline[metric] - report[metric]
            if drop > REGRESSION_MARGIN:
                print(
                    f"{metric} regressed by {drop:.4f} "
                    f"({baseline[metric]:.4f} -> {report[metric]:.4f}), "
                    f"more than the {REGRESSION_MARGIN} margin",
                    file=sys.stderr,
                )
                return 1

    return 0 if report["false_negatives"] == 0 and report["false_positives"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
