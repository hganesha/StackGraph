"""Enumerate what a package registry offers, so an upgrade target is not limited to the estate.

`valid_targets` could only offer versions some repository already ran, because
`package_registry_identity` records estate identity and nothing enumerated a registry. That made
§6's "14.x — candidate upgrade" unreachable: if nobody had upgraded yet, there was nothing to
upgrade to.

Enumeration is deliberately *not* written into `package_registry_identity`. Every row there has
an entity, so enumerating would invent entities for versions the estate does not run and inflate
every count taken over the estate. A catalogue is a different claim — "the registry offers this"
rather than "we run this" — so it gets its own table and is joined at read time.

The npm packument already contains every version; the previous client fetched it and discarded
all but one. PyPI needs the project endpoint rather than the per-version one. Neither adds a
request beyond what resolving a single version already costs.
"""

from __future__ import annotations

import argparse
import json
import os
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterable, Mapping
from urllib.parse import quote
from uuid import UUID

import psycopg
from psycopg import Connection
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb


# A catalogue is only useful if it is bounded. A package with thousands of releases contributes
# its newest; offering every historical patch would drown the list a user has to choose from.
MAX_VERSIONS_PER_PACKAGE = 200
# Two conventions, and neither can be matched by the other's rule. SemVer separates the
# prerelease with a hyphen and the whole identifier is the marker; PEP 440 attaches it directly
# to the release number with no separator at all. A `+` never introduces a prerelease in either
# — it is build metadata — so `1.0.0+build.5` is a release however it starts.
_SEMVER_PRERELEASE = re.compile(
    r"-(?:a|b|rc|c|alpha|beta|dev|pre|preview|next|canary|nightly|snapshot|m)(?:[.\-]?\d+)?\b",
    re.IGNORECASE,
)
_PEP440_PRERELEASE = re.compile(r"\d(?:a|b|c|rc|alpha|beta|dev|pre)\d*$", re.IGNORECASE)
_NUMERIC = re.compile(r"\d+")


def is_prerelease(version: str) -> bool:
    """Report whether a version string names a prerelease.

    Two conventions are recognised because neither subsumes the other: SemVer's hyphenated
    identifier (`2.0.0-rc1`) and PEP 440's attached suffix (`24.0.0b1`). Build metadata after a
    `+` is stripped first, so `1.0.0+build.5` is a release rather than a "b" prerelease.

    Deliberately conservative: mistaking a stable release for a prerelease hides it from the
    target list, which is the more damaging of the two errors.
    """
    candidate = version.split("+", 1)[0]
    return bool(_SEMVER_PRERELEASE.search(candidate) or _PEP440_PRERELEASE.search(candidate))


def _release_key(version: str) -> tuple[tuple[int, Any], ...]:
    return tuple(
        (0, int(part)) if part.isdigit() else (1, part.lower())
        for part in re.split(r"[.+\-_]", version) if part
    )


@dataclass(frozen=True)
class CatalogVersion:
    version: str
    is_prerelease: bool
    is_yanked: bool = False
    is_deprecated: bool = False
    deprecation_reason: str | None = None
    published_at: str | None = None


@dataclass(frozen=True)
class CatalogResult:
    ecosystem: str
    registry_key: str
    package_name: str
    status: str
    versions: tuple[CatalogVersion, ...]
    limitations: tuple[str, ...]
    source_uri: str | None = None


def npm_catalog(document: Mapping[str, Any], *, registry_key: str, source_uri: str) -> CatalogResult:
    """Extract every offered version from an npm packument.

    Deprecation is per-version in npm and is carried through rather than flattened: a package
    with three deprecated releases and one live one is a different situation from a package
    that is deprecated outright.
    """
    name = document.get("name")
    versions = document.get("versions")
    if not isinstance(name, str) or not isinstance(versions, Mapping):
        return CatalogResult(
            ecosystem="npm", registry_key=registry_key, package_name=str(name or ""),
            status="ERROR", versions=(),
            limitations=("the registry document carried no version map",),
            source_uri=source_uri,
        )
    published = document.get("time") if isinstance(document.get("time"), Mapping) else {}
    collected: list[CatalogVersion] = []
    for version, metadata in versions.items():
        if not isinstance(version, str) or not isinstance(metadata, Mapping):
            continue
        deprecation = metadata.get("deprecated")
        collected.append(CatalogVersion(
            version=version,
            is_prerelease=is_prerelease(version),
            is_deprecated=bool(deprecation),
            deprecation_reason=str(deprecation) if isinstance(deprecation, str) else None,
            published_at=(
                published.get(version) if isinstance(published.get(version), str) else None
            ),
        ))
    return _bounded(
        CatalogResult(
            ecosystem="npm", registry_key=registry_key, package_name=name,
            status="AVAILABLE", versions=tuple(collected), limitations=(),
            source_uri=source_uri,
        )
    )


