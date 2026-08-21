from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
from dataclasses import asdict, dataclass
from pathlib import Path

import psycopg


@dataclass(frozen=True, slots=True)
class MigrationResult:
    applied: list[str]
    skipped: list[str]
    accepted_legacy: list[str]


MIGRATION_FILENAME = re.compile(r"^[0-9]{3}_[a-z0-9]+(?:_[a-z0-9]+)*\.sql$")
LEGACY_DEPENDENCY_USAGE_VERSION = "005_dependency_usage_analysis.sql"
LEGACY_DEPENDENCY_USAGE_CHECKSUM = (
    "8469299e4dd376a36ece0bbfdde5ee3fac9d094b95145db09939c208ed5366bd"
)
CANONICAL_DEPENDENCY_USAGE_CHECKSUM = (
    "98263f1f32158e24b75518348dbe26bf66d68cd5d0d5e01596496850b9d08e74"
)

_DEPENDENCY_USAGE_COLUMNS = {
    ("package_api_surface", "id", "uuid"),
    ("package_api_surface", "tenant_id", "uuid"),
    ("package_api_surface", "package_version_entity_id", "uuid"),
    ("package_api_surface", "ecosystem", "text"),
    ("package_api_surface", "artifact_checksum", "text"),
    ("package_api_surface", "analyzer_key", "text"),
    ("package_api_surface", "analyzer_version", "text"),
    ("package_api_surface", "analysis_fingerprint", "text"),
    ("package_api_surface", "public_symbol_count", "int4"),
    ("package_api_surface", "symbols", "jsonb"),
    ("package_api_surface", "completeness", "text"),
    ("package_api_surface", "limitations", "jsonb"),
    ("package_api_surface", "stats", "jsonb"),
    ("package_api_surface", "analyzed_at", "timestamptz"),
    ("dependency_usage_summary", "id", "uuid"),
    ("dependency_usage_summary", "tenant_id", "uuid"),
    ("dependency_usage_summary", "source_snapshot_id", "uuid"),
    ("dependency_usage_summary", "dependency_fact_assertion_id", "uuid"),
    ("dependency_usage_summary", "declared", "bool"),
    ("dependency_usage_summary", "resolved", "bool"),
    ("dependency_usage_summary", "referenced", "bool"),
    ("dependency_usage_summary", "static_reachability", "text"),
    ("dependency_usage_summary", "runtime_observed", "text"),
    ("dependency_usage_summary", "reference_count", "int4"),
    ("dependency_usage_summary", "referenced_symbols", "jsonb"),
    ("dependency_usage_summary", "source_files_scanned", "int4"),
    ("dependency_usage_summary", "limitations", "jsonb"),
    ("dependency_usage_summary", "analysis_fingerprint", "text"),
    ("dependency_usage_summary", "created_at", "timestamptz"),
}


def legacy_checksum_candidate(version: str, applied_checksum: str, file_checksum: str) -> bool:
    return (
        version == LEGACY_DEPENDENCY_USAGE_VERSION
        and applied_checksum == LEGACY_DEPENDENCY_USAGE_CHECKSUM
        and file_checksum == CANONICAL_DEPENDENCY_USAGE_CHECKSUM
    )


