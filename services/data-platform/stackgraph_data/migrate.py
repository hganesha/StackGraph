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


MIGRATION_FILENAME = re.compile(r"^[0-9]{3}_[a-z0-9]+(?:_[a-z0-9]+)*\.sql$")


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

    return MigrationResult(applied=applied, skipped=skipped)


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
