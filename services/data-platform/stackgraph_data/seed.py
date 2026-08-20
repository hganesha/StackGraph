from __future__ import annotations

import argparse
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import UUID

import psycopg
from psycopg import Connection
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from stackgraph_data.catalog import Catalog, load_catalog, sha256_key


EXTRACTOR_KEY = "foundation-curated-seed"
EXTRACTOR_VERSION = "1.0.0"


@dataclass(frozen=True, slots=True)
class SeedResult:
    seed_id: str
    seed_version: str
    replayed: bool
    technology_count: int
    capability_count: int
    relationship_count: int
    assessment_count: int
    fact_count: int

    def as_dict(self) -> dict[str, str | bool | int]:
        return {
            "seed_id": self.seed_id,
            "seed_version": self.seed_version,
            "replayed": self.replayed,
            "technology_count": self.technology_count,
            "capability_count": self.capability_count,
            "relationship_count": self.relationship_count,
            "assessment_count": self.assessment_count,
            "fact_count": self.fact_count,
        }


class CatalogSeeder:
    def __init__(self, connection: Connection[dict[str, Any]], catalog: Catalog) -> None:
        self.connection = connection
        self.catalog = catalog
        self.source_system_id: UUID | None = None
        self.target_id: UUID | None = None
        self.run_id: UUID | None = None
        self.snapshot_id: UUID | None = None
        self.artifact_id: UUID | None = None
        self.entities: dict[str, UUID] = {}
        self.fact_count = 0

    def run(self) -> SeedResult:
        self.source_system_id = self._upsert_source_system()
        self.target_id = self._upsert_target()

        if self._published_snapshot_exists():
            return self._result(replayed=True)

        self.run_id = self._create_run()
        self.artifact_id = self._upsert_source_artifact()
        self.snapshot_id = self._create_snapshot()
        self._upsert_entities()
        self._insert_entity_property_facts()
        self._insert_relationship_facts()
        self._insert_assessments()
        self.connection.execute("SELECT publish_source_snapshot(%s)", (self.snapshot_id,))
        self._complete_run()
        return self._result(replayed=False)

    def _upsert_source_system(self) -> UUID:
        row = self.connection.execute(
            """
            INSERT INTO source_system (tenant_id, source_key, kind, metadata)
            VALUES (NULL, %s, 'CURATED', %s)
            ON CONFLICT (tenant_id, source_key) DO UPDATE
            SET kind = EXCLUDED.kind, metadata = EXCLUDED.metadata
            RETURNING id
            """,
            (
                self.catalog.seed_id,
                Jsonb(
                    {
                        "seed_version": self.catalog.seed_version,
                        "original_source_file": self.catalog.manifest["source_file"],
                        "original_source_sha256": self.catalog.manifest["source_sha256"],
                    }
                ),
            ),
        ).fetchone()
        assert row is not None
        return row["id"]

    def _upsert_target(self) -> UUID:
        row = self.connection.execute(
            """
            INSERT INTO ingest_target (
                tenant_id, source_system_id, target_kind, target_key, priority,
                enabled, refresh_policy, desired_source_revision
            )
            VALUES (NULL, %s, 'CURATED_SEED', %s, 'COLD', true, %s, %s)
            ON CONFLICT (tenant_id, source_system_id, target_kind, target_key) DO UPDATE
            SET desired_source_revision = EXCLUDED.desired_source_revision,
                refresh_policy = EXCLUDED.refresh_policy,
                updated_at = now()
            RETURNING id
            """,
            (
                self.source_system_id,
                self.catalog.seed_id,
                Jsonb({"mode": "versioned_manual"}),
                self.catalog.seed_version,
            ),
        ).fetchone()
        assert row is not None
        return row["id"]

    def _published_snapshot_exists(self) -> bool:
        row = self.connection.execute(
            """
            SELECT id
            FROM source_snapshot
            WHERE ingest_target_id = %s
              AND source_revision = %s
              AND extractor_key = %s
              AND extractor_version = %s
              AND status = 'PUBLISHED'
            """,
            (
                self.target_id,
                self.catalog.seed_version,
                EXTRACTOR_KEY,
                EXTRACTOR_VERSION,
            ),
        ).fetchone()
        return row is not None

    def _create_run(self) -> UUID:
        row = self.connection.execute(
            """
            INSERT INTO ingest_run (
                tenant_id, ingest_target_id, trigger_kind, requested_source_revision,
                status, completeness, started_at
            )
            VALUES (NULL, %s, 'MANUAL', %s, 'RUNNING', 'COMPLETE', now())
            RETURNING id
            """,
            (self.target_id, self.catalog.seed_version),
        ).fetchone()
        assert row is not None
        return row["id"]

    def _upsert_source_artifact(self) -> UUID:
        row = self.connection.execute(
            """
            INSERT INTO source_artifact (
                tenant_id, source_system_id, external_key, artifact_type, name,
                source_revision, content_hash, metadata, observed_at
            )
            VALUES (NULL, %s, %s, 'CURATED_SEED_BUNDLE', 'seed-manifest.json',
                    %s, %s, %s, %s)
            ON CONFLICT (tenant_id, source_system_id, external_key, source_revision)
            DO UPDATE SET content_hash = EXCLUDED.content_hash,
                          metadata = EXCLUDED.metadata,
                          observed_at = EXCLUDED.observed_at
            RETURNING id
            """,
            (
                self.source_system_id,
                f"curated-seed:{self.catalog.seed_id}",
                self.catalog.seed_version,
                self.catalog.bundle_hash,
                Jsonb(
                    {
                        "original_source_file": self.catalog.manifest["source_file"],
                        "original_source_sha256": self.catalog.manifest["source_sha256"],
                        "original_source_available": False,
                        "seed_files": [
                            "seed-manifest.json",
                            "domains.json",
                            "categories.json",
                            "capabilities.json",
                            "technologies.json",
                            "relationships.json",
                            "assessments.json",
                            "source-rows.json",
                        ],
                    }
                ),
                self.catalog.observed_at,
            ),
        ).fetchone()
        assert row is not None
        return row["id"]

    def _create_snapshot(self) -> UUID:
        row = self.connection.execute(
            """
            INSERT INTO source_snapshot (
                tenant_id, ingest_run_id, ingest_target_id, source_revision,
                extractor_key, extractor_version, completeness, status,
                observed_at, stats
            )
            VALUES (NULL, %s, %s, %s, %s, %s, 'COMPLETE', 'STAGED', %s, %s)
            RETURNING id
            """,
            (
                self.run_id,
                self.target_id,
                self.catalog.seed_version,
                EXTRACTOR_KEY,
                EXTRACTOR_VERSION,
                self.catalog.observed_at,
                Jsonb(self._catalog_counts()),
            ),
        ).fetchone()
        assert row is not None
        return row["id"]

    def _upsert_entities(self) -> None:
        domains = {item["id"]: item for item in self.catalog.domains}
        categories = {item["id"]: item for item in self.catalog.categories}
        for capability in self.catalog.capabilities:
            domain = domains[capability["domain_id"]]
            canonical_key = f"stackgraph:capability:{capability['id']}"
            properties = {
                "seed_id": self.catalog.seed_id,
                "seed_version": self.catalog.seed_version,
                "capability_key": capability["id"],
                "domain_id": capability["domain_id"],
                "domain_name": domain["name"],
                "definition": capability["definition"],
            }
            self.entities[capability["id"]] = self._upsert_entity(
                entity_type="Capability",
                canonical_key=canonical_key,
                name=capability["name"],
                properties=properties,
            )

        for technology in self.catalog.technologies:
            domain = domains[technology["domain_id"]]
            category = categories[technology["category_id"]]
            lookup_keys = {
                str(technology["id"]).lower(),
                str(technology["name"]).lower(),
                *(str(alias).lower() for alias in technology.get("aliases", [])),
            }
            if str(technology["name"]).lower().endswith(".js"):
                lookup_keys.add(str(technology["name"])[:-3].lower())
            if str(technology["id"]).lower().endswith("-js"):
                lookup_keys.add(str(technology["id"])[:-3].lower())
            canonical_key = f"stackgraph:technology:{technology['id']}"
            properties = {
                "seed_id": self.catalog.seed_id,
                "seed_version": self.catalog.seed_version,
                "domain_id": technology["domain_id"],
                "domain_name": domain["name"],
                "category_id": technology["category_id"],
                "category_name": category["name"],
                "entity_kind": technology["entity_kind"],
                "language_ecosystem": technology.get("language_ecosystem"),
                "purpose": technology.get("purpose"),
                "curated_signal": technology.get("curated_signal"),
                "aliases": technology.get("aliases", []),
                "catalog_lookup_keys": sorted(lookup_keys),
            }
            self.entities[technology["id"]] = self._upsert_entity(
                entity_type="Technology",
                canonical_key=canonical_key,
                name=technology["name"],
                properties=properties,
            )

    def _upsert_entity(
        self,
        *,
        entity_type: str,
        canonical_key: str,
        name: str,
        properties: dict[str, Any],
    ) -> UUID:
        row = self.connection.execute(
            """
            INSERT INTO entity (
                tenant_id, namespace, entity_type, canonical_key, name, properties,
                first_seen_at, last_seen_at
            )
            VALUES (NULL, 'TECHNOLOGY', %s, %s, %s, %s, %s, %s)
            ON CONFLICT (tenant_id, namespace, entity_type, canonical_key) DO UPDATE
            SET name = EXCLUDED.name,
                properties = EXCLUDED.properties,
                first_seen_at = COALESCE(entity.first_seen_at, EXCLUDED.first_seen_at),
                last_seen_at = EXCLUDED.last_seen_at,
                updated_at = now()
            RETURNING id
            """,
            (
                entity_type,
                canonical_key,
                name,
                Jsonb(properties),
                self.catalog.observed_at,
                self.catalog.observed_at,
            ),
        ).fetchone()
        assert row is not None
        entity_id: UUID = row["id"]
        self.connection.execute(
            """
            INSERT INTO entity_identity (
                tenant_id, entity_id, scheme, identity_value, is_canonical,
                source_artifact_id, first_seen_at, last_seen_at
            )
            VALUES (NULL, %s, 'STACKGRAPH', %s, true, %s, %s, %s)
            ON CONFLICT (tenant_id, scheme, identity_value) DO UPDATE
            SET entity_id = EXCLUDED.entity_id,
                source_artifact_id = EXCLUDED.source_artifact_id,
                last_seen_at = EXCLUDED.last_seen_at
            """,
            (
                entity_id,
                canonical_key,
                self.artifact_id,
                self.catalog.observed_at,
                self.catalog.observed_at,
            ),
        )
        return entity_id

    def _insert_entity_property_facts(self) -> None:
        domains = {item["id"]: item for item in self.catalog.domains}
        categories = {item["id"]: item for item in self.catalog.categories}
        for capability in self.catalog.capabilities:
            domain = domains[capability["domain_id"]]
            self._insert_fact(
                subject_id=self.entities[capability["id"]],
                predicate="HAS_PROPERTY",
                object_value={
                    "record_kind": "capability_catalog_entry",
                    "capability_key": capability["id"],
                    "domain_id": capability["domain_id"],
                    "domain_name": domain["name"],
                    "definition": capability["definition"],
                },
                confidence=1.0,
                logical_scope=f"capability:{capability['id']}:catalog-entry",
                locator={"seed_file": "capabilities.json", "record_id": capability["id"]},
                record_kind="CAPABILITY",
            )

        for technology in self.catalog.technologies:
            domain = domains[technology["domain_id"]]
            category = categories[technology["category_id"]]
            locator: dict[str, Any] = {
                "seed_file": "technologies.json",
                "record_id": technology["id"],
            }
            if technology.get("source_line") is not None:
                locator["source_line"] = technology["source_line"]
            self._insert_fact(
                subject_id=self.entities[technology["id"]],
                predicate="HAS_PROPERTY",
                object_value={
                    "record_kind": "technology_catalog_entry",
                    "domain_id": technology["domain_id"],
                    "domain_name": domain["name"],
                    "category_id": technology["category_id"],
                    "category_name": category["name"],
                    "entity_kind": technology["entity_kind"],
                    "language_ecosystem": technology.get("language_ecosystem"),
                    "purpose": technology.get("purpose"),
                    "curated_signal": technology.get("curated_signal"),
                },
                confidence=float(technology["confidence"]),
                logical_scope=f"technology:{technology['id']}:catalog-entry",
                locator=locator,
                record_kind="TECHNOLOGY",
            )

    def _insert_relationship_facts(self) -> None:
        technologies = {item["id"]: item for item in self.catalog.technologies}
        for relationship in self.catalog.relationships:
            source_record = technologies[relationship["source"]]
            locator: dict[str, Any] = {
                "seed_file": "relationships.json",
                "source": relationship["source"],
                "predicate": relationship["type"],
                "target": relationship["target"],
            }
            if source_record.get("source_line") is not None:
                locator["source_line"] = source_record["source_line"]
            self._insert_fact(
                subject_id=self.entities[relationship["source"]],
                predicate=relationship["type"],
                object_entity_id=self.entities[relationship["target"]],
                confidence=float(relationship["confidence"]),
                logical_scope=(
                    f"relationship:{relationship['source']}:{relationship['type']}:"
                    f"{relationship['target']}"
                ),
                locator=locator,
                record_kind="RELATIONSHIP",
            )

    def _insert_assessments(self) -> None:
        self.connection.execute(
            """
            UPDATE assessment
            SET status = 'SUPERSEDED', valid_to = %s
            WHERE method = 'CURATED_SEED'
              AND method_version <> %s
              AND status = 'CURRENT'
            """,
            (self.catalog.observed_at, self.catalog.seed_version),
        )

        for assessment in self.catalog.assessments:
            fact_id = self._insert_fact(
                subject_id=self.entities[assessment["technology_id"]],
                predicate="HAS_PROPERTY",
                object_value={
                    "record_kind": "curated_assessment_signal",
                    "dimension": assessment["dimension"],
                    "value": assessment["value"],
                    "rationale": assessment["rationale"],
                },
                confidence=float(assessment["confidence"]),
                logical_scope=(
                    f"assessment:{assessment['technology_id']}:"
                    f"{assessment['dimension']}"
                ),
                locator={
                    "seed_file": "assessments.json",
                    "technology_id": assessment["technology_id"],
                    "dimension": assessment["dimension"],
                    "source_line": assessment["source_line"],
                },
                record_kind="ASSESSMENT_SIGNAL",
            )
            row = self.connection.execute(
                """
                INSERT INTO assessment (
                    tenant_id, subject_entity_id, assessment_type, dimension,
                    categorical_value, confidence, method, method_version,
                    rationale, query_snapshot_key, status, valid_from
                )
                VALUES (
                    NULL, %s, 'CURATED_SIGNAL', %s, %s, %s,
                    'CURATED_SEED', %s, %s, %s, 'CURRENT', %s
                )
                RETURNING id
                """,
                (
                    self.entities[assessment["technology_id"]],
                    assessment["dimension"],
                    assessment["value"],
                    assessment["confidence"],
                    self.catalog.seed_version,
                    assessment["rationale"],
                    f"seed:{self.catalog.seed_id}@{self.catalog.seed_version}",
                    self.catalog.observed_at,
                ),
            ).fetchone()
            assert row is not None
            self.connection.execute(
                """
                INSERT INTO assessment_input (
                    tenant_id, assessment_id, fact_assertion_id
                )
                VALUES (NULL, %s, %s)
                """,
                (row["id"], fact_id),
            )

    def _insert_fact(
        self,
        *,
        subject_id: UUID,
        predicate: str,
        confidence: float,
        logical_scope: str,
        locator: dict[str, Any],
        record_kind: str,
        object_entity_id: UUID | None = None,
        object_value: dict[str, Any] | None = None,
    ) -> UUID:
        logical_key = sha256_key(self.catalog.seed_id, logical_scope)
        idempotency_key = sha256_key(
            logical_key,
            self.catalog.seed_version,
            EXTRACTOR_VERSION,
        )
        row = self.connection.execute(
            """
            INSERT INTO fact_assertion (
                tenant_id, source_snapshot_id, subject_entity_id, predicate,
                object_entity_id, object_value, assertion_class, confidence,
                logical_key, idempotency_key, source_revision, extractor_key,
                extractor_version, properties, effective_from, observed_at
            )
            VALUES (
                NULL, %s, %s, %s, %s, %s, 'CURATED', %s,
                %s, %s, %s, %s, %s, %s, %s, %s
            )
            RETURNING id
            """,
            (
                self.snapshot_id,
                subject_id,
                predicate,
                object_entity_id,
                Jsonb(object_value) if object_value is not None else None,
                confidence,
                logical_key,
                idempotency_key,
                self.catalog.seed_version,
                EXTRACTOR_KEY,
                EXTRACTOR_VERSION,
                Jsonb(
                    {
                        "seed_id": self.catalog.seed_id,
                        "seed_version": self.catalog.seed_version,
                        "record_kind": record_kind,
                    }
                ),
                self.catalog.observed_at,
                self.catalog.observed_at,
            ),
        ).fetchone()
        assert row is not None
        fact_id: UUID = row["id"]
        self.connection.execute(
            """
            INSERT INTO evidence (
                tenant_id, fact_assertion_id, source_artifact_id, evidence_type,
                locator, metadata, observed_at
            )
            VALUES (NULL, %s, %s, 'CURATED_REFERENCE', %s, %s, %s)
            """,
            (
                fact_id,
                self.artifact_id,
                Jsonb(locator),
                Jsonb({"seed_version": self.catalog.seed_version}),
                self.catalog.observed_at,
            ),
        )
        self.fact_count += 1
        return fact_id

    def _complete_run(self) -> None:
        counts = self._catalog_counts() | {"fact_count": self.fact_count}
        self.connection.execute(
            """
            UPDATE ingest_run
            SET status = 'SUCCEEDED', completeness = 'COMPLETE',
                completed_at = now(), stats = %s
            WHERE id = %s
            """,
            (Jsonb(counts), self.run_id),
        )
        self.connection.execute(
            """
            UPDATE ingest_target
            SET last_success_at = now(), updated_at = now()
            WHERE id = %s
            """,
            (self.target_id,),
        )

    def _catalog_counts(self) -> dict[str, int]:
        return {
            "technology_count": len(self.catalog.technologies),
            "capability_count": len(self.catalog.capabilities),
            "relationship_count": len(self.catalog.relationships),
            "assessment_count": len(self.catalog.assessments),
        }

    def _result(self, *, replayed: bool) -> SeedResult:
        expected_fact_count = (
            len(self.catalog.technologies)
            + len(self.catalog.capabilities)
            + len(self.catalog.relationships)
            + len(self.catalog.assessments)
        )
        return SeedResult(
            seed_id=self.catalog.seed_id,
            seed_version=self.catalog.seed_version,
            replayed=replayed,
            technology_count=len(self.catalog.technologies),
            capability_count=len(self.catalog.capabilities),
            relationship_count=len(self.catalog.relationships),
            assessment_count=len(self.catalog.assessments),
            fact_count=self.fact_count if not replayed else expected_fact_count,
        )


def seed_database(database_url: str, seed_dir: Path) -> SeedResult:
    catalog = load_catalog(seed_dir)
    with psycopg.connect(database_url, row_factory=dict_row) as connection:
        return CatalogSeeder(connection, catalog).run()


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed StackGraph curated catalog data")
    parser.add_argument(
        "--seed-dir",
        type=Path,
        default=Path(os.environ.get("STACKGRAPH_SEED_DIR", "/seed")),
    )
    args = parser.parse_args()
    database_url = os.environ.get("STACKGRAPH_DATABASE_URL")
    if not database_url:
        parser.error("STACKGRAPH_DATABASE_URL is required")

    result = seed_database(database_url, args.seed_dir)
    print(json.dumps(result.as_dict(), sort_keys=True))


if __name__ == "__main__":
    main()
