"""Resolve observed container images and write the typed container profile.

`estate_container_profile` is keyed by immutable digest, and the scanner never resolves one, so
the table had no writer and `/repositories/{id}/container-compositions` could only degrade to
untyped entities. This is the asynchronous step S3 asks for: it runs after a scan, never during
one, and a scan's conclusions do not change if it never runs at all.

Gated by `REGISTRY_ENRICHMENT`, which defaults off. Reaching an external registry is a decision
an operator makes.
"""

from __future__ import annotations

import argparse
import os
from typing import Any, Mapping
from uuid import UUID

import psycopg
from psycopg import Connection
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from stackgraph_data.container_packages import PackageInventory, read_package_inventory
from stackgraph_data.container_registry import (
    ContainerRegistryClient,
    ContainerRegistryError,
    ResolvedImage,
    parse_image_reference,
)


METHOD_VERSION = "container-enrichment/1.1.0"

# `ecosystem` names what the package is; `source` names the database it was read from. A
# `pkg:npm` record found in an image's node_modules and one declared by a repository are the
# same ecosystem and very different claims.
_SOURCE_OF_ECOSYSTEM = {"deb": "dpkg", "apk": "apk", "pypi": "python", "npm": "npm"}


def _flag_enabled(
    connection: Connection[dict[str, Any]], tenant_id: UUID, flag_key: str = "REGISTRY_ENRICHMENT",
) -> bool:
    row = connection.execute(
        """
        SELECT enabled FROM phase2_feature_flag
        WHERE flag_key=%s AND (tenant_id IS NULL OR tenant_id=%s)
        ORDER BY (tenant_id IS NOT NULL) DESC LIMIT 1
        """,
        (flag_key, tenant_id),
    ).fetchone()
    return bool(row and row["enabled"])


def unresolved_images(
    connection: Connection[dict[str, Any]], tenant_id: UUID, *, limit: int,
) -> list[Mapping[str, Any]]:
    """Container images the estate observed but has no digest-keyed profile for.

    Only images something is actually built from or deployed as are resolved. An image mentioned
    nowhere in the estate is not StackGraph's to fetch.
    """
    return connection.execute(
        """
        SELECT DISTINCT image.id image_entity_id, image.canonical_key, image.name,
               repository.id repository_entity_id, fact.source_revision, fact.observed_at
        FROM entity image
        JOIN fact_assertion fact
          ON (fact.object_entity_id=image.id AND fact.predicate IN ('RUNS_ON','BASED_ON'))
        LEFT JOIN entity repository
          ON repository.id=fact.subject_entity_id AND repository.entity_type='Repository'
        LEFT JOIN estate_container_profile profile
          ON profile.image_entity_id=image.id AND profile.valid_to IS NULL
         AND profile.source_revision=fact.source_revision
        WHERE image.tenant_id=%s AND image.entity_type='ContainerImage'
          AND fact.system_to IS NULL AND profile.id IS NULL
        ORDER BY image.canonical_key
        LIMIT %s
        """,
        (tenant_id, limit),
    ).fetchall()


def _image_reference(canonical_key: str) -> str:
    """Recover the registry reference from the entity's canonical key.

    The scanner mints `container-image:<reference>`; anything else is a build placeholder the
    registry has never heard of and must not be requested.
    """
    prefix = "container-image:"
    if not canonical_key.startswith(prefix):
        raise ContainerRegistryError(
            f"{canonical_key!r} is not a registry reference; it names a local build",
        )
    return canonical_key[len(prefix):]


