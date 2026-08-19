from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from uuid import UUID

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from stackgraph_ai.capabilities import CapabilityTaxonomy, LocalCapabilityCatalog


def sync_capability_taxonomies(
    connection: psycopg.Connection,
    taxonomies: tuple[CapabilityTaxonomy, ...],
    *,
    tenant_id: UUID | None,
    actor_key: str,
) -> int:
    for taxonomy in taxonomies:
        existing = connection.execute(
            """
            SELECT id,content_hash FROM capability_taxonomy_version
            WHERE tenant_id IS NOT DISTINCT FROM %s AND taxonomy_key=%s AND version=%s
            """,
            (tenant_id, taxonomy.key, taxonomy.version),
        ).fetchone()
        if existing and existing["content_hash"] != taxonomy.content_hash:
            used = connection.execute(
                "SELECT 1 FROM capability_inference WHERE taxonomy_version_id=%s LIMIT 1",
                (existing["id"],),
            ).fetchone()
            if used:
                raise ValueError(
                    f"taxonomy {taxonomy.key}@{taxonomy.version} is immutable after inference"
                )
            connection.execute(
                "DELETE FROM capability_mapping WHERE taxonomy_version_id=%s",
                (existing["id"],),
            )
            connection.execute(
                "DELETE FROM capability_definition WHERE taxonomy_version_id=%s",
                (existing["id"],),
            )
        if taxonomy.status == "ACTIVE":
            connection.execute(
                """
                UPDATE capability_taxonomy_version SET status='RETIRED',updated_at=now()
                WHERE tenant_id IS NOT DISTINCT FROM %s AND taxonomy_key=%s
                  AND version<>%s AND status='ACTIVE'
                """,
                (tenant_id, taxonomy.key, taxonomy.version),
            )
        row = connection.execute(
            """
            INSERT INTO capability_taxonomy_version(
              tenant_id,taxonomy_key,version,status,name,description,
              content_hash,metadata,created_by
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT(tenant_id,taxonomy_key,version) DO UPDATE SET
              status=EXCLUDED.status,name=EXCLUDED.name,description=EXCLUDED.description,
              content_hash=EXCLUDED.content_hash,metadata=EXCLUDED.metadata,updated_at=now()
            RETURNING id
            """,
            (
                tenant_id, taxonomy.key, taxonomy.version, taxonomy.status,
                taxonomy.name, taxonomy.description, taxonomy.content_hash,
                Jsonb(dict(taxonomy.metadata)), actor_key,
            ),
        ).fetchone()
        taxonomy_id = row["id"]
        if existing and existing["content_hash"] == taxonomy.content_hash:
            continue
        capability_ids: dict[str, UUID] = {}
        for capability in taxonomy.capabilities:
            definition = connection.execute(
                """
                INSERT INTO capability_definition(
                  taxonomy_version_id,capability_key,name,description,
                  parent_capability_key,aliases,metadata
                ) VALUES (%s,%s,%s,%s,%s,%s,%s) RETURNING id
                """,
                (
                    taxonomy_id, capability.key, capability.name, capability.description,
                    capability.parent_key, Jsonb(list(capability.aliases)),
                    Jsonb(dict(capability.metadata)),
                ),
            ).fetchone()
            capability_ids[capability.key] = definition["id"]
        for mapping in taxonomy.mappings:
            connection.execute(
                """
                INSERT INTO capability_mapping(
                  taxonomy_version_id,capability_definition_id,ecosystem,
                  package_name,symbol_pattern,confidence,rationale,evidence
                ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
                """,
                (
                    taxonomy_id, capability_ids[mapping.capability_key],
                    mapping.ecosystem, mapping.package_name, mapping.symbol_pattern,
                    mapping.confidence, mapping.rationale, Jsonb(dict(mapping.evidence)),
                ),
            )
    return len(taxonomies)


def sync_capabilities(
    database_url: str,
    catalog_dir: Path,
    *,
    tenant_id: UUID | None,
    actor_key: str,
) -> int:
    taxonomies = LocalCapabilityCatalog(catalog_dir).definitions()
    with psycopg.connect(database_url, row_factory=dict_row) as connection:
        return sync_capability_taxonomies(
            connection, taxonomies, tenant_id=tenant_id, actor_key=actor_key,
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="Sync capability taxonomies into PostgreSQL")
    parser.add_argument("--catalog-dir", type=Path, required=True)
    parser.add_argument("--tenant-id", type=UUID)
    parser.add_argument("--actor-key", default="capability-catalog-sync")
    args = parser.parse_args()
    database_url = os.getenv("STACKGRAPH_DATABASE_URL")
    if not database_url:
        parser.error("STACKGRAPH_DATABASE_URL is required")
    count = sync_capabilities(
        database_url,
        args.catalog_dir,
        tenant_id=args.tenant_id,
        actor_key=args.actor_key,
    )
    print(json.dumps({"synced": count, "tenant_id": str(args.tenant_id) if args.tenant_id else None}))


if __name__ == "__main__":
    main()
