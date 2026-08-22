import asyncio
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import patch
from uuid import UUID

from app.enterprise_posture_insights import (
    ASSURANCE_COVERAGE,
    BUSINESS_DARK_CAPABILITY,
    DECISION_LAG,
    POSTURE_INSIGHT_REPORTS,
    TECHNOLOGY_INTRODUCTION,
    assurance_coverage,
    assurance_report_presentation,
    business_dark_capability,
    decision_lag,
    match_posture_question,
    posture_report_readiness,
    technology_introduction,
)
from app.models import AskRequest, AskResponse
from app.read_models import ReadModelStore


TENANT = UUID("00000000-0000-4000-8000-000000000001")
NOW = datetime(2026, 8, 22, 9, 0, tzinfo=UTC)


class QueryStub:
    """Return a canned payload and record the SQL each report actually issued."""

    def __init__(self, one: dict[str, Any] | None = None, all_rows: list[dict[str, Any]] | None = None) -> None:
        self.one = one
        self.all_rows = all_rows or []
        self.queries: list[str] = []
        self.params: list[Any] = []

    async def fetch_one(self, query, params=None, *, tenant_id=None):
        self.queries.append(query)
        self.params.append(params)
        return self.one

    async def fetch_all(self, query, params=None, *, tenant_id=None):
        self.queries.append(query)
        self.params.append(params)
        return self.all_rows


def _coverage_counters(**overrides: int | str) -> dict[str, Any]:
    counters: dict[str, Any] = {
        "repositories": 4, "fresh_repositories": 4,
        "ecosystem_supported_repositories": 4, "available_repositories": 4,
        "covered_repositories": 4, "facts": 100, "evidenced_facts": 100,
        "connectors": 2, "healthy_connectors": 2,
        "source_snapshotted_repositories": 4, "open_dead_letters": 0,
        "quota_providers": 2, "healthy_quota_providers": 2,
        "unsupported_ecosystems": "", "analyzable_ecosystems": "NPM",
    }
    counters.update(overrides)
    return counters


# --- report catalogue -------------------------------------------------------

def test_posture_reports_use_the_frozen_report_contract() -> None:
    categories = {"ENTERPRISE_RISK", "TECHNOLOGY_RATIONALIZATION", "PORTFOLIO_DECISIONS"}
    statuses = {"ACTION_REQUIRED", "WATCH", "HEALTHY", "WAITING_FOR_DATA"}
    assert [definition["key"] for definition in POSTURE_INSIGHT_REPORTS] == [
        ASSURANCE_COVERAGE, TECHNOLOGY_INTRODUCTION, BUSINESS_DARK_CAPABILITY, DECISION_LAG,
    ]
    for definition in POSTURE_INSIGHT_REPORTS:
        assert definition["category"] in categories
        assert definition["populated_status"] in statuses


def test_posture_questions_route_without_capturing_existing_reports() -> None:
    routed = {
        definition["question"]: match_posture_question(definition["question"].lower())
        for definition in POSTURE_INSIGHT_REPORTS
    }
    assert routed == {
        definition["question"]: definition["key"] for definition in POSTURE_INSIGHT_REPORTS
    }
    # Questions already owned by the Phase 1 enterprise reports must not be stolen.
    for question in (
        "show me the top 20 dependencies representing systemic enterprise risk.",
        "which vulnerabilities are actually reachable in production tier-1 applications?",
        "where have teams independently implemented the same capability?",
        "which package categories have the most unnecessary technology diversity?",
        "which unsupported dependencies block our node/python/.net modernization?",
        "what are our best application retirement/consolidation candidates?",
    ):
        assert match_posture_question(question) is None


# --- H1 ---------------------------------------------------------------------

