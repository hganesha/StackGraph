import asyncio
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

import pytest

from app.errors import APIError
from app.read_models import (
    ReadModelStore,
    _confidence_label,
    _decode_cursor,
    _encode_cursor,
    _group_application_technologies,
)


NOW = datetime(2026, 8, 19, 14, 10, tzinfo=UTC)


class EstateDatabaseStub:
    def __init__(self) -> None:
        self.queries: list[str] = []

    async def fetch_one(self, query, params=None, *, tenant_id=None):
        self.queries.append(query)
        if "evidence_ratio" in query:
            return {"repositories_total": 2, "repositories_scanned": 2, "evidence_ratio": 1}
        return {"applications": 2, "repositories": 2, "services": 0, "technologies": 1}

    async def fetch_all(self, query, params=None, *, tenant_id=None):
        self.queries.append(query)
        if "GROUP BY 1 ORDER BY 1" in query or "WITH matched AS" in query:
            return []
        if "FROM entity e" in query and "priority_score" in query:
            return [
                {
                    "id": UUID("00000000-0000-4000-8000-000000000201"),
                    "namespace": "ENTERPRISE",
                    "entity_type": "Application",
                    "name": "Billing API",
                    "properties": {},
                    "observed_at": NOW,
                    "priority_score": Decimal("81"),
                    "priority_confidence": Decimal("0.91"),
                    "priority_method": "priority-v1",
                    "viability_score": None,
                },
                {
                    "id": UUID("00000000-0000-4000-8000-000000000220"),
                    "namespace": "ENTERPRISE",
                    "entity_type": "Application",
                    "name": "Catalog API",
                    "properties": {},
                    "observed_at": NOW,
                    "priority_score": Decimal("70"),
                    "priority_confidence": Decimal("0.75"),
                    "priority_method": "priority-v1",
                    "viability_score": None,
                },
            ]
        raise AssertionError(f"unexpected query: {query}")


def test_confidence_labels_use_frozen_contract_boundaries() -> None:
    assert _confidence_label(0.8499) == "MEDIUM"
    assert _confidence_label(0.85) == "HIGH"
    assert _confidence_label(0.5999) == "LOW"
    assert _confidence_label(0.60) == "MEDIUM"


def test_application_technologies_group_by_catalog_domain_and_capability() -> None:
    usage_fact = UUID("00000000-0000-4000-8000-000000000301")
    classification_fact = UUID("00000000-0000-4000-8000-000000000302")
    catalog_fact = UUID("00000000-0000-4000-8000-000000000304")
    react_package_id = UUID("00000000-0000-4000-8000-000000000204")
    unknown_package_id = UUID("00000000-0000-4000-8000-000000000205")
    react_catalog_id = UUID("00000000-0000-4000-8000-000000000206")
    technology_rows = [
        {
            "id": react_package_id,
            "namespace": "TECHNOLOGY",
            "entity_type": "PackageVersion",
            "canonical_key": "pkg:npm/react@19.1.1",
            "name": "react 19.1.1",
            "properties": {"catalog_metadata": {"description": "Interactive UI components."}},
            "usage_fact_ids": [usage_fact],
            "usage_confidence": Decimal("1.0"),
        },
        {
            "id": unknown_package_id,
            "namespace": "TECHNOLOGY",
            "entity_type": "PackageVersion",
            "canonical_key": "pkg:npm/unknown-package@1.0.0",
            "name": "unknown-package 1.0.0",
            "properties": {},
            "usage_fact_ids": [UUID("00000000-0000-4000-8000-000000000303")],
            "usage_confidence": Decimal("0.9"),
        },
    ]
    catalog_rows = [{
        "id": react_catalog_id,
        "namespace": "TECHNOLOGY",
        "entity_type": "Technology",
        "canonical_key": "stackgraph:technology:react",
        "name": "React",
        "properties": {
            "domain_id": "frontend",
            "domain_name": "Frontend",
            "category_id": "ui-rendering-reactivity",
            "category_name": "UI rendering & reactivity",
            "catalog_lookup_keys": ["react"],
        },
        "capability_id": UUID("00000000-0000-4000-8000-000000000207"),
        "capability_key": "ui-rendering",
        "capability_name": "UI rendering",
        "capability_summary": "Turn application state into interactive UI.",
        "catalog_fact_id": catalog_fact,
        "classification_fact_id": classification_fact,
        "classification_confidence": Decimal("0.95"),
    }]

    groups = _group_application_technologies(technology_rows, catalog_rows)

    assert [group.domain.key for group in groups] == ["frontend", "unclassified"]
    frontend = groups[0].functions[0]
    assert frontend.function.key == "ui-rendering"
    assert frontend.technologies[0].classification == "CATALOG_MATCH"
    assert frontend.technologies[0].confidence == pytest.approx(0.85)
    assert frontend.technologies[0].technology.summary == "Interactive UI components."
    assert {citation.fact_id for citation in frontend.technologies[0].citations} == {
        usage_fact,
        classification_fact,
        catalog_fact,
    }
    unknown = groups[1].functions[0].technologies[0]
    assert unknown.classification == "UNCLASSIFIED"
    assert unknown.confidence == 0
    assert unknown.category is None


def test_cursor_is_typed_and_rejects_cross_endpoint_reuse() -> None:
    cursor = _encode_cursor(
        "estate", score="81", name="Billing API",
        id="00000000-0000-4000-8000-000000000201",
    )

    assert _decode_cursor(cursor, "estate")["score"] == "81"
    with pytest.raises(APIError) as raised:
        _decode_cursor(cursor, "modernization")
    assert raised.value.code == "INVALID_CURSOR"


def test_estate_pagination_uses_constant_query_count_and_keyset_cursor() -> None:
    database = EstateDatabaseStub()
    result = asyncio.run(ReadModelStore(database).estate_summary(
        tenant_id=None, cursor=None, limit=1,
    ))

    assert result.page_info is not None
    assert result.page_info.has_next_page
    assert result.page_info.next_cursor is not None
    cursor = _decode_cursor(result.page_info.next_cursor, "estate")
    assert cursor == {
        "v": 1,
        "kind": "estate",
        "score": "81",
        "name": "Billing API",
        "id": "00000000-0000-4000-8000-000000000201",
    }
    assert len(database.queries) == 5
    assert all("OFFSET" not in query.upper() for query in database.queries)