def _legacy_dependency_usage_schema_is_compatible(connection: psycopg.Connection) -> bool:
    column_rows = connection.execute(
        """
        SELECT table_name,column_name,udt_name
        FROM information_schema.columns
        WHERE table_schema='public'
          AND table_name IN ('package_api_surface','dependency_usage_summary')
        """
    ).fetchall()
    actual_columns = {(row[0], row[1], row[2]) for row in column_rows}
    if not _DEPENDENCY_USAGE_COLUMNS <= actual_columns:
        return False

    relation_row = connection.execute(
        """
        SELECT
          to_regclass('public.idx_package_api_surface_lookup') IS NOT NULL,
          to_regclass('public.idx_dependency_usage_snapshot') IS NOT NULL,
          coalesce((SELECT relrowsecurity FROM pg_class
                    WHERE oid=to_regclass('public.package_api_surface')),false),
          coalesce((SELECT relrowsecurity FROM pg_class
                    WHERE oid=to_regclass('public.dependency_usage_summary')),false),
          (SELECT count(*)=2 FROM pg_policies
           WHERE schemaname='public' AND policyname='tenant_isolation'
             AND tablename IN ('package_api_surface','dependency_usage_summary'))
        """
    ).fetchone()
    if relation_row is None or not all(relation_row):
        return False

    constraint_rows = connection.execute(
        """
        SELECT conrelid::regclass::text,pg_get_constraintdef(oid)
        FROM pg_constraint
        WHERE conrelid IN (
          'public.package_api_surface'::regclass,
          'public.dependency_usage_summary'::regclass
        )
        """
    ).fetchall()
    constraints = " ".join(
        re.sub(r"\s+", " ", f"{row[0]} {row[1]}").lower()
        for row in constraint_rows
    )
    for required in (
        "unique nulls not distinct (tenant_id, package_version_entity_id, artifact_checksum, analyzer_key, analyzer_version)",
        "unique (dependency_fact_assertion_id)",
    ):
        if required not in constraints:
            return False
    if not any(
        fingerprint_constraint in constraints
        for fingerprint_constraint in (
            "unique (analysis_fingerprint)",
            "unique nulls not distinct (tenant_id, analysis_fingerprint)",
        )
    ):
        return False

    function_row = connection.execute(
        "SELECT pg_get_functiondef(to_regprocedure('public.publish_source_snapshot(uuid)'))"
    ).fetchone()
    if function_row is None or function_row[0] is None:
        return False
    function_definition = re.sub(r"\s+", "", function_row[0]).lower()
    return all(
        marker in function_definition
        for marker in (
            "old.extractor_key=s.extractor_key",
            "old.id<>s.id",
            "'close'",
            "closed_by_source_snapshot_id",
        )
    )


def legacy_migration_is_compatible(
    connection: psycopg.Connection,
    version: str,
    applied_checksum: str,
    checksum: str,
) -> bool:
    if not legacy_checksum_candidate(version, applied_checksum, checksum):
        return False
    return _legacy_dependency_usage_schema_is_compatible(connection)


def file_checksum(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def migration_paths(migrations_dir: Path) -> list[Path]:
    return sorted(
        path
        for path in migrations_dir.glob("*.sql")
        if MIGRATION_FILENAME.fullmatch(path.name)
    )


def apply_migrations(database_url: str, migrations_dir: Path) -> MigrationResult:
    paths = migration_paths(migrations_dir)
    applied: list[str] = []
    skipped: list[str] = []
    accepted_legacy: list[str] = []

    with psycopg.connect(database_url) as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_migration (
                version text PRIMARY KEY,
                checksum text NOT NULL CHECK (checksum ~ '^[a-f0-9]{64}$'),
                applied_at timestamptz NOT NULL DEFAULT now()
            )
            """
        )

        for path in paths:
            version = path.name
            checksum = file_checksum(path)
            row = connection.execute(
                "SELECT checksum FROM schema_migration WHERE version = %s",
                (version,),
            ).fetchone()
            if row is not None:
                if row[0] != checksum:
                    if legacy_migration_is_compatible(connection, version, row[0], checksum):
                        accepted_legacy.append(version)
                    else:
                        raise RuntimeError(
                            f"applied migration {version} has checksum {row[0]}, "
                            f"but the file has {checksum}"
                        )
                skipped.append(version)
                continue

            with connection.transaction():
                connection.execute(path.read_text(encoding="utf-8"))
                connection.execute(
                    "INSERT INTO schema_migration (version, checksum) VALUES (%s, %s)",
                    (version, checksum),
                )
            applied.append(version)

    return MigrationResult(
        applied=applied,
        skipped=skipped,
        accepted_legacy=accepted_legacy,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Apply StackGraph database migrations")
    parser.add_argument(
        "--migrations-dir",
        type=Path,
        default=Path(
            os.environ.get("STACKGRAPH_MIGRATIONS_DIR", "/migrations")
        ),
    )
    args = parser.parse_args()
    database_url = os.environ.get("STACKGRAPH_DATABASE_URL")
    if not database_url:
        parser.error("STACKGRAPH_DATABASE_URL is required")

    result = apply_migrations(database_url, args.migrations_dir)
    print(json.dumps(asdict(result), sort_keys=True))


if __name__ == "__main__":
    main()