def pypi_catalog(document: Mapping[str, Any], *, registry_key: str, source_uri: str) -> CatalogResult:
    """Extract every offered version from a PyPI project document.

    A release with no files is not offered — PyPI keeps the key after every artifact is removed —
    and a release whose every artifact is yanked is recorded as yanked rather than dropped, so a
    reader can see that it existed and was withdrawn.
    """
    info = document.get("info") if isinstance(document.get("info"), Mapping) else {}
    releases = document.get("releases")
    name = info.get("name")
    if not isinstance(name, str) or not isinstance(releases, Mapping):
        return CatalogResult(
            ecosystem="pypi", registry_key=registry_key, package_name=str(name or ""),
            status="ERROR", versions=(),
            limitations=("the registry document carried no release map",),
            source_uri=source_uri,
        )
    collected: list[CatalogVersion] = []
    for version, artifacts in releases.items():
        if not isinstance(version, str) or not isinstance(artifacts, list) or not artifacts:
            continue
        yanked = all(
            isinstance(artifact, Mapping) and artifact.get("yanked") is True
            for artifact in artifacts
        )
        uploads = sorted(
            str(artifact.get("upload_time_iso_8601"))
            for artifact in artifacts
            if isinstance(artifact, Mapping) and artifact.get("upload_time_iso_8601")
        )
        collected.append(CatalogVersion(
            version=version,
            is_prerelease=is_prerelease(version),
            is_yanked=yanked,
            published_at=uploads[0] if uploads else None,
        ))
    return _bounded(
        CatalogResult(
            ecosystem="pypi", registry_key=registry_key, package_name=name,
            status="AVAILABLE", versions=tuple(collected), limitations=(),
            source_uri=source_uri,
        )
    )


def _bounded(result: CatalogResult) -> CatalogResult:
    if len(result.versions) <= MAX_VERSIONS_PER_PACKAGE:
        return result
    ordered = sorted(result.versions, key=lambda item: _release_key(item.version), reverse=True)
    return CatalogResult(
        ecosystem=result.ecosystem, registry_key=result.registry_key,
        package_name=result.package_name, status="PARTIAL",
        versions=tuple(ordered[:MAX_VERSIONS_PER_PACKAGE]),
        limitations=(
            *result.limitations,
            f"only the newest {MAX_VERSIONS_PER_PACKAGE} of {len(result.versions)} released "
            "versions were catalogued",
        ),
        source_uri=result.source_uri,
    )


def persist_catalog(
    connection: Connection[dict[str, Any]], result: CatalogResult, *, tenant_id: UUID | None = None,
) -> int:
    """Write a catalogue and its collection record. Returns the number of versions stored."""
    for version in result.versions:
        connection.execute(
            """
            INSERT INTO package_version_catalog(
              tenant_id,registry_key,ecosystem,package_name,version,is_prerelease,is_yanked,
              is_deprecated,deprecation_reason,published_at,source_uri
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT(tenant_id,registry_key,package_name,version) DO UPDATE SET
              is_prerelease=EXCLUDED.is_prerelease,
              is_yanked=EXCLUDED.is_yanked,
              is_deprecated=EXCLUDED.is_deprecated,
              deprecation_reason=EXCLUDED.deprecation_reason,
              published_at=EXCLUDED.published_at,
              collected_at=now()
            """,
            (
                tenant_id, result.registry_key, result.ecosystem, result.package_name,
                version.version, version.is_prerelease, version.is_yanked,
                version.is_deprecated, version.deprecation_reason, version.published_at,
                result.source_uri,
            ),
        )
    connection.execute(
        """
        INSERT INTO package_catalog_collection(
          tenant_id,registry_key,ecosystem,package_name,status,version_count,limitations
        ) VALUES (%s,%s,%s,%s,%s,%s,%s)
        ON CONFLICT(tenant_id,registry_key,package_name) DO UPDATE SET
          status=EXCLUDED.status,
          version_count=EXCLUDED.version_count,
          limitations=EXCLUDED.limitations,
          collected_at=now()
        """,
        (
            tenant_id, result.registry_key, result.ecosystem, result.package_name,
            result.status, len(result.versions), Jsonb(list(result.limitations)),
        ),
    )
    return len(result.versions)


