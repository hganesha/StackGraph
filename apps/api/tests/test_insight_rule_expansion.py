import asyncio
from datetime import UTC, datetime
from uuid import UUID

from app.deterministic_insights import RULE_CATALOG, _policies, _to_insight
from app.insight_rule_expansion import (
    DEFAULT_STRONG_COPYLEFT_LICENSES,
    DEFAULT_WEAK_COPYLEFT_LICENSES,
    expanded_rule_queries,
)


TENANT_ID = UUID("00000000-0000-4000-8000-000000000001")
FACT_ID = UUID("00000000-0000-4000-8000-000000000101")
SUBJECT_ID = UUID("00000000-0000-4000-8000-000000000102")
REPOSITORY_ID = UUID("00000000-0000-4000-8000-000000000103")


class EmptyPolicyDatabase:
    async def fetch_all(self, query, params=None, *, tenant_id=None):
        assert "deterministic_insight_rule_policy" in query
        return []


def test_expanded_catalog_registers_four_active_policy_governed_rules() -> None:
    expanded = {
        rule["key"]: rule for rule in RULE_CATALOG
        if rule["key"].startswith(("supplychain.", "oss.", "code."))
    }

    assert set(expanded) == {
        "supplychain.dependency-confusion",
        "oss.license-obligation",
        "code.cross-repository-clone",
        "code.vendored-third-party",
    }
    assert all(rule["readiness"] == "ACTIVE" for rule in expanded.values())
    assert all(rule["missing"] for rule in expanded.values())


def test_default_rule_configuration_is_available_without_stored_policy() -> None:
    policies = asyncio.run(_policies(EmptyPolicyDatabase(), TENANT_ID))

    assert policies["code.cross-repository-clone"]["configuration"]["minimum_lines"] == 6
    assert policies["code.cross-repository-clone"]["minimum_repositories"] == 2
    assert policies["code.vendored-third-party"]["configuration"][
        "minimum_vendored_units"
    ] == 1
    assert policies["oss.license-obligation"]["configuration"][
        "strong_copyleft_licenses"
    ] == list(DEFAULT_STRONG_COPYLEFT_LICENSES)
    assert policies["oss.license-obligation"]["configuration"][
        "weak_copyleft_licenses"
    ] == list(DEFAULT_WEAK_COPYLEFT_LICENSES)


def test_expanded_query_parameters_are_bounded_and_tenant_scoped() -> None:
    policies = asyncio.run(_policies(EmptyPolicyDatabase(), TENANT_ID))
    policies["code.cross-repository-clone"]["configuration"]["minimum_lines"] = -5
    policies["code.vendored-third-party"]["configuration"][
        "minimum_vendored_units"
    ] = 50000
    queries = {
        key: (sql, params)
        for key, sql, params in expanded_rule_queries(TENANT_ID, policies)
    }

    assert queries["supplychain.dependency-confusion"][1] == (TENANT_ID,)
    assert queries["oss.license-obligation"][1][0:2] == (TENANT_ID, TENANT_ID)
    assert len(queries["oss.license-obligation"][1]) == 4
    assert queries["code.cross-repository-clone"][1] == (TENANT_ID, 2)
    assert queries["code.vendored-third-party"][1] == (TENANT_ID, 1000)
    assert "resolution.tenant_id=%s" in queries["supplychain.dependency-confusion"][0]
    assert "unit.tenant_id=%s" in queries["code.cross-repository-clone"][0]
    assert "fact.predicate='DEPENDS_ON'" in queries["oss.license-obligation"][0]
    assert "registry.ecosystem" in queries["oss.license-obligation"][0]
    assert "current_capability_application_relationship" in queries["code.cross-repository-clone"][0]
    assert "NOT EXISTS" in queries["code.vendored-third-party"][0]
    assert "vendored_package_version" in queries["code.vendored-third-party"][0]


def test_expanded_insight_preserves_evidence_and_applies_coverage_penalty() -> None:
    row = {
        "rule_key": "code.vendored-third-party",
        "policy": {
            "enabled": True,
            "severity": "HIGH",
            "minimum_repositories": 1,
            "configuration": {"minimum_vendored_units": 1},
            "version": 0,
        },
        "subject_id": SUBJECT_ID,
        "subject_kind": "Repository",
        "subject_name": "billing-api",
        "subject_key": "github:repo:billing-api",
        "kind": "VENDORED_SOURCE_OUTSIDE_MANAGEMENT",
        "title": "billing-api contains vendored source",
        "summary": "1 repositories contain vendored source.",
        "present": 1,
        "referenced": 1,
        "reachable": 0,
        "runtime": 0,
        "deployed": 0,
        "applications": 1,
        "scope_ids": [REPOSITORY_ID],
        "repositories": [{
            "id": REPOSITORY_ID,
            "kind": "Repository",
            "name": "billing-api",
        }],
        "fact_ids": [FACT_ID],
        "detected_at": datetime(2026, 8, 22, tzinfo=UTC),
        "action": "INVESTIGATE",
        "recommendation_title": "Move vendored source under governance",
        "recommendation_rationale": "Establish origin before replacement.",
        "effort": "HIGH",
        "missing_inputs": ["Upstream origin is unknown."],
        "coverage_penalty": 2,
        "risk_bonus": 4,
    }

    insight = _to_insight(row)

    assert insight.kind == "VENDORED_SOURCE_OUTSIDE_MANAGEMENT"
    assert insight.supporting_fact_ids == [FACT_ID]
    assert insight.affected_repository_count == 1
    assert insight.summary == "1 repository contain vendored source."
    assert insight.evidence_coverage < 0.7
    assert "Upstream origin is unknown." in insight.missing_inputs
    assert insight.priority_score > 50