def test_assurance_coverage_scores_every_scan_dimension_separately() -> None:
    database = QueryStub(one=_coverage_counters(
        fresh_repositories=3, ecosystem_supported_repositories=2, available_repositories=3,
        covered_repositories=2, evidenced_facts=90, healthy_connectors=1,
        unsupported_ecosystems="CARGO, MAVEN",
    ))
    result = asyncio.run(assurance_coverage(database, tenant_id=TENANT))

    assert result.result_kind == "TABLE"
    # No fact backs an operational scan, so nothing is cited.
    assert result.citations == []
    dimensions = [row["dimension"] for row in result.rows]
    assert dimensions == [
        "Analytically covered estate", "Scan freshness", "Analyzable ecosystems",
        "Evidence completeness", "Connector health", "Repository availability",
        "Published source snapshots", "Dead-letter backlog", "Connector quota",
    ]
    by_dimension = {row["dimension"]: row for row in result.rows}
    assert by_dimension["Analytically covered estate"]["coverage_percent"] == 50
    assert by_dimension["Scan freshness"]["status"] == "PARTIAL"
    # Ecosystems the estate cannot analyze are separated from an ordinary gap.
    assert by_dimension["Analyzable ecosystems"]["status"] == "UNSUPPORTED"
    assert "CARGO, MAVEN" in by_dimension["Analyzable ecosystems"]["detail"]
    assert by_dimension["Evidence completeness"]["scope"] == "Current facts"
    assert by_dimension["Evidence completeness"]["covered"] == 90
    assert by_dimension["Connector health"]["covered"] == 1
    assert by_dimension["Repository availability"]["in_scope"] == 4
    assert by_dimension["Published source snapshots"]["covered"] == 4
    assert by_dimension["Dead-letter backlog"]["status"] == "COVERED"
    assert by_dimension["Connector quota"]["covered"] == 2
    assert "source_snapshot" in database.queries[0]
    assert "dead_letter" in database.queries[0]
    assert "connector_quota" in database.queries[0]


def test_assurance_coverage_reports_no_rows_before_the_first_repository() -> None:
    result = asyncio.run(assurance_coverage(
        QueryStub(one=_coverage_counters(repositories=0, covered_repositories=0)),
        tenant_id=TENANT,
    ))
    assert result.rows == []
    assert "cannot be scored" in result.text


def test_assurance_presentation_separates_healthy_from_actionable_and_unsupported() -> None:
    healthy = [
        {"dimension": "Analytically covered estate", "coverage_percent": 100, "status": "COVERED"},
        {"dimension": "Scan freshness", "status": "COVERED"},
        {"dimension": "Connector health", "status": "COVERED"},
    ]
    assert assurance_report_presentation(healthy) == ("100%", "HEALTHY")

    unsupported = [
        {"dimension": "Analytically covered estate", "coverage_percent": 60, "status": "PARTIAL"},
        {"dimension": "Analyzable ecosystems", "status": "UNSUPPORTED"},
    ]
    assert assurance_report_presentation(unsupported) == ("60%", "WATCH")

    failing = [
        {"dimension": "Analytically covered estate", "coverage_percent": 25, "status": "PARTIAL"},
        {"dimension": "Analyzable ecosystems", "status": "UNSUPPORTED"},
        {"dimension": "Connector health", "status": "GAP"},
    ]
    assert assurance_report_presentation(failing) == ("25%", "ACTION_REQUIRED")

    assert assurance_report_presentation([]) is None


# --- C1 ---------------------------------------------------------------------

def test_technology_introduction_attributes_the_earliest_repository_and_evidence() -> None:
    fact_id = UUID("00000000-0000-4000-8000-0000000000c1")
    database = QueryStub(all_rows=[{
        "technology": "fastify", "technology_kind": "PackageVersion",
        "repository": "Checkout API", "fact_id": fact_id,
        "first_seen_at": NOW - timedelta(days=12),
        "evidence_observed_at": NOW - timedelta(days=12, hours=2),
        "repositories": 3, "total_count": 73,
    }])
    result = asyncio.run(technology_introduction(database, tenant_id=TENANT))

    assert result.rows == [{
        "technology": "fastify", "kind": "PackageVersion",
        "first_repository": "Checkout API",
        "first_seen_at": (NOW - timedelta(days=12)).isoformat(),
        "evidence_observed_at": (NOW - timedelta(days=12, hours=2)).isoformat(),
        "repositories": 3, "total_count": 73,
    }]
    assert [citation.fact_id for citation in result.citations] == [fact_id]
    assert database.params[0]["window_days"] == 90
    assert "technology.first_seen_at" in database.queries[0]
    assert "fact.system_to IS NULL" in database.queries[0]
    assert "count(*) OVER()" in database.queries[0]
    assert "73 technologies" in result.text


