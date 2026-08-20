from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import os
import re
import socket
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping
from urllib.error import HTTPError, URLError
from urllib.parse import unquote, urlsplit, urlunsplit
from urllib.request import Request, urlopen
from uuid import UUID

import psycopg
from psycopg import Connection
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from stackgraph_data.catalog import sha256_key
from stackgraph_data.depsdev import PackageVersionKey


JsonObject = dict[str, Any]
DATASET_ID = "deepklarity/top-npm-packages"
DATASET_PAGE = f"https://huggingface.co/datasets/{DATASET_ID}"
DATASET_REVISION = "c411645fa468857669fa7e18bc2fdd38f603e254"
DATASET_EFFECTIVE_AT = datetime(2024, 11, 5, 9, 18, 44, tzinfo=timezone.utc)
DEFAULT_DATASET_URL = (
    f"https://huggingface.co/datasets/{DATASET_ID}/resolve/"
    f"{DATASET_REVISION}/npm_packages.csv"
)
SOURCE_KEY = f"huggingface:{DATASET_ID}"
EXTRACTOR_KEY = "huggingface-top-npm-catalog"
EXTRACTOR_VERSION = "1.1.0"
MAX_DATASET_BYTES = 8 * 1024 * 1024
EXPECTED_COLUMNS = (
    "package_name",
    "description",
    "installation_command",
    "latest_version",
    "last_published",
    "dependents",
    "dependencies",
    "versions",
    "license",
    "total_files",
    "unpacked_size",
    "weekly_downloads",
    "package_url",
    "homepage",
    "repository",
)
SIZE_PATTERN = re.compile(r"^([0-9]+(?:\.[0-9]+)?)\s*([kmgt]?b)$", re.IGNORECASE)
SIZE_MULTIPLIERS = {
    "b": 1,
    "kb": 1_000,
    "mb": 1_000_000,
    "gb": 1_000_000_000,
    "tb": 1_000_000_000_000,
}


@dataclass(frozen=True, slots=True)
class DatasetPayload:
    content: bytes
    source_uri: str
    observed_at: datetime
    effective_at: datetime = DATASET_EFFECTIVE_AT

    @property
    def content_hash(self) -> str:
        return f"sha256:{hashlib.sha256(self.content).hexdigest()}"

    @property
    def source_revision(self) -> str:
        return self.content_hash


@dataclass(frozen=True, slots=True)
class NpmCatalogRecord:
    row_number: int
    package: PackageVersionKey
    metadata: JsonObject
    repository_url: str | None

    @property
    def package_purl(self) -> str:
        return self.package.package_purl

    @property
    def version_purl(self) -> str:
        return self.package.purl

    @property
    def project_key(self) -> str:
        return f"oss:npm:{self.package_purl}"


@dataclass(frozen=True, slots=True)
class ImportResult:
    dataset_id: str
    source_revision: str
    replayed: bool
    row_count: int
    project_count: int
    package_count: int
    version_count: int
    repository_count: int
    fact_count: int

    def as_dict(self) -> dict[str, str | bool | int]:
        return {
            "dataset_id": self.dataset_id,
            "source_revision": self.source_revision,
            "replayed": self.replayed,
            "row_count": self.row_count,
            "project_count": self.project_count,
            "package_count": self.package_count,
            "version_count": self.version_count,
            "repository_count": self.repository_count,
            "fact_count": self.fact_count,
        }


