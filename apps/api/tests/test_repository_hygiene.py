import asyncio
from datetime import UTC, datetime
from uuid import UUID

from app.deterministic_insights import RULE_CATALOG, list_deterministic_insights
from app.repository_hygiene import repository_hygiene_queries


TENANT_ID = UUID("00000000-0000-4000-8000-000000000001")
REPOSITORY_ID = UUID("00000000-0000-4000-8000-000000000101")
FACT_ID = UUID("00000000-0000-4000-8000-000000000102")


class MissingReadmeDatabase:
    async def fetch_all(self, query, params=None, *, tenant_id=None):
        if "deterministic_insight_rule_policy" in query:
            return []
        if "MISSING_README" in query:
            return [{
                "subject_id": REPOSITORY_ID,
                "subject_kind": "Repository",
                "subject_name": "billing-api",
                "subject_key": "github:repo:billing-api",
                "kind": "MISSING_README",
                "title": "billing-api has no root README",
                "summary": "The complete repository scan did not find a root README file.",
                "present": 1,
                "referenced": 0,
                "reachable": 0,
                "runtime": 0,
                "deployed": 0,
                "applications": 1,
                "scope_ids": [REPOSITORY_ID],
                "repositories": [{
                    "id": REPOSITORY_ID,
                    "kind": "Repository",
                    "name": "billing-api",
                    "canonical_key": "github:repo:billing-api",
                }],
                "fact_ids": [FACT_ID],
                "detected_at": datetime(2026, 8, 24, tzinfo=UTC),
                "action": "INVESTIGATE",
                "recommendation_title": "Add a repository README",
                "recommendation_rationale": "Document the repository purpose.",
                "effort": "LOW",
                "missing_inputs": [],
                "coverage_penalty": 0,
            }]
        if "WITH repository AS" in query:
            return []
        raise AssertionError(f"unexpected query: {query[:80]}")


def test_catalog_registers_six_active_repository_hygiene_rules() -> None:
    rules = {
        rule["key"]: rule for rule in RULE_CATALOG
        if rule["key"].startswith(("repository.missing-", "dependency.missing-", "testing.missing-"))
    }

    assert set(rules) == {
        "repository.missing-readme",
        "repository.missing-license",
        "repository.missing-codeowners",
        "repository.missing-ci",
        "dependency.missing-lockfile",
        "testing.missing-tests",
    }
    assert all(rule["readiness"] == "ACTIVE" for rule in rules.values())
    assert all(rule["phase"] == 1 for rule in rules.values())


def test_queries_require_current_complete_repository_profile_evidence() -> None:
    queries = {
        key: (sql, params) for key, sql, params in repository_hygiene_queries(TENANT_ID)
    }

    assert len(queries) == 6
    for sql, params in queries.values():
        assert params == (TENANT_ID,)
        assert "snapshot.status='PUBLISHED'" in sql
        assert "snapshot.completeness='COMPLETE'" in sql
        assert "fact.system_to IS NULL" in sql
        assert "repository_profile" in sql
        assert "::boolean IS FALSE" in sql
    assert "dependency_lockfile'->>'applicable')::boolean IS TRUE" in queries[
        "dependency.missing-lockfile"
    ][0]
    assert "tests'->>'applicable')::boolean IS TRUE" in queries["testing.missing-tests"][0]


def test_missing_readme_row_flows_through_the_deterministic_insight_contract() -> None:
    result = asyncio.run(list_deterministic_insights(
        MissingReadmeDatabase(),
        tenant_id=TENANT_ID,
        rule_key="repository.missing-readme",
    ))

    assert result.summary.total == 1
    insight = result.insights[0]
    assert insight.kind == "MISSING_README"
    assert insight.subject.id == REPOSITORY_ID
    assert insight.supporting_fact_ids == [FACT_ID]
    assert insight.recommendation is not None
    assert insight.recommendation.estimated_effort == "LOW"