def test_technology_introduction_reports_a_quiet_window_as_an_empty_table() -> None:
    result = asyncio.run(technology_introduction(QueryStub(), tenant_id=TENANT))
    assert result.rows == []
    assert result.citations == []
    assert "90 days" in result.text


# --- G1 ---------------------------------------------------------------------

def test_business_dark_capability_carries_map_context_without_inventing_citations() -> None:
    database = QueryStub(all_rows=[{
        "business_map_key": "porter-2026", "business_map": "Enterprise value chain",
        "lane": "Operations",
        "business_function": "Fulfilment", "business_process": "Order routing",
        "capability_key": "order-routing", "capability": "Order routing",
        "criticality": 5, "owner": None, "maturity": 2, "total_count": 81,
    }])
    result = asyncio.run(business_dark_capability(database, tenant_id=TENANT))

    assert result.citations == []
    assert result.rows == [{
        "capability": "Order routing", "criticality": 5, "maturity": 2,
        "business_map": "Enterprise value chain", "lane": "Operations",
        "business_function": "Fulfilment", "business_process": "Order routing",
        "owner": "unassigned", "business_map_key": "porter-2026",
        "capability_key": "order-routing", "total_count": 81,
    }]
    query = database.queries[0]
    # Every governed catalog capability is evaluated, including capabilities
    # that have not yet been projected to a graph entity or map placement.
    assert "map.status='ACTIVE'" in query
    assert "LEFT JOIN LATERAL" in query
    assert "capability.entity_id IS NOT NULL" not in query
    assert "count(*) OVER()" in query
    assert "business_map_application_assignment" in query
    assert database.params[0]["minimum_criticality"] == 4


def test_business_dark_capability_reports_a_fully_covered_map_as_empty() -> None:
    result = asyncio.run(business_dark_capability(QueryStub(), tenant_id=TENANT))
    assert result.rows == []
    assert "has at least one application" in result.text


# --- C3 ---------------------------------------------------------------------

def test_decision_lag_requires_acceptance_elapsed_time_and_a_live_condition() -> None:
    fact_id = UUID("00000000-0000-4000-8000-0000000000c3")
    accepted_at = NOW - timedelta(days=46)
    database = QueryStub(all_rows=[{
        "title": "Consolidate HTTP clients", "action": "CONSOLIDATE",
        "objective": "REDUCE_DUPLICATION", "estimated_effort": "MEDIUM",
        "supporting_fact_ids": [fact_id, fact_id],
        "repository": "Checkout API", "accepted_at": accepted_at,
        "days_since_acceptance": 46,
    }])
    result = asyncio.run(decision_lag(database, tenant_id=TENANT))

    assert result.rows == [{
        "decision": "Consolidate HTTP clients", "action": "CONSOLIDATE",
        "repository": "Checkout API", "accepted_at": accepted_at.isoformat(),
        "days_since_acceptance": 46, "estimated_effort": "MEDIUM",
        "objective": "REDUCE_DUPLICATION",
    }]
    assert [citation.fact_id for citation in result.citations] == [fact_id]
    query = database.queries[0]
    assert "recommendation.review_state='ACCEPTED'" in query
    assert "review.decision='ACCEPT'" in query
    assert "recommendation.stale_at IS NULL" in query
    assert "modernization_validation_outcome" in query
    assert "fact.system_to IS NULL" in query
    assert "current_supporting_fact_ids" in query
    assert database.params[0]["threshold_days"] == 30


def test_decision_lag_reports_a_clear_backlog_as_empty() -> None:
    result = asyncio.run(decision_lag(QueryStub(), tenant_id=TENANT))
    assert result.rows == []
    assert result.citations == []


# --- readiness and gallery wiring ------------------------------------------