def fetch_dataset(
    url: str = DEFAULT_DATASET_URL,
    *,
    timeout_seconds: float = 30.0,
    max_bytes: int = MAX_DATASET_BYTES,
) -> DatasetPayload:
    _validate_dataset_url(url)
    request = Request(
        url,
        headers={"User-Agent": "StackGraph-OSS-catalog/1.0"},
        method="GET",
    )
    try:
        with urlopen(request, timeout=timeout_seconds) as response:
            final_url = response.geturl()
            _validate_dataset_url(final_url)
            declared_length = response.headers.get("Content-Length")
            if declared_length and int(declared_length) > max_bytes:
                raise ValueError("Hugging Face dataset exceeds the configured size limit")
            content = response.read(max_bytes + 1)
    except HTTPError as error:
        raise RuntimeError(
            f"Hugging Face dataset request failed with HTTP {error.code}"
        ) from error
    except (URLError, TimeoutError, socket.timeout) as error:
        reason = getattr(error, "reason", error)
        raise RuntimeError(f"Hugging Face dataset request failed: {reason}") from error
    if len(content) > max_bytes:
        raise ValueError("Hugging Face dataset exceeds the configured size limit")
    return DatasetPayload(
        content=content,
        # Keep the durable requested URL as provenance; the cache redirect can
        # contain transient query parameters even though its bytes are verified.
        source_uri=url,
        observed_at=datetime.now(timezone.utc),
        effective_at=DATASET_EFFECTIVE_AT,
    )


def load_dataset_file(
    path: Path,
    *,
    observed_at: datetime,
    effective_at: datetime = DATASET_EFFECTIVE_AT,
) -> DatasetPayload:
    content = path.read_bytes()
    if len(content) > MAX_DATASET_BYTES:
        raise ValueError("Hugging Face dataset exceeds the configured size limit")
    return DatasetPayload(
        content=content,
        source_uri=DEFAULT_DATASET_URL,
        observed_at=_as_utc(observed_at),
        effective_at=_as_utc(effective_at),
    )


def parse_dataset(content: bytes) -> list[NpmCatalogRecord]:
    try:
        decoded = content.decode("utf-8-sig")
    except UnicodeDecodeError as error:
        raise ValueError("Hugging Face npm dataset must be UTF-8 CSV") from error
    reader = csv.DictReader(io.StringIO(decoded, newline=""))
    columns = tuple(reader.fieldnames or ())
    missing = sorted(set(EXPECTED_COLUMNS) - set(columns))
    if missing:
        raise ValueError(f"Hugging Face npm dataset is missing columns: {', '.join(missing)}")

    records: list[NpmCatalogRecord] = []
    seen_names: set[str] = set()
    for row_number, row in enumerate(reader, start=2):
        if None in row:
            raise ValueError(f"row {row_number} has more values than the CSV header")
        source_package_name = _optional_text(row.get("package_name"))
        package_name = source_package_name or _package_name_from_url(row.get("package_url"))
        latest_version = _optional_text(row.get("latest_version"))
        if package_name is None or latest_version is None:
            raise ValueError(f"row {row_number} has no package name or latest version")
        try:
            package = PackageVersionKey.from_version_key(
                {"system": "NPM", "name": package_name, "version": latest_version}
            )
        except ValueError as error:
            raise ValueError(f"row {row_number} has invalid npm coordinates: {error}") from error
        if package.name in seen_names:
            raise ValueError(f"row {row_number} duplicates npm package {package.name!r}")
        seen_names.add(package.name)

        repository_url = _normalize_repository_url(row.get("repository"), row_number)
        metadata: JsonObject = {
            "record_kind": "huggingface_top_npm_package",
            "dataset_id": DATASET_ID,
            "dataset_revision": DATASET_REVISION,
            "dataset_effective_at": DATASET_EFFECTIVE_AT.isoformat(),
            "source_row_number": row_number,
            "source_fields": {
                key: _optional_text(value)
                for key, value in row.items()
                if key is not None
            },
            "ecosystem": "npm",
            "package_name": package.name,
            "package_name_inferred": source_package_name is None,
            "description": _optional_text(row.get("description")),
            "installation_command": _optional_text(row.get("installation_command")),
            "latest_version": package.version,
            # The source deliberately supplies a relative label, not a timestamp.
            "last_published_text": _optional_text(row.get("last_published")),
            "dependents": _nonnegative_int(row.get("dependents"), "dependents", row_number),
            "dependencies": _nonnegative_int(
                row.get("dependencies"), "dependencies", row_number
            ),
            "versions": _nonnegative_int(row.get("versions"), "versions", row_number),
            "license": _optional_text(row.get("license")),
            "total_files": _nonnegative_int(
                row.get("total_files"), "total_files", row_number, optional=True
            ),
            "unpacked_size": _optional_text(row.get("unpacked_size")),
            "unpacked_size_bytes": _size_bytes(row.get("unpacked_size"), row_number),
            "weekly_downloads": _nonnegative_int(
                row.get("weekly_downloads"), "weekly_downloads", row_number
            ),
            "package_url": _validated_optional_url(
                row.get("package_url"), "package_url", row_number
            ),
            "homepage": _validated_optional_url(row.get("homepage"), "homepage", row_number),
            "repository": repository_url,
        }
        extra_fields = {
            key: _optional_text(value)
            for key, value in row.items()
            if key not in EXPECTED_COLUMNS and key is not None
        }
        if extra_fields:
            metadata["extra_fields"] = extra_fields
        records.append(
            NpmCatalogRecord(
                row_number=row_number,
                package=package,
                metadata=metadata,
                repository_url=repository_url,
            )
        )
    if not records:
        raise ValueError("Hugging Face npm dataset contains no records")
    return records


