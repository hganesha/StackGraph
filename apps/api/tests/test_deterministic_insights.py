from datetime import UTC, datetime
from uuid import UUID

from app.deterministic_insights import METHOD_VERSION, RULE_CATALOG, _to_insight


def _row(*, severity: str = "HIGH", policy_version: int = 2):
    return {
        "rule_key": "dependency.deprecated",
        "policy": {
            "enabled": True,
            "severity": severity,
            "minimum_repositories": 1,
            "configuration": {},
            "version": policy_version,
        },
        "subject_id": UUID("00000000-0000-4000-8000-000000000100"),
        "subject_kind": "PackageVersion",
        "subject_name": "request 2.88.2",
        "subject_key": "pkg:npm/request@2.88.2",
        "kind": "DEPRECATED_DEPENDENCY",
        "title": "request 2.88.2 is deprecated",
        "summary": "Two repositories resolve the deprecated version.",
        "present": 2,
        "referenced": 1,
        "reachable": 1,
        "runtime": 0,
        "deployed": 1,
        "applications": 1,
        "scope_ids": [UUID("00000000-0000-4000-8000-000000000200")],
        "repositories": [
            {
                "id": "00000000-0000-4000-8000-000000000300",
                "kind": "Repository",
                "name": "billing-api",
            },
        ],
        "fact_ids": [UUID("00000000-0000-4000-8000-000000000400")],
        "detected_at": datetime(2026, 8, 21, tzinfo=UTC),
        "action": "UPGRADE",
        "recommendation_title": "Move off the deprecated version",
        "recommendation_rationale": "Select an eligible replacement.",
        "effort": "MEDIUM",
        "missing_inputs": [],
    }


def test_rule_catalog_exposes_current_two_phase_scope_and_blocks_unready_rules() -> None:
    assert {rule["phase"] for rule in RULE_CATALOG} == {1, 2}
    assert all(rule["readiness"] == "ACTIVE" for rule in RULE_CATALOG if rule["phase"] == 1)
    assert all(rule["missing"] for rule in RULE_CATALOG if rule["readiness"] == "NEEDS_DATA")


def test_insight_identity_is_stable_and_policy_changes_are_fingerprinted() -> None:
    first = _to_insight(_row())
    repeated = _to_insight(_row())
    changed = _to_insight(_row(policy_version=3))

    assert first.id == repeated.id
    assert first.input_fingerprint == repeated.input_fingerprint
    assert changed.id != first.id
    assert changed.input_fingerprint != first.input_fingerprint
    assert first.rule_version == METHOD_VERSION


def test_priority_and_evidence_coverage_are_separate_outputs() -> None:
    high = _to_insight(_row(severity="HIGH"))
    medium = _to_insight(_row(severity="MEDIUM"))

    assert high.priority_score > medium.priority_score
    assert high.evidence_coverage == medium.evidence_coverage
    assert high.stages.production == 0
    assert high.stages.externally_exposed == 0
    assert high.stages.business_critical is None
    assert "Live deployment and runtime ingress status are not observed; only code declarations are evaluated." in high.missing_inputs
    assert high.supporting_fact_ids


def test_phase_two_context_raises_priority_without_claiming_live_deployment() -> None:
    repository_id = UUID("00000000-0000-4000-8000-000000000300")
    contextual = _to_insight(
        _row(),
        phase_two_context={
            repository_id: {
                "business_criticality": 5,
                "code_production": True,
                "code_external_exposure": True,
            },
        },
    )
    baseline = _to_insight(_row())

    assert contextual.stages.production == 1
    assert contextual.stages.externally_exposed == 1
    assert contextual.stages.business_critical == 1
    assert contextual.priority_score > baseline.priority_score