def persist_resolution(
    connection: Connection[dict[str, Any]],
    *,
    tenant_id: UUID,
    image_entity_id: UUID,
    repository_entity_id: UUID | None,
    source_revision: str,
    observed_at: Any,
    resolved: ResolvedImage,
    inventory: PackageInventory | None = None,
) -> UUID:
    reference = resolved.reference
    if reference.tag:
        # The tag history is kept rather than overwritten: a tag that has moved since is then
        # visible as a moved tag instead of silently replacing what production actually ran.
        connection.execute(
            """
            INSERT INTO container_tag_resolution(
              tenant_id,registry_host,repository,tag,digest,architecture,operating_system,
              media_type
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT DO NOTHING
            """,
            (
                tenant_id, reference.registry_host, reference.repository, reference.tag,
                resolved.digest, resolved.architecture, resolved.operating_system,
                resolved.media_type,
            ),
        )
    row = connection.execute(
        """
        INSERT INTO estate_container_profile(
          tenant_id,image_entity_id,repository_entity_id,digest,tags,registry,architecture,
          operating_system,build_metadata,deployment_metadata,coverage,source_revision,observed_at
        ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        ON CONFLICT(tenant_id,digest,source_revision) DO UPDATE SET
          image_entity_id=EXCLUDED.image_entity_id,
          repository_entity_id=EXCLUDED.repository_entity_id,
          tags=EXCLUDED.tags,
          architecture=EXCLUDED.architecture,
          operating_system=EXCLUDED.operating_system,
          build_metadata=EXCLUDED.build_metadata,
          deployment_metadata=EXCLUDED.deployment_metadata,
          coverage=EXCLUDED.coverage,
          observed_at=EXCLUDED.observed_at
        RETURNING id
        """,
        (
            tenant_id, image_entity_id, repository_entity_id, resolved.digest,
            [reference.tag] if reference.tag else [], reference.registry_host,
            resolved.architecture, resolved.operating_system,
            Jsonb({
                "entrypoint": list(resolved.entrypoint),
                "user": resolved.user,
                "exposed_ports": list(resolved.exposed_ports),
                "labels": dict(resolved.runtime_labels),
                "platform_digest": resolved.platform_digest,
                "media_type": resolved.media_type,
                "method_version": METHOD_VERSION,
            }),
            Jsonb({"limitations": [
                *resolved.limitations, *(inventory.limitations if inventory else ()),
            ]}),
            # The manifest's coverage plus what the layer read achieved. `os_packages` stays
            # NOT_COLLECTED unless a read actually happened, so an image nobody looked inside is
            # never confused with one that has no packages.
            Jsonb({
                **dict(resolved.coverage),
                **({"os_packages": inventory.coverage} if inventory else {}),
            }),
            source_revision, observed_at,
        ),
    ).fetchone()
    profile_id = row["id"]
    connection.execute(
        """
        UPDATE estate_container_profile SET valid_to=now()
        WHERE tenant_id=%s AND image_entity_id=%s AND id<>%s AND valid_to IS NULL
        """,
        (tenant_id, image_entity_id, profile_id),
    )
    if inventory is not None:
        # Rewritten wholesale rather than merged: the inventory describes this digest, and a
        # package that has disappeared from a re-read must disappear from the record too.
        connection.execute(
            "DELETE FROM estate_container_package WHERE container_profile_id=%s", (profile_id,),
        )
        for package in inventory.packages:
            connection.execute(
                """
                INSERT INTO estate_container_package(
                  tenant_id,container_profile_id,name,version,ecosystem,purl,source
                ) VALUES (%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT DO NOTHING
                """,
                (
                    tenant_id, profile_id, package.name, package.version, package.ecosystem,
                    package.purl, _SOURCE_OF_ECOSYSTEM.get(package.ecosystem),
                ),
            )
    for ordinal, layer in enumerate(resolved.layers):
        connection.execute(
            """
            INSERT INTO estate_container_layer(
              tenant_id,container_profile_id,ordinal,digest,size_bytes
            ) VALUES (%s,%s,%s,%s,%s)
            ON CONFLICT(container_profile_id,ordinal) DO UPDATE SET
              digest=EXCLUDED.digest, size_bytes=EXCLUDED.size_bytes
            """,
            (
                tenant_id, profile_id, ordinal,
                str(layer.get("digest")) if layer.get("digest") else None,
                int(layer["size"]) if isinstance(layer.get("size"), int) else None,
            ),
        )
    return profile_id


def run_enrichment(
    connection: Connection[dict[str, Any]], *, tenant_id: UUID, registry: ContainerRegistryClient,
    limit: int = 50,
) -> dict[str, int]:
    connection.execute("SELECT set_config('app.tenant_id',%s,true)", (str(tenant_id),))
    if not _flag_enabled(connection, tenant_id):
        return {
            "examined": 0, "resolved": 0, "unresolvable": 0, "packages_recorded": 0,
            "skipped_disabled": 1,
        }
    # Reading layers is a second, much larger decision than reading a manifest, so it has its
    # own flag. With it off the profile still reports `os_packages: NOT_COLLECTED`, which is
    # what it has always said and remains true.
    read_packages = _flag_enabled(connection, tenant_id, "CONTAINER_PACKAGE_INVENTORY")
    examined = 0
    resolved_count = 0
    unresolvable = 0
    packages_recorded = 0
    for image in unresolved_images(connection, tenant_id, limit=limit):
        examined += 1
        try:
            resolved = registry.resolve(_image_reference(image["canonical_key"]))
        except ContainerRegistryError:
            # An image that cannot be resolved stays unresolved. The read surface already
            # reports an unresolved tag as INFERRED or UNRESOLVED, which is the truth.
            unresolvable += 1
            continue
        inventory = None
        if read_packages:
            try:
                inventory = read_package_inventory(registry, resolved)
            except ContainerRegistryError as error:
                # A failed layer read never costs the digest. The manifest resolution is still
                # a real identity worth recording, with the gap stated beside it.
                inventory = PackageInventory(
                    coverage="NOT_COLLECTED",
                    limitations=(f"the image's layers could not be read: {error}",),
                )
            packages_recorded += len(inventory.packages)
        persist_resolution(
            connection, tenant_id=tenant_id, image_entity_id=image["image_entity_id"],
            repository_entity_id=image["repository_entity_id"],
            source_revision=image["source_revision"], observed_at=image["observed_at"],
            resolved=resolved, inventory=inventory,
        )
        resolved_count += 1
    return {
        "examined": examined, "resolved": resolved_count, "unresolvable": unresolvable,
        "packages_recorded": packages_recorded, "skipped_disabled": 0,
    }


def _database_url() -> str:
    url = os.environ.get("STACKGRAPH_DATABASE_URL")
    if not url:
        raise SystemExit("STACKGRAPH_DATABASE_URL is required")
    return url


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tenant-id", required=True)
    parser.add_argument("--limit", type=int, default=50)
    arguments = parser.parse_args(argv)
    from stackgraph_data.npm_registry import UrlLibTransport

    registry = ContainerRegistryClient(UrlLibTransport())
    with psycopg.connect(_database_url(), row_factory=dict_row) as connection:
        counts = run_enrichment(
            connection, tenant_id=UUID(arguments.tenant_id), registry=registry,
            limit=arguments.limit,
        )
        connection.commit()
    for key in sorted(counts):
        print(f"{key}={counts[key]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