class OssCatalogImporter:
    def __init__(
        self,
        connection: Connection[dict[str, Any]],
        payload: DatasetPayload,
        records: Iterable[NpmCatalogRecord],
    ) -> None:
        self.connection = connection
        self.payload = payload
        self.records = list(records)
        self.source_system_id: UUID | None = None
        self.target_id: UUID | None = None
        self.run_id: UUID | None = None
        self.snapshot_id: UUID | None = None
        self.artifact_id: UUID | None = None
        self.registry_id: UUID | None = None
        self.fact_count = 0
        self.projects: set[UUID] = set()
        self.packages: set[UUID] = set()
        self.versions: set[UUID] = set()
        self.repositories: set[UUID] = set()

    def run(self) -> ImportResult:
        self.source_system_id = self._upsert_source_system()
        self.target_id = self._upsert_target()
        replay_stats = self._published_snapshot_stats()
        if replay_stats is not None:
            return self._result(replayed=True, stats=replay_stats)

        self.run_id = self._create_run()
        self.artifact_id = self._upsert_artifact()
        self.snapshot_id = self._create_snapshot()
        self.registry_id = self._upsert_public_npm_registry()
        for record in self.records:
            self._import_record(record)
        self.connection.execute("SELECT publish_source_snapshot(%s)", (self.snapshot_id,))
        stats = self._stats()
        self.connection.execute(
            """
            UPDATE ingest_run
            SET status='SUCCEEDED',completeness='COMPLETE',completed_at=now(),stats=%s
            WHERE id=%s
            """,
            (Jsonb(stats), self.run_id),
        )
        self.connection.execute(
            "UPDATE ingest_target SET last_success_at=now(),updated_at=now() WHERE id=%s",
            (self.target_id,),
        )
        return self._result(replayed=False, stats=stats)

    def _upsert_source_system(self) -> UUID:
        row = self.connection.execute(
            """
            INSERT INTO source_system(tenant_id,source_key,kind,base_uri,metadata)
            VALUES (NULL,%s,'OTHER',%s,%s)
            ON CONFLICT(tenant_id,source_key) DO UPDATE
            SET kind=EXCLUDED.kind,base_uri=EXCLUDED.base_uri,metadata=EXCLUDED.metadata
            RETURNING id
            """,
            (
                SOURCE_KEY,
                DATASET_PAGE,
                Jsonb(
                    {
                        "dataset_id": DATASET_ID,
                        "dataset_revision": DATASET_REVISION,
                        "dataset_effective_at": self.payload.effective_at.isoformat(),
                        "format": "csv",
                        "license_label": "cc",
                        "source_revision": self.payload.source_revision,
                    }
                ),
            ),
        ).fetchone()
        assert row is not None
        return row["id"]

    def _upsert_target(self) -> UUID:
        row = self.connection.execute(
            """
            INSERT INTO ingest_target(
              tenant_id,source_system_id,target_kind,target_key,priority,enabled,
              refresh_policy,desired_source_revision
            ) VALUES (NULL,%s,'OSS_CATALOG',%s,'COLD',true,%s,%s)
            ON CONFLICT(tenant_id,source_system_id,target_kind,target_key) DO UPDATE
            SET refresh_policy=EXCLUDED.refresh_policy,
                desired_source_revision=EXCLUDED.desired_source_revision,
                updated_at=now()
            RETURNING id
            """,
            (
                self.source_system_id,
                DATASET_ID,
                Jsonb({"mode": "manual_content_addressed"}),
                self.payload.source_revision,
            ),
        ).fetchone()
        assert row is not None
        return row["id"]

    def _published_snapshot_stats(self) -> Mapping[str, Any] | None:
        return self.connection.execute(
            """
            SELECT run.stats
            FROM source_snapshot snapshot
            JOIN ingest_run run ON run.id=snapshot.ingest_run_id
            WHERE snapshot.ingest_target_id=%s AND snapshot.source_revision=%s
              AND snapshot.extractor_key=%s AND snapshot.extractor_version=%s
              AND snapshot.status='PUBLISHED'
            """,
            (
                self.target_id,
                self.payload.source_revision,
                EXTRACTOR_KEY,
                EXTRACTOR_VERSION,
            ),
        ).fetchone()

    def _create_run(self) -> UUID:
        row = self.connection.execute(
            """
            INSERT INTO ingest_run(
              tenant_id,ingest_target_id,trigger_kind,requested_source_revision,
              status,completeness,started_at
            ) VALUES (NULL,%s,'MANUAL',%s,'RUNNING','COMPLETE',now()) RETURNING id
            """,
            (self.target_id, self.payload.source_revision),
        ).fetchone()
        assert row is not None
        return row["id"]

    def _upsert_artifact(self) -> UUID:
        row = self.connection.execute(
            """
            INSERT INTO source_artifact(
              tenant_id,source_system_id,external_key,artifact_type,name,
              source_revision,content_hash,blob_uri,metadata,observed_at
            ) VALUES (NULL,%s,%s,'DATASET_CSV','npm_packages.csv',%s,%s,%s,%s,%s)
            ON CONFLICT(tenant_id,source_system_id,external_key,source_revision)
            DO UPDATE SET content_hash=EXCLUDED.content_hash,blob_uri=EXCLUDED.blob_uri,
                          metadata=EXCLUDED.metadata,observed_at=EXCLUDED.observed_at
            RETURNING id
            """,
            (
                self.source_system_id,
                f"dataset:{DATASET_ID}:npm_packages.csv",
                self.payload.source_revision,
                self.payload.content_hash,
                self.payload.source_uri,
                Jsonb(
                    {
                        "dataset_id": DATASET_ID,
                        "dataset_revision": DATASET_REVISION,
                        "dataset_effective_at": self.payload.effective_at.isoformat(),
                        "row_count": len(self.records),
                    }
                ),
                self.payload.observed_at,
            ),
        ).fetchone()
        assert row is not None
        return row["id"]

    def _create_snapshot(self) -> UUID:
        row = self.connection.execute(
            """
            INSERT INTO source_snapshot(
              tenant_id,ingest_run_id,ingest_target_id,source_revision,
              extractor_key,extractor_version,completeness,status,observed_at,stats
            ) VALUES (NULL,%s,%s,%s,%s,%s,'COMPLETE','STAGED',%s,%s) RETURNING id
            """,
            (
                self.run_id,
                self.target_id,
                self.payload.source_revision,
                EXTRACTOR_KEY,
                EXTRACTOR_VERSION,
                self.payload.observed_at,
                Jsonb({"row_count": len(self.records)}),
            ),
        ).fetchone()
        assert row is not None
        return row["id"]

    def _upsert_public_npm_registry(self) -> UUID:
        source = self.connection.execute(
            """
            INSERT INTO source_system(tenant_id,source_key,kind,base_uri,metadata)
            VALUES (NULL,'registry.npmjs.org','PACKAGE_REGISTRY',
                    'https://registry.npmjs.org/','{}')
            ON CONFLICT(tenant_id,source_key) DO UPDATE SET base_uri=EXCLUDED.base_uri
            RETURNING id
            """
        ).fetchone()
        assert source is not None
        registry = self.connection.execute(
            """
            INSERT INTO package_registry(
              tenant_id,source_system_id,registry_key,origin_uri,normalized_origin_uri,
              ecosystem,visibility,auth_mode,allow_metadata_fetch,metadata
            ) VALUES (NULL,%s,'npm-public','https://registry.npmjs.org/',
                      'https://registry.npmjs.org/','NPM','PUBLIC','NONE',true,'{}')
            ON CONFLICT(tenant_id,ecosystem,normalized_origin_uri) DO UPDATE
            SET source_system_id=EXCLUDED.source_system_id,registry_key=EXCLUDED.registry_key,
                visibility='PUBLIC',updated_at=now()
            RETURNING id
            """,
            (source["id"],),
        ).fetchone()
        assert registry is not None
        return registry["id"]

    def _import_record(self, record: NpmCatalogRecord) -> None:
        package_id = self._upsert_entity(
            namespace="TECHNOLOGY",
            entity_type="Package",
            canonical_key=record.package_purl,
            name=record.package.name,
            properties={
                "ecosystem": "npm",
                "package_name": record.package.name,
                "catalog_metadata": record.metadata,
            },
        )
        version_id = self._upsert_entity(
            namespace="TECHNOLOGY",
            entity_type="PackageVersion",
            canonical_key=record.version_purl,
            name=record.package.display_name,
            properties={
                "ecosystem": "npm",
                "package_name": record.package.name,
                "version": record.package.version,
            },
        )
        project_id = self._upsert_entity(
            namespace="OSS",
            entity_type="OSSProject",
            canonical_key=record.project_key,
            name=record.package.name,
            properties={
                "ecosystem": "npm",
                "package_purl": record.package_purl,
                "catalog_metadata": record.metadata,
            },
        )
        self.packages.add(package_id)
        self.versions.add(version_id)
        self.projects.add(project_id)
        self._upsert_purl_identity(package_id, record.package_purl)
        self._upsert_purl_identity(version_id, record.version_purl)
        self._upsert_registry_identity(package_id, record, version=None)
        self._upsert_registry_identity(version_id, record, version=record.package.version)

        self._insert_fact(
            subject_id=package_id,
            predicate="HAS_PROPERTY",
            object_value=record.metadata,
            logical_scope=f"package:{record.package_purl}:catalog-metadata",
            row_number=record.row_number,
        )
        self._insert_fact(
            subject_id=project_id,
            predicate="PUBLISHES",
            object_entity_id=package_id,
            logical_scope=f"project:{record.project_key}:publishes:{record.package_purl}",
            row_number=record.row_number,
        )
        self._insert_fact(
            subject_id=package_id,
            predicate="HAS_VERSION",
            object_entity_id=version_id,
            logical_scope=f"package:{record.package_purl}:version:{record.version_purl}",
            row_number=record.row_number,
        )
        if record.repository_url is not None:
            repository_id = self._upsert_entity(
                namespace="OSS",
                entity_type="OSSRepository",
                canonical_key=record.repository_url,
                name=_repository_name(record.repository_url),
                properties={"url": record.repository_url, "provider": "github"},
            )
            self.repositories.add(repository_id)
            self._upsert_url_identity(repository_id, record.repository_url)
            self._insert_fact(
                subject_id=project_id,
                predicate="HOSTED_IN",
                object_entity_id=repository_id,
                logical_scope=(
                    f"project:{record.project_key}:repository:{record.repository_url}"
                ),
                row_number=record.row_number,
            )

    def _upsert_entity(
        self,
        *,
        namespace: str,
        entity_type: str,
        canonical_key: str,
        name: str,
        properties: JsonObject,
    ) -> UUID:
        row = self.connection.execute(
            """
            INSERT INTO entity(
              tenant_id,namespace,entity_type,canonical_key,name,properties,
              first_seen_at,last_seen_at
            ) VALUES (NULL,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT(tenant_id,namespace,entity_type,canonical_key) DO UPDATE
            SET name=EXCLUDED.name,properties=entity.properties || EXCLUDED.properties,
                first_seen_at=COALESCE(entity.first_seen_at,EXCLUDED.first_seen_at),
                last_seen_at=GREATEST(entity.last_seen_at,EXCLUDED.last_seen_at),
                updated_at=now()
            RETURNING id
            """,
            (
                namespace,
                entity_type,
                canonical_key,
                name,
                Jsonb(properties),
                self.payload.effective_at,
                self.payload.effective_at,
            ),
        ).fetchone()
        assert row is not None
        return row["id"]

    def _upsert_purl_identity(self, entity_id: UUID, purl: str) -> None:
        self.connection.execute(
            """
            INSERT INTO entity_identity(
              tenant_id,entity_id,scheme,identity_value,is_canonical,
              source_artifact_id,first_seen_at,last_seen_at
            ) VALUES (NULL,%s,'PURL',%s,true,%s,%s,%s)
            ON CONFLICT(tenant_id,scheme,identity_value) DO UPDATE
            SET entity_id=EXCLUDED.entity_id,is_canonical=true,
                source_artifact_id=EXCLUDED.source_artifact_id,
                last_seen_at=GREATEST(
                    entity_identity.last_seen_at,EXCLUDED.last_seen_at
                )
            """,
            (
                entity_id,
                purl,
                self.artifact_id,
                self.payload.effective_at,
                self.payload.effective_at,
            ),
        )

    def _upsert_url_identity(self, entity_id: UUID, url: str) -> None:
        self.connection.execute(
            """
            INSERT INTO entity_identity(
              tenant_id,entity_id,scheme,identity_value,is_canonical,
              source_artifact_id,first_seen_at,last_seen_at
            ) VALUES (NULL,%s,'URL',%s,true,%s,%s,%s)
            ON CONFLICT(tenant_id,scheme,identity_value) DO UPDATE
            SET entity_id=EXCLUDED.entity_id,is_canonical=true,
                source_artifact_id=EXCLUDED.source_artifact_id,
                last_seen_at=GREATEST(
                    entity_identity.last_seen_at,EXCLUDED.last_seen_at
                )
            """,
            (
                entity_id,
                url,
                self.artifact_id,
                self.payload.effective_at,
                self.payload.effective_at,
            ),
        )

    def _upsert_registry_identity(
        self,
        entity_id: UUID,
        record: NpmCatalogRecord,
        *,
        version: str | None,
    ) -> None:
        purl = record.package_purl if version is None else record.version_purl
        self.connection.execute(
            """
            INSERT INTO package_registry_identity(
              tenant_id,entity_id,package_registry_id,package_name,package_version,
              purl,visibility,first_seen_at,last_seen_at
            ) VALUES (NULL,%s,%s,%s,%s,%s,'PUBLIC',%s,%s)
            ON CONFLICT(package_registry_id,package_name,package_version) DO UPDATE
            SET entity_id=EXCLUDED.entity_id,purl=EXCLUDED.purl,visibility='PUBLIC',
                last_seen_at=GREATEST(
                    package_registry_identity.last_seen_at,EXCLUDED.last_seen_at
                )
            """,
            (
                entity_id,
                self.registry_id,
                record.package.name,
                version,
                purl,
                self.payload.effective_at,
                self.payload.effective_at,
            ),
        )

    def _insert_fact(
        self,
        *,
        subject_id: UUID,
        predicate: str,
        logical_scope: str,
        row_number: int,
        object_entity_id: UUID | None = None,
        object_value: JsonObject | None = None,
    ) -> None:
        logical_key = sha256_key(SOURCE_KEY, logical_scope)
        idempotency_key = sha256_key(
            logical_key,
            self.payload.source_revision,
            EXTRACTOR_KEY,
            EXTRACTOR_VERSION,
        )
        row = self.connection.execute(
            """
            INSERT INTO fact_assertion(
              tenant_id,source_snapshot_id,subject_entity_id,predicate,
              object_entity_id,object_value,assertion_class,confidence,
              logical_key,idempotency_key,source_revision,extractor_key,
              extractor_version,properties,effective_from,observed_at
            ) VALUES (
              NULL,%s,%s,%s,%s,%s,'EXTERNAL_MEASURED',1.0,%s,%s,%s,%s,%s,%s,%s,%s
            ) RETURNING id
            """,
            (
                self.snapshot_id,
                subject_id,
                predicate,
                object_entity_id,
                Jsonb(object_value) if object_value is not None else None,
                logical_key,
                idempotency_key,
                self.payload.source_revision,
                EXTRACTOR_KEY,
                EXTRACTOR_VERSION,
                Jsonb({"dataset_id": DATASET_ID, "source_row_number": row_number}),
                self.payload.effective_at,
                self.payload.observed_at,
            ),
        ).fetchone()
        assert row is not None
        self.connection.execute(
            """
            INSERT INTO evidence(
              tenant_id,fact_assertion_id,source_artifact_id,evidence_type,
              locator,excerpt_hash,metadata,observed_at
            ) VALUES (NULL,%s,%s,'DATASET_ROW',%s,%s,%s,%s)
            """,
            (
                row["id"],
                self.artifact_id,
                Jsonb(
                    {
                        "uri": self.payload.source_uri,
                        "row_number": row_number,
                        "dataset_id": DATASET_ID,
                    }
                ),
                sha256_key(object_value or logical_scope),
                Jsonb({"dataset_id": DATASET_ID}),
                self.payload.observed_at,
            ),
        )
        self.fact_count += 1

    def _stats(self) -> JsonObject:
        return {
            "row_count": len(self.records),
            "project_count": len(self.projects),
            "package_count": len(self.packages),
            "version_count": len(self.versions),
            "repository_count": len(self.repositories),
            "fact_count": self.fact_count,
        }

    def _result(self, *, replayed: bool, stats: Mapping[str, Any]) -> ImportResult:
        if "stats" in stats and isinstance(stats["stats"], Mapping):
            stats = stats["stats"]
        return ImportResult(
            dataset_id=DATASET_ID,
            source_revision=self.payload.source_revision,
            replayed=replayed,
            row_count=int(stats.get("row_count", len(self.records))),
            project_count=int(stats.get("project_count", 0)),
            package_count=int(stats.get("package_count", 0)),
            version_count=int(stats.get("version_count", 0)),
            repository_count=int(stats.get("repository_count", 0)),
            fact_count=int(stats.get("fact_count", 0)),
        )


