"""The ontology registry must describe the vocabulary the product actually queries.

Migration 055 registered the AI supply-chain entity types and predicates in the database, but
`ontology.registry.json` — the document CONTRACTS.md names as the canonical vocabulary for
scanners, normalization, SQL seeds, projection, and the API — was never updated. The result was
an endpoint filtering on sixteen names absent from its own contract, which no test could catch
because nothing compared the two.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from app.estate_governance import _AI_PREDICATES, _AI_TYPES


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
CONTRACTS_DIR = Path(
    os.environ.get(
        "STACKGRAPH_CONTRACTS_DIR", REPOSITORY_ROOT / "stackgraph-foundation" / "contracts" / "v1",
    )
)
REGISTRY_PATH = CONTRACTS_DIR / "ontology.registry.json"


@pytest.fixture(scope="module")
def registry() -> dict:
    if not REGISTRY_PATH.exists():
        pytest.skip(f"ontology registry not available at {REGISTRY_PATH}")
    return json.loads(REGISTRY_PATH.read_text())


def test_every_queried_ai_entity_type_is_in_the_registry(registry) -> None:
    declared = {value for values in registry["namespaces"].values() for value in values}
    missing = sorted(_AI_TYPES - declared)
    assert not missing, (
        "the AI supply-chain read model filters on entity types absent from the ontology "
        f"registry, so they can never appear: {missing}"
    )


def test_every_queried_ai_predicate_is_in_the_registry(registry) -> None:
    missing = sorted(_AI_PREDICATES - set(registry["predicates"]))
    assert not missing, (
        "the AI supply-chain read model filters on predicates absent from the ontology "
        f"registry, so they can never appear: {missing}"
    )


def test_registry_predicates_all_declare_an_object_kind(registry) -> None:
    for predicate, definition in registry["predicates"].items():
        assert definition.get("object_kind") in {"ENTITY", "VALUE", "EITHER"}, predicate
