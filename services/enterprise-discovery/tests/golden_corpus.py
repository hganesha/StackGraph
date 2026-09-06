"""Evaluation harness for the versioned golden repository corpus.

The Phase 2 plan states correctness objectives — canonical entity precision above 99%, no
regression beyond a quarter of a percentage point, zero silent false positives — that are only
meaningful relative to a labelled corpus. This module is that corpus's reader and scorer.

Two labelled sets per case drive the score:

* `expect.facts` are facts the scanner must emit. A missing one is a false negative.
* `expect.absent_facts` are facts the scanner must not emit. These are curated false positives —
  a dependency belonging to a vendored package, a component the repository does not own, a
  neighbouring monorepo app dragged into a sibling's impact. A present one is a false positive.

Precision and recall are computed over that labelled set only. Unlabelled facts are neither
credited nor penalised, because nobody has reviewed them; the corpus grows by labelling more,
not by assuming silence means correctness.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping

from stackgraph_discovery.repository_scanner import scan_repository


CORPUS_ROOT = Path(__file__).resolve().parents[3] / "tests" / "fixtures" / "golden-repository"
PACKAGE_SCENARIO_ROOT = Path(__file__).resolve().parents[3] / "tests" / "fixtures" / "golden-package"

# Pinned so entity keys, idempotency keys, and fingerprints are byte-stable across runs.
CORPUS_REVISION = "a" * 40
CORPUS_REQUESTED_AT = "2026-08-19T14:00:00Z"
CORPUS_RUN_ID = "00000000-0000-4000-8000-000000000101"
CORPUS_REPOSITORY_KEY = "github:repo:1"


@dataclass(frozen=True)
class FactMatcher:
    """A subset match against one emitted fact.

    Every field left unset is a wildcard, so a matcher states exactly as much as the case
    author is willing to defend and no more.
    """

    predicate: str | None = None
    subject_type: str | None = None
    subject_key: str | None = None
    object_type: str | None = None
    object_key: str | None = None
    record_kind: str | None = None
    finding_type: str | None = None
    properties: Mapping[str, Any] = field(default_factory=dict)
    note: str | None = None

    @classmethod
    def from_json(cls, value: Mapping[str, Any]) -> "FactMatcher":
        return cls(
            predicate=value.get("predicate"),
            subject_type=value.get("subject_type"),
            subject_key=value.get("subject_key"),
            object_type=value.get("object_type"),
            object_key=value.get("object_key"),
            record_kind=value.get("record_kind"),
            finding_type=value.get("finding_type"),
            properties=value.get("properties") or {},
            note=value.get("note"),
        )

    def describe(self) -> str:
        parts = [
            f"{name}={value}"
            for name, value in (
                ("predicate", self.predicate),
                ("subject_type", self.subject_type),
                ("subject_key", self.subject_key),
                ("object_type", self.object_type),
                ("object_key", self.object_key),
                ("record_kind", self.record_kind),
                ("finding_type", self.finding_type),
            )
            if value is not None
        ]
        if self.properties:
            parts.append(f"properties={json.dumps(self.properties, sort_keys=True)}")
        return " ".join(parts) or "<any fact>"

    def matches(self, fact: Mapping[str, Any]) -> bool:
        subject = fact.get("subject") or {}
        object_entity = fact.get("object_entity") or {}
        object_value = fact.get("object_value")
        object_value = object_value if isinstance(object_value, Mapping) else {}
        if self.predicate is not None and fact.get("predicate") != self.predicate:
            return False
        if self.subject_type is not None and subject.get("type") != self.subject_type:
            return False
        if self.subject_key is not None and subject.get("key") != self.subject_key:
            return False
        if self.object_type is not None and object_entity.get("type") != self.object_type:
            return False
        if self.object_key is not None and object_entity.get("key") != self.object_key:
            return False
        if self.record_kind is not None and object_value.get("record_kind") != self.record_kind:
            return False
        if self.finding_type is not None and object_value.get("finding_type") != self.finding_type:
            return False
        return all(_contains(object_value.get(key), value) for key, value in self.properties.items())


def _contains(actual: Any, expected: Any) -> bool:
    """Subset comparison: mappings match on stated keys, lists on stated members."""
    if isinstance(expected, Mapping):
        if not isinstance(actual, Mapping):
            return False
        return all(_contains(actual.get(key), value) for key, value in expected.items())
    if isinstance(expected, list):
        if not isinstance(actual, list):
            return False
        return all(any(_contains(item, value) for item in actual) for value in expected)
    return actual == expected


@dataclass(frozen=True)
class GoldenCase:
    identifier: str
    title: str
    why: str
    root: Path
    limits: Mapping[str, int]
    expected_completeness: str
    expected_classifications: tuple[str, ...] | None
    expected_diagnostic_codes: tuple[str, ...]
    expected_facts: tuple[FactMatcher, ...]
    absent_facts: tuple[FactMatcher, ...]
    generate: Mapping[str, Any] | None

    def request(self, checkout_root: Path) -> dict[str, Any]:
        return {
            "scanner_contract_version": "1.0.0",
            "run_id": CORPUS_RUN_ID,
            "tenant_key": "golden",
            "target": {
                "provider": "github",
                "repository_id": "1",
                "canonical_key": CORPUS_REPOSITORY_KEY,
                "name": self.identifier,
                "default_branch": "main",
            },
            "snapshot": {
                "source_revision": CORPUS_REVISION,
                "checkout_root": str(checkout_root),
                "requested_at": CORPUS_REQUESTED_AT,
            },
            "limits": dict(self.limits),
        }


@dataclass(frozen=True)
class CaseResult:
    case: GoldenCase
    result: Mapping[str, Any]
    missing: tuple[FactMatcher, ...]
    unexpected: tuple[FactMatcher, ...]
    completeness_ok: bool
    classifications_ok: bool
    actual_classifications: tuple[str, ...]

    @property
    def true_positives(self) -> int:
        return len(self.case.expected_facts) - len(self.missing)

    @property
    def false_negatives(self) -> int:
        return len(self.missing)

    @property
    def false_positives(self) -> int:
        return len(self.unexpected)

    @property
    def passed(self) -> bool:
        return (
            not self.missing
            and not self.unexpected
            and self.completeness_ok
            and self.classifications_ok
        )


def load_cases(root: Path = CORPUS_ROOT) -> list[GoldenCase]:
    cases: list[GoldenCase] = []
    for manifest in sorted(root.glob("*/case.json")):
        document = json.loads(manifest.read_text())
        expect = document.get("expect") or {}
        classifications = expect.get("classifications")
        cases.append(GoldenCase(
            identifier=document["id"],
            title=document["title"],
            why=document["why"],
            root=manifest.parent / "repo",
            limits=document.get("limits") or {
                "max_files": 500, "max_bytes": 10_000_000, "deadline_seconds": 60,
            },
            expected_completeness=expect.get("completeness", "COMPLETE"),
            expected_classifications=(
                tuple(classifications) if classifications is not None else None
            ),
            expected_diagnostic_codes=tuple(expect.get("diagnostic_codes") or ()),
            expected_facts=tuple(
                FactMatcher.from_json(item) for item in expect.get("facts") or ()
            ),
            absent_facts=tuple(
                FactMatcher.from_json(item) for item in expect.get("absent_facts") or ()
            ),
            generate=document.get("generate"),
        ))
    if not cases:
        raise FileNotFoundError(f"no golden cases found under {root}")
    return cases


def materialize(case: GoldenCase, workspace: Path) -> Path:
    """Return the checkout root for a case, expanding any generated tree into `workspace`.

    Large-repository behaviour is a bounds property, not a content property, so the case
    declares the shape and the harness expands it. Committing ten thousand near-identical
    files would make the corpus expensive to review for no extra signal.
    """
    if not case.generate:
        return case.root
    checkout = workspace / case.identifier
    checkout.mkdir(parents=True, exist_ok=True)
    for source in sorted(case.root.rglob("*")):
        if not source.is_file():
            continue
        destination = checkout / source.relative_to(case.root)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(source.read_bytes())
    count = int(case.generate.get("source_files") or 0)
    directory = checkout / str(case.generate.get("directory") or "src/generated")
    directory.mkdir(parents=True, exist_ok=True)
    for index in range(count):
        (directory / f"module_{index:05d}.js").write_text(
            f"exports.value{index} = () => {index};\n"
        )
    return checkout


def evaluate(case: GoldenCase, workspace: Path) -> CaseResult:
    checkout = materialize(case, workspace)
    result = scan_repository(case.request(checkout))
    facts = list(result.get("facts") or ())
    missing = tuple(
        matcher for matcher in case.expected_facts
        if not any(matcher.matches(fact) for fact in facts)
    )
    unexpected = tuple(
        matcher for matcher in case.absent_facts
        if any(matcher.matches(fact) for fact in facts)
    )
    actual_classifications = tuple(sorted(_classifications(facts)))
    return CaseResult(
        case=case,
        result=result,
        missing=missing,
        unexpected=unexpected,
        completeness_ok=result.get("completeness") == case.expected_completeness,
        classifications_ok=(
            case.expected_classifications is None
            or actual_classifications == tuple(sorted(case.expected_classifications))
        ),
        actual_classifications=actual_classifications,
    )


def _classifications(facts: Iterable[Mapping[str, Any]]) -> set[str]:
    for fact in facts:
        value = fact.get("object_value")
        if isinstance(value, Mapping) and value.get("record_kind") == "repository_profile":
            return {
                str(item.get("classification"))
                for item in value.get("classifications") or ()
            }
    return set()


def score(results: Iterable[CaseResult]) -> dict[str, Any]:
    results = list(results)
    true_positives = sum(item.true_positives for item in results)
    false_negatives = sum(item.false_negatives for item in results)
    false_positives = sum(item.false_positives for item in results)
    labelled = true_positives + false_negatives
    return {
        "corpus_version": "golden-repository/1.0.0",
        "scanner_contract_version": "1.0.0",
        "cases": len(results),
        "cases_passed": sum(1 for item in results if item.passed),
        "labelled_expectations": labelled,
        "labelled_false_positive_probes": sum(len(item.case.absent_facts) for item in results),
        "true_positives": true_positives,
        "false_negatives": false_negatives,
        "false_positives": false_positives,
        "recall": round(true_positives / labelled, 6) if labelled else 1.0,
        "precision": (
            round(true_positives / (true_positives + false_positives), 6)
            if true_positives + false_positives
            else 1.0
        ),
        "per_case": [
            {
                "id": item.case.identifier,
                "passed": item.passed,
                "true_positives": item.true_positives,
                "false_negatives": item.false_negatives,
                "false_positives": item.false_positives,
                "completeness": item.result.get("completeness"),
                "classifications": list(item.actual_classifications),
                "facts_emitted": len(item.result.get("facts") or ()),
                "missing": [matcher.describe() for matcher in item.missing],
                "unexpected": [matcher.describe() for matcher in item.unexpected],
            }
            for item in results
        ],
    }