def import_dataset(database_url: str, payload: DatasetPayload) -> ImportResult:
    records = parse_dataset(payload.content)
    with psycopg.connect(database_url, row_factory=dict_row) as connection:
        return OssCatalogImporter(connection, payload, records).run()


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text or text.lower() in {"null", "none", "nan"}:
        return None
    return text


def _nonnegative_int(
    value: object,
    field: str,
    row_number: int,
    *,
    optional: bool = False,
) -> int | None:
    text = _optional_text(value)
    if text is None:
        if optional:
            return None
        raise ValueError(f"row {row_number} has no {field}")
    try:
        number = float(text.replace(",", ""))
    except ValueError as error:
        raise ValueError(f"row {row_number} has invalid {field}: {text!r}") from error
    if number < 0 or not number.is_integer():
        raise ValueError(f"row {row_number} has invalid {field}: {text!r}")
    return int(number)


def _size_bytes(value: object, row_number: int) -> int | None:
    text = _optional_text(value)
    if text is None:
        return None
    match = SIZE_PATTERN.fullmatch(text)
    if match is None:
        raise ValueError(f"row {row_number} has invalid unpacked_size: {text!r}")
    return round(float(match.group(1)) * SIZE_MULTIPLIERS[match.group(2).lower()])


def _validated_optional_url(value: object, field: str, row_number: int) -> str | None:
    text = _optional_text(value)
    if text is None:
        return None
    parsed = urlsplit(text)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError(f"row {row_number} has invalid {field}: {text!r}")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError(f"row {row_number} has credentialed {field}")
    return text