def test_posture_readiness_separates_a_defensible_zero_from_missing_state() -> None:
    ready = asyncio.run(posture_report_readiness(QueryStub(one={
        "estate_observed": True, "technology_observed": True,
        "critical_capability_governed": False, "decision_accepted": True,
    }), tenant_id=TENANT))
    assert ready == {
        ASSURANCE_COVERAGE: True, TECHNOLOGY_INTRODUCTION: True,
        BUSINESS_DARK_CAPABILITY: False, DECISION_LAG: True,
    }
    assert asyncio.run(posture_report_readiness(QueryStub(one=None), tenant_id=TENANT)) == {
        ASSURANCE_COVERAGE: False, TECHNOLOGY_INTRODUCTION: False,
        BUSINESS_DARK_CAPABILITY: False, DECISION_LAG: False,
    }


class GalleryDatabaseStub:
    """Readiness is satisfied so the posture cards are scored, not parked."""

    async def fetch_one(self, query, params=None, *, tenant_id=None):
        if "estate_observed" in query:
            return {
                "estate_observed": True, "technology_observed": True,
                "critical_capability_governed": True, "decision_accepted": True,
            }
        return {}

    async def fetch_all(self, query, params=None, *, tenant_id=None):
        return []


def test_posture_reports_render_in_the_existing_gallery_without_ai() -> None:
    coverage_rows = [
        {"dimension": "Analytically covered estate", "coverage_percent": 75, "status": "PARTIAL"},
        {"dimension": "Scan freshness", "status": "COVERED"},
        {"dimension": "Analyzable ecosystems", "status": "UNSUPPORTED"},
        {"dimension": "Evidence completeness", "status": "COVERED"},
        {"dimension": "Connector health", "status": "COVERED"},
        {"dimension": "Repository availability", "status": "COVERED"},
    ]

    async def deterministic_ask(self, request: AskRequest, *, tenant_id=None) -> AskResponse:
        rows: list[dict[str, Any]] = []
        if "analytically covered" in request.question.lower():
            rows = coverage_rows
        elif "no application behind them" in request.question.lower():
            rows = [{"capability": "Order routing", "criticality": 5}]
        elif "accepted decisions" in request.question.lower():
            rows = [{"decision": "Consolidate HTTP clients", "days_since_acceptance": 46}]
        return AskResponse(
            text=f"Deterministic result for {request.question}",
            citations=[], result_kind="TABLE", rows=rows,
        )

    store = ReadModelStore(GalleryDatabaseStub())
    with patch.object(ReadModelStore, "ask", deterministic_ask):
        result = asyncio.run(store.enterprise_insight_reports(tenant_id=TENANT))

    reports = {report.key: report for report in result.reports}
    assert set(reports) >= {
        ASSURANCE_COVERAGE, TECHNOLOGY_INTRODUCTION, BUSINESS_DARK_CAPABILITY, DECISION_LAG,
    }
    assert reports[ASSURANCE_COVERAGE].metric_value == "75%"
    assert reports[ASSURANCE_COVERAGE].status == "WATCH"
    # An empty result with the underlying state present is a healthy zero.
    assert reports[TECHNOLOGY_INTRODUCTION].status == "HEALTHY"
    assert reports[TECHNOLOGY_INTRODUCTION].metric_value == "0"
    assert reports[BUSINESS_DARK_CAPABILITY].status == "ACTION_REQUIRED"
    assert reports[DECISION_LAG].metric_value == "46"
    assert all(reports[key].answerable for key in (
        ASSURANCE_COVERAGE, TECHNOLOGY_INTRODUCTION, BUSINESS_DARK_CAPABILITY, DECISION_LAG,
    ))


def test_ask_dispatches_posture_questions_deterministically() -> None:
    captured: list[str] = []

    async def fake_answer(database, key, *, tenant_id=None):
        captured.append(key)
        return AskResponse(text="ok", citations=[], result_kind="TABLE", rows=[])

    store = ReadModelStore(GalleryDatabaseStub())
    with patch("app.read_models.answer_posture_report", fake_answer):
        for definition in POSTURE_INSIGHT_REPORTS:
            asyncio.run(store.ask(
                AskRequest(question=definition["question"]), tenant_id=TENANT,
            ))
    assert captured == [definition["key"] for definition in POSTURE_INSIGHT_REPORTS]