def packages_needing_enumeration(
    connection: Connection[dict[str, Any]], *, tenant_id: UUID, limit: int,
) -> list[Mapping[str, Any]]:
    """Packages the estate depends on whose catalogue is missing or stale.

    Only packages something actually depends on are enumerated. Cataloguing a registry
    exhaustively would be a different product.
    """
    return connection.execute(
        """
        SELECT DISTINCT lower(identity.package_name) package_name,
               registry.registry_key,
               CASE WHEN identity.purl LIKE 'pkg:npm/%%' THEN 'npm'
                    WHEN identity.purl LIKE 'pkg:pypi/%%' THEN 'pypi'
               END ecosystem
        FROM fact_assertion fact
        JOIN package_registry_identity identity ON identity.entity_id=fact.object_entity_id
        JOIN package_registry registry ON registry.id=identity.package_registry_id
        LEFT JOIN package_catalog_collection collection
               ON collection.registry_key=registry.registry_key
              AND lower(collection.package_name)=lower(identity.package_name)
              AND collection.collected_at > now() - interval '7 days'
        WHERE fact.tenant_id=%s AND fact.predicate='DEPENDS_ON' AND fact.system_to IS NULL
          AND registry.visibility='PUBLIC'
          AND collection.id IS NULL
          AND (identity.purl LIKE 'pkg:npm/%%' OR identity.purl LIKE 'pkg:pypi/%%')
        ORDER BY 1
        LIMIT %s
        """,
        (tenant_id, limit),
    ).fetchall()


def enumerate_package(
    package_name: str, ecosystem: str, *, registry_key: str, transport: Any,
    npm_origin: str = "https://registry.npmjs.org/",
    pypi_origin: str = "https://pypi.org/",
    timeout_seconds: float = 20.0,
) -> CatalogResult:
    """Fetch and normalise one package's catalogue.

    `transport` is the same protocol the npm and PyPI clients already use, so allowlisting,
    timeouts, and response bounds are enforced by the caller's transport rather than reinvented.
    """
    if ecosystem == "npm":
        uri = f"{npm_origin}{quote(package_name, safe='')}"
    elif ecosystem == "pypi":
        uri = f"{pypi_origin}pypi/{quote(package_name, safe='')}/json"
    else:
        return CatalogResult(
            ecosystem=ecosystem, registry_key=registry_key, package_name=package_name,
            status="ERROR", versions=(),
            limitations=(f"no catalogue adapter exists for the {ecosystem} ecosystem",),
        )
    response = transport.request(
        uri, {"Accept": "application/json", "User-Agent": "StackGraph-registry-catalog/1.0"},
        timeout_seconds,
    )
    if response.status == 404:
        return CatalogResult(
            ecosystem=ecosystem, registry_key=registry_key, package_name=package_name,
            status="NOT_FOUND", versions=(),
            limitations=("the registry does not publish this package",), source_uri=uri,
        )
    if response.status < 200 or response.status >= 300:
        return CatalogResult(
            ecosystem=ecosystem, registry_key=registry_key, package_name=package_name,
            status="ERROR", versions=(),
            limitations=(f"the registry answered with status {response.status}",), source_uri=uri,
        )
    try:
        document = json.loads(response.body)
    except (UnicodeDecodeError, json.JSONDecodeError):
        return CatalogResult(
            ecosystem=ecosystem, registry_key=registry_key, package_name=package_name,
            status="ERROR", versions=(),
            limitations=("the registry returned a document that is not JSON",), source_uri=uri,
        )
    if not isinstance(document, Mapping):
        return CatalogResult(
            ecosystem=ecosystem, registry_key=registry_key, package_name=package_name,
            status="ERROR", versions=(),
            limitations=("the registry returned an unexpected document shape",), source_uri=uri,
        )
    if ecosystem == "npm":
        return npm_catalog(document, registry_key=registry_key, source_uri=uri)
    return pypi_catalog(document, registry_key=registry_key, source_uri=uri)


def run_enumeration(
    connection: Connection[dict[str, Any]], *, tenant_id: UUID, transport: Any, limit: int = 50,
) -> dict[str, int]:
    connection.execute("SELECT set_config('app.tenant_id',%s,true)", (str(tenant_id),))
    examined = 0
    catalogued = 0
    versions = 0
    for package in packages_needing_enumeration(connection, tenant_id=tenant_id, limit=limit):
        if not package["ecosystem"]:
            continue
        examined += 1
        result = enumerate_package(
            package["package_name"], package["ecosystem"],
            registry_key=package["registry_key"], transport=transport,
        )
        versions += persist_catalog(connection, result)
        catalogued += int(result.status in {"AVAILABLE", "PARTIAL"})
    return {"examined": examined, "catalogued": catalogued, "versions_recorded": versions}


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

    with psycopg.connect(_database_url(), row_factory=dict_row) as connection:
        counts = run_enumeration(
            connection, tenant_id=UUID(arguments.tenant_id),
            transport=UrlLibTransport(), limit=arguments.limit,
        )
        connection.commit()
    for key in sorted(counts):
        print(f"{key}={counts[key]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