def _package_name_from_url(value: object) -> str | None:
    text = _optional_text(value)
    if text is None:
        return None
    parsed = urlsplit(text)
    if parsed.hostname not in {"npmjs.com", "www.npmjs.com"}:
        return None
    prefix = "/package/"
    if not parsed.path.startswith(prefix):
        return None
    name = unquote(parsed.path[len(prefix) :]).strip("/")
    return name or None


def _normalize_repository_url(value: object, row_number: int) -> str | None:
    text = _validated_optional_url(value, "repository", row_number)
    if text is None:
        return None
    parsed = urlsplit(text)
    host = parsed.hostname.lower() if parsed.hostname else ""
    path = parsed.path.rstrip("/")
    if path.endswith(".git"):
        path = path[:-4]
    return urlunsplit((parsed.scheme.lower(), host, path, "", ""))


def _repository_name(url: str) -> str:
    parsed = urlsplit(url)
    parts = [part for part in parsed.path.split("/") if part]
    if len(parts) >= 2:
        return f"{parts[-2]}/{parts[-1]}"
    return parts[-1] if parts else parsed.netloc


def _validate_dataset_url(url: str) -> None:
    parsed = urlsplit(url)
    if parsed.scheme != "https" or parsed.hostname != "huggingface.co":
        raise ValueError("dataset URL must use HTTPS on huggingface.co")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("dataset URL must not contain credentials")
    allowed_prefixes = (
        f"/datasets/{DATASET_ID}/",
        f"/api/resolve-cache/datasets/{DATASET_ID}/",
    )
    if not parsed.path.startswith(allowed_prefixes):
        raise ValueError(f"dataset URL must reference {DATASET_ID}")


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("observed_at must include a timezone")
    return value.astimezone(timezone.utc)


def _parse_observed_at(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return _as_utc(parsed)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Import the Hugging Face top npm dataset into the OSS catalog"
    )
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--csv-file", type=Path)
    source.add_argument("--dataset-url", default=DEFAULT_DATASET_URL)
    parser.add_argument(
        "--effective-at",
        help=(
            "effective UTC timestamp for a local CSV "
            f"(defaults to {DATASET_EFFECTIVE_AT.isoformat()})"
        ),
    )
    arguments = parser.parse_args()
    database_url = os.environ.get("STACKGRAPH_DATABASE_URL")
    if not database_url:
        parser.error("STACKGRAPH_DATABASE_URL is required")

    if arguments.csv_file is not None:
        effective_at = (
            _parse_observed_at(arguments.effective_at)
            if arguments.effective_at
            else DATASET_EFFECTIVE_AT
        )
        payload = load_dataset_file(
            arguments.csv_file,
            observed_at=datetime.now(timezone.utc),
            effective_at=effective_at,
        )
    else:
        if arguments.effective_at:
            parser.error("--effective-at can only be used with --csv-file")
        payload = fetch_dataset(arguments.dataset_url)
    result = import_dataset(database_url, payload)
    print(json.dumps(result.as_dict(), sort_keys=True))


if __name__ == "__main__":
    main()
