from __future__ import annotations

import argparse
import ast
import hashlib
import json
import re
import sys
import time
import tomllib
import yaml
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Iterable, Mapping
from urllib.parse import quote, urlsplit

from .github_snapshot import manifest_kind
from .npm_resolution import (
    PUBLIC_NPM_ORIGIN,
    NpmConfig,
    normalize_registry_origin,
    parse_npmrc,
    resolve_npm_dependency,
)


SCANNER_KEY = "repository-dependency-usage"
SCANNER_VERSION = "1.11.0"
HTTP_METHODS = frozenset({"get", "put", "post", "delete", "options", "head", "patch", "trace"})
PYPI_NORMALIZE = re.compile(r"[-_.]+")
REQUIREMENT = re.compile(
    r"^\s*([A-Za-z0-9][A-Za-z0-9._-]*)(?:\[[^\]]+\])?\s*([^;\s]+)?"
)
JS_IMPORT = re.compile(
    r"(?:import\s+(?P<clause>[^;\n]*?)\s+from\s+|import\s*\(|require\s*\()"
    r"[\"'](?P<module>[^\"']+)[\"']"
)
JS_SIDE_EFFECT_IMPORT = re.compile(r"import\s*[\"'](?P<module>[^\"']+)[\"']")
JS_REQUIRE_DESTRUCTURE = re.compile(
    r"(?:const|let|var)\s*\{(?P<symbols>[^}]+)\}\s*=\s*require\s*\(\s*"
    r"[\"'](?P<module>[^\"']+)[\"']\s*\)"
)
JS_REQUIRE_MEMBER = re.compile(
    r"require\s*\(\s*[\"'](?P<module>[^\"']+)[\"']\s*\)\.(?P<symbol>[A-Za-z_$][\w$]*)"
)
JS_LOCAL_IMPORT = re.compile(
    r"(?:from\s+|import\s*\(|require\s*\()\s*[\"'](?P<module>\.{1,2}/[^\"']+)[\"']"
)
JS_EXPORT = re.compile(
    r"(?:export\s+(?:declare\s+)?(?:async\s+)?(?:function|class|const|let|var|interface|type|enum)\s+"
    r"|exports\.)([A-Za-z_$][\w$]*)"
)
JS_FUNCTION = re.compile(
    r"(?:export\s+)?(?:default\s+)?(?:async\s+)?function\s+"
    r"(?P<name>[A-Za-z_$][\w$]*)\s*\([^)]*\)\s*\{"
)
JS_ARROW_FUNCTION = re.compile(
    r"(?:export\s+)?(?:const|let|var)\s+(?P<name>[A-Za-z_$][\w$]*)\s*=\s*"
    r"(?:async\s*)?(?:\([^)]*\)|[A-Za-z_$][\w$]*)\s*=>\s*\{"
)
IDENTIFIER_PART = re.compile(r"[A-Z]?[a-z]+|[A-Z]+(?=[A-Z]|$)|[0-9]+")
SHA256_CONTENT_HASH = re.compile(r"^sha256:[a-f0-9]{64}$")
README_SUFFIXES = {"", ".md", ".markdown", ".mdown", ".rst", ".txt"}
LANGUAGE_LABELS = {
    ".js": "JavaScript", ".jsx": "JavaScript", ".mjs": "JavaScript", ".cjs": "JavaScript",
    ".ts": "TypeScript", ".tsx": "TypeScript", ".mts": "TypeScript", ".cts": "TypeScript",
    ".py": "Python",
}


@dataclass(frozen=True, slots=True)
class ResourceTechnology:
    entity_type: str
    key: str
    name: str
    engine: str
    provider: str | None = None


POSTGRESQL = ResourceTechnology(
    "Database", "stackgraph:database:postgresql", "PostgreSQL", "postgresql",
)
MYSQL = ResourceTechnology(
    "Database", "stackgraph:database:mysql", "MySQL / MariaDB", "mysql",
)
MONGODB = ResourceTechnology(
    "Database", "stackgraph:database:mongodb", "MongoDB", "mongodb",
)
REDIS = ResourceTechnology(
    "Database", "stackgraph:database:redis-valkey", "Redis / Valkey", "redis",
)
SQLITE = ResourceTechnology(
    "Database", "stackgraph:database:sqlite", "SQLite", "sqlite",
)
DYNAMODB = ResourceTechnology(
    "Database", "stackgraph:database:amazon-dynamodb", "Amazon DynamoDB", "dynamodb", "aws",
)
RDS = ResourceTechnology(
    "Database", "stackgraph:database:amazon-rds", "Amazon RDS", "rds", "aws",
)
GOOGLE_CLOUD_SQL = ResourceTechnology(
    "Database", "stackgraph:database:google-cloud-sql", "Google Cloud SQL", "cloud-sql", "gcp",
)
COSMOS_DB = ResourceTechnology(
    "Database", "stackgraph:database:azure-cosmos-db", "Azure Cosmos DB", "cosmos-db", "azure",
)
AMAZON_S3 = ResourceTechnology(
    "Storage", "stackgraph:storage:amazon-s3", "Amazon S3", "s3", "aws",
)
S3_COMPATIBLE = ResourceTechnology(
    "Storage", "stackgraph:storage:s3-compatible", "S3-compatible object storage", "s3-compatible",
)
GOOGLE_CLOUD_STORAGE = ResourceTechnology(
    "Storage", "stackgraph:storage:google-cloud-storage", "Google Cloud Storage", "gcs", "gcp",
)
AZURE_BLOB_STORAGE = ResourceTechnology(
    "Storage", "stackgraph:storage:azure-blob", "Azure Blob Storage", "azure-blob", "azure",
)


RESOURCE_DEPENDENCIES: dict[tuple[str, str], ResourceTechnology] = {
    ("pypi", "psycopg"): POSTGRESQL,
    ("pypi", "psycopg2"): POSTGRESQL,
    ("pypi", "psycopg2-binary"): POSTGRESQL,
    ("pypi", "asyncpg"): POSTGRESQL,
    ("pypi", "pymysql"): MYSQL,
    ("pypi", "mysqlclient"): MYSQL,
    ("pypi", "mysql-connector-python"): MYSQL,
    ("pypi", "aiomysql"): MYSQL,
    ("pypi", "pymongo"): MONGODB,
    ("pypi", "motor"): MONGODB,
    ("pypi", "redis"): REDIS,
    ("pypi", "aiosqlite"): SQLITE,
    ("pypi", "minio"): S3_COMPATIBLE,
    ("pypi", "google-cloud-storage"): GOOGLE_CLOUD_STORAGE,
    ("pypi", "azure-storage-blob"): AZURE_BLOB_STORAGE,
    ("npm", "pg"): POSTGRESQL,
    ("npm", "postgres"): POSTGRESQL,
    ("npm", "mysql"): MYSQL,
    ("npm", "mysql2"): MYSQL,
    ("npm", "mongodb"): MONGODB,
    ("npm", "mongoose"): MONGODB,
    ("npm", "redis"): REDIS,
    ("npm", "ioredis"): REDIS,
    ("npm", "sqlite3"): SQLITE,
    ("npm", "better-sqlite3"): SQLITE,
    ("npm", "@aws-sdk/client-s3"): AMAZON_S3,
    ("npm", "minio"): S3_COMPATIBLE,
    ("npm", "@google-cloud/storage"): GOOGLE_CLOUD_STORAGE,
    ("npm", "@azure/storage-blob"): AZURE_BLOB_STORAGE,
}

URL_SCHEME_RESOURCES: tuple[tuple[re.Pattern[str], ResourceTechnology, str], ...] = (
    (re.compile(r"\bpostgres(?:ql)?(?:\+[a-z0-9_-]+)?://", re.I), POSTGRESQL, "postgresql"),
    (re.compile(r"\bmysql(?:\+[a-z0-9_-]+)?://", re.I), MYSQL, "mysql"),
    (re.compile(r"\bmongodb(?:\+srv)?://", re.I), MONGODB, "mongodb"),
    (re.compile(r"\brediss?://", re.I), REDIS, "redis"),
    (re.compile(r"\bsqlite(?:\+[a-z0-9_-]+)?:(?://)?", re.I), SQLITE, "sqlite"),
    (re.compile(r"\bs3://", re.I), AMAZON_S3, "s3"),
)

CONFIG_KEY_RESOURCES: tuple[tuple[re.Pattern[str], ResourceTechnology], ...] = (
    (re.compile(r"^(?:[A-Z0-9]+_)*(?:POSTGRES(?:QL)?(?:_(?:URL|URI|HOST|PORT|DATABASE|DB|USER|USERNAME|PASSWORD|DSN|SERVICE))?|PGHOST|PGPORT|PGDATABASE|PGUSER|PGPASSWORD|PGSERVICE)$"), POSTGRESQL),
    (re.compile(r"^(?:[A-Z0-9]+_)*(?:MYSQL|MARIADB)(?:_(?:URL|URI|HOST|PORT|DATABASE|DB|USER|USERNAME|PASSWORD|DSN))?$"), MYSQL),
    (re.compile(r"^(?:[A-Z0-9]+_)*(?:MONGO|MONGODB)(?:_(?:URL|URI|HOST|PORT|DATABASE|DB|USER|USERNAME|PASSWORD|DSN))?$"), MONGODB),
    (re.compile(r"^(?:[A-Z0-9]+_)*(?:REDIS|VALKEY)(?:_(?:URL|URI|HOST|PORT|DATABASE|DB|USER|USERNAME|PASSWORD))?$"), REDIS),
    (re.compile(r"^(?:[A-Z0-9]+_)*SQLITE(?:_(?:URL|URI|PATH|DATABASE|DB))?$"), SQLITE),
    (re.compile(r"^(?:[A-Z0-9]+_)*DYNAMODB(?:_(?:URL|URI|ENDPOINT|TABLE|REGION))?$"), DYNAMODB),
    (re.compile(r"^(?:[A-Z0-9]+_)*(?:AWS_)?S3(?:_(?:URL|URI|ENDPOINT|BUCKET|PREFIX|REGION|ACCESS_KEY|SECRET_KEY|KMS_KEY_ID|PROFILE))?$"), AMAZON_S3),
    (re.compile(r"^(?:[A-Z0-9]+_)*MINIO(?:_(?:URL|URI|ENDPOINT|BUCKET|REGION|ROOT_USER|ROOT_PASSWORD|ACCESS_KEY|SECRET_KEY))?$"), S3_COMPATIBLE),
    (re.compile(r"^(?:[A-Z0-9]+_)*(?:GCS|GOOGLE_CLOUD_STORAGE)(?:_(?:URL|URI|ENDPOINT|BUCKET|PROJECT|REGION|CREDENTIALS))?$"), GOOGLE_CLOUD_STORAGE),
    (re.compile(r"^(?:[A-Z0-9]+_)*(?:AZURE_STORAGE|AZURE_BLOB)(?:_(?:URL|URI|ENDPOINT|ACCOUNT|CONTAINER|CREDENTIALS|CONNECTION_STRING))?$"), AZURE_BLOB_STORAGE),
)

GENERIC_DATABASE_CONFIG_KEYS = {"DATABASE_URL", "DB_URL", "DATABASE_URI", "DB_URI"}
GENERIC_STORAGE_CONFIG_KEYS = {"STORAGE_URL", "BLOB_URL", "BUCKET_NAME"}
CONFIG_KEY = re.compile(r"\b[A-Z][A-Z0-9_]{2,}\b")
COMPOSE_FILE = re.compile(r"^(?:docker-)?compose(?:\.[a-z0-9_-]+)*\.ya?ml$", re.I)

TERRAFORM_RESOURCE_TECHNOLOGIES: dict[str, ResourceTechnology] = {
    "aws_s3_bucket": AMAZON_S3,
    "aws_s3_object": AMAZON_S3,
    "aws_dynamodb_table": DYNAMODB,
    "aws_db_instance": RDS,
    "aws_rds_cluster": RDS,
    "google_storage_bucket": GOOGLE_CLOUD_STORAGE,
    "google_storage_bucket_object": GOOGLE_CLOUD_STORAGE,
    "google_sql_database_instance": GOOGLE_CLOUD_SQL,
    "azurerm_storage_account": AZURE_BLOB_STORAGE,
    "azurerm_storage_container": AZURE_BLOB_STORAGE,
    "azurerm_storage_blob": AZURE_BLOB_STORAGE,
    "azurerm_cosmosdb_account": COSMOS_DB,
}


def canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_key(*parts: object) -> str:
    payload = "\x1f".join(part if isinstance(part, str) else canonical_json(part) for part in parts)
    return f"sha256:{hashlib.sha256(payload.encode('utf-8')).hexdigest()}"


def content_hash(content: bytes) -> str:
    return f"sha256:{hashlib.sha256(content).hexdigest()}"


@dataclass(frozen=True, slots=True)
class Diagnostic:
    severity: str
    code: str
    message: str
    path: str | None = None
    details: Mapping[str, Any] | None = None

    def as_dict(self) -> dict[str, Any]:
        value: dict[str, Any] = {
            "severity": self.severity,
            "code": self.code,
            "message": self.message,
        }
        if self.path is not None:
            value["path"] = self.path
        if self.details is not None:
            value["details"] = dict(self.details)
        return value


@dataclass(frozen=True, slots=True)
class Evidence:
    path: str
    evidence_type: str
    content_hash: str
    locator: Mapping[str, Any]
    excerpt_hash: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def as_dict(
        self,
        repository_key: str,
        source_revision: str,
        snapshot_blob_uri: str | None = None,
    ) -> dict[str, Any]:
        source_artifact: dict[str, Any] = {
            "key": f"{repository_key}:{self.path}",
            "type": "REPOSITORY_FILE",
            "revision": source_revision,
            "content_hash": self.content_hash,
        }
        if snapshot_blob_uri is not None:
            source_artifact["uri"] = (
                f"{snapshot_blob_uri}#path=files/{quote(self.path, safe='/')}"
            )
        value: dict[str, Any] = {
            "type": self.evidence_type,
            "source_artifact": source_artifact,
            "locator": dict(self.locator),
        }
        if self.excerpt_hash is not None:
            value["excerpt_hash"] = self.excerpt_hash
        if self.metadata:
            value["metadata"] = dict(self.metadata)
        return value


@dataclass(frozen=True, slots=True)
class ResourceSignal:
    resource: ResourceTechnology
    evidence: Evidence
    signal_kind: str
    confidence: float
    assertion_class: str = "INFERRED"
    package: str | None = None
    config_key: str | None = None
    provider: str | None = None
    detail: str | None = None


@dataclass(slots=True)
class Reference:
    ecosystem: str
    package_name: str
    path: str
    line: int
    symbols: set[str] = field(default_factory=set)


@dataclass(frozen=True, slots=True)
class CodeUnit:
    language: str
    symbol_kind: str
    qualified_name: str
    path: str
    line_start: int
    line_end: int
    structural_fingerprint: str
    semantic_tokens: tuple[str, ...]
    dependency_keys: tuple[str, ...]
    covering_tests: tuple[str, ...]
    dynamic_signals: tuple[str, ...]
    touchpoints: tuple[Mapping[str, str], ...]
    vendored: bool
    vendored_package_key: str | None = None
    vendored_package_version: str | None = None
    vendored_identity_source: str | None = None


@dataclass(frozen=True, slots=True)
class OpenApiDefinition:
    path: str
    line: int
    title: str
    metadata: Mapping[str, Any]


@dataclass(slots=True)
class Dependency:
    ecosystem: str
    name: str
    requested_spec: str
    scope: str
    direct: bool
    component_path: str
    declaration: Evidence
    resolved_version: str | None = None
    resolution_evidence: Evidence | None = None
    registry_properties: Mapping[str, Any] | None = None
    artifact_properties: Mapping[str, Any] | None = None

    @property
    def normalized_name(self) -> str:
        return normalize_package_name(self.ecosystem, self.name)

    @property
    def package_purl(self) -> str:
        encoded = quote(self.normalized_name, safe="/" if self.ecosystem == "npm" else "")
        return f"pkg:{self.ecosystem}/{encoded}"

    @property
    def entity_key(self) -> str:
        if self.resolved_version:
            version = quote(self.resolved_version, safe=".-_~+")
            public_key = f"{self.package_purl}@{version}"
        else:
            public_key = self.package_purl
        registry = self.registry_properties or {}
        if registry.get("visibility") in {"PRIVATE", "UNKNOWN"} and registry.get("custom_registry"):
            origin = str(registry.get("origin") or "")
            registry_key = f"npm-{hashlib.sha256(origin.encode()).hexdigest()[:16]}"
            return f"registry:{registry_key}:{public_key}"
        return public_key

    @property
    def entity_type(self) -> str:
        return "PackageVersion" if self.resolved_version else "Package"


@dataclass(frozen=True, slots=True)
class ScanInput:
    run_id: str
    tenant_key: str
    repository_key: str
    repository_name: str
    source_revision: str
    checkout_root: Path
    observed_at: str
    snapshot_blob_uri: str | None
    snapshot_content_hash: str | None
    snapshot_content_size_bytes: int | None
    max_files: int
    max_bytes: int
    deadline_seconds: int


def _evidence_dict(evidence: Evidence, scan_input: ScanInput) -> dict[str, Any]:
    return evidence.as_dict(
        scan_input.repository_key,
        scan_input.source_revision,
        scan_input.snapshot_blob_uri,
    )


def scan_repository(request: Mapping[str, Any]) -> dict[str, Any]:
    started = time.monotonic()
    scan_input = _parse_request(request)
    diagnostics: list[Diagnostic] = []
    files, completeness, bytes_read = _discover_files(scan_input, diagnostics, started)
    contents: dict[str, bytes] = {}
    for relative, path in files.items():
        try:
            contents[relative] = path.read_bytes()
        except OSError as error:
            completeness = "PARTIAL"
            diagnostics.append(Diagnostic("ERROR", "FILE_READ_FAILED", type(error).__name__, relative))

    dependencies: list[Dependency] = []
    dependencies.extend(_scan_npm(contents, diagnostics))
    dependencies.extend(_scan_python(contents, diagnostics))
    dependencies = _dedupe_dependencies(dependencies)
    runtime = _runtime_observations(contents, diagnostics)
    inventory_facts = _repository_profile_facts(scan_input, contents)
    inventory_facts.extend(_component_facts(scan_input, contents, dependencies))
    inventory_facts.extend(_internal_package_publication_facts(
        scan_input, contents, diagnostics,
    ))
    inventory_facts.extend(_application_boundary_facts(scan_input, contents))
    inventory_facts.extend(_service_boundary_facts(scan_input, contents, diagnostics))
    inventory_facts.extend(_deployment_facts(scan_input, contents, diagnostics))
    pass_a_completed = time.monotonic()

    references, local_edges, entrypoints = _scan_sources(contents, dependencies, diagnostics)
    reachable_files = _reachable_files(contents, local_edges, entrypoints)
    code_units = _scan_code_units(contents, references, local_edges, diagnostics)
    if any(item.severity == "ERROR" for item in diagnostics):
        completeness = "PARTIAL"
    facts = list(inventory_facts)
    facts.extend(_database_storage_facts(
        scan_input, contents, dependencies, references,
    ))
    facts.extend(_dependency_facts(
        scan_input,
        dependencies,
        references,
        reachable_files,
        runtime,
        completeness,
        source_file_count=sum(1 for path in contents if _is_source(path)),
    ))
    facts.extend(_component_dependency_facts(
        scan_input,
        dependencies,
        references,
        reachable_files,
        runtime,
        completeness,
        source_file_count=sum(1 for path in contents if _is_source(path)),
    ))
    facts.extend(
        _usage_findings(
            scan_input,
            dependencies,
            references,
            reachable_files,
            runtime,
            completeness,
            source_file_count=sum(1 for path in contents if _is_source(path)),
        )
    )
    facts.extend(_code_unit_facts(scan_input, code_units))
    facts.extend(_repository_fingerprint_facts(scan_input, facts, contents))
    service_keys = {
        entity["key"]
        for fact in facts
        for entity in (fact.get("subject"), fact.get("object_entity"))
        if isinstance(entity, Mapping) and entity.get("type") == "Service"
    }
    api_keys = {
        entity["key"]
        for fact in facts
        for entity in (fact.get("subject"), fact.get("object_entity"))
        if isinstance(entity, Mapping) and entity.get("type") == "API"
    }
    api_operations = sum(
        int(value.get("operation_count") or 0)
        for fact in facts
        if fact.get("predicate") == "HAS_PROPERTY"
        and isinstance((value := fact.get("object_value")), Mapping)
        and value.get("record_kind") == "openapi_service_profile"
    )
    material_findings = sum(
        fact.get("predicate") == "HAS_PROPERTY"
        and isinstance(fact.get("object_value"), Mapping)
        and bool(fact["object_value"].get("finding_type"))
        for fact in facts
    )
    duration_ms = max(0, int((time.monotonic() - started) * 1000))
    pass_a_ms = max(0, int((pass_a_completed - started) * 1000))
    return {
        "scanner_contract_version": "1.0.0",
        "run_id": scan_input.run_id,
        "source_revision": scan_input.source_revision,
        "extractor": {"key": SCANNER_KEY, "version": SCANNER_VERSION},
        "completeness": completeness,
        "facts": facts,
        "stats": {
            "files_seen": len(files),
            "files_scanned": len(contents),
            "facts_emitted": len(facts),
            "bytes_read": bytes_read,
            "duration_ms": duration_ms,
            "code_units_emitted": len(code_units),
            "pass_a_inventory_items": len(dependencies) + len(inventory_facts),
            "material_findings_emitted": material_findings,
            "services_discovered": len(service_keys),
            "api_contracts_discovered": len(api_keys),
            "api_operations_discovered": api_operations,
            "phase_timings_ms": {
                "pass_a_inventory": pass_a_ms,
                "pass_b_refinement": max(0, duration_ms - pass_a_ms),
            },
        },
        "diagnostics": [item.as_dict() for item in diagnostics],
    }


def _repository_fingerprint_facts(
    scan_input: ScanInput,
    facts: list[dict[str, Any]],
    contents: Mapping[str, bytes],
) -> list[dict[str, Any]]:
    """Summarize lower-level evidence without overriding or replacing direct facts."""
    profile = next((
        fact.get("object_value") for fact in facts
        if isinstance(fact.get("object_value"), Mapping)
        and fact["object_value"].get("record_kind") == "repository_profile"
    ), {})
    classifications = list(profile.get("classifications") or []) if isinstance(profile, Mapping) else []
    classification_labels = {str(item.get("classification")) for item in classifications}
    component_facts = [
        fact for fact in facts
        if fact.get("predicate") == "CONTAINS"
        and fact.get("subject", {}).get("type") == "Repository"
        and fact.get("object_entity", {}).get("type") == "Component"
    ]
    dependency_facts = [
        fact for fact in facts
        if fact.get("predicate") == "DEPENDS_ON"
        and fact.get("subject", {}).get("type") == "Component"
    ]
    deployment_facts = [
        fact for fact in facts
        if fact.get("predicate") in {"DEPLOYED_AS", "RUNS_ON", "BUILDS", "BASED_ON", "LOCATED_IN"}
    ]
    resource_facts = [
        fact for fact in facts
        if fact.get("predicate") == "USES"
        and fact.get("object_entity", {}).get("type") in {"Database", "Storage", "Queue"}
    ]
    architectures: list[dict[str, Any]] = []

    def archetype(key: str, label: str, confidence: float, contributions: list[str]) -> None:
        architectures.append({
            "key": key, "label": label, "classification": "STANDARD_ARCHETYPE",
            "confidence": confidence, "feature_contributions": contributions,
            "rule_version": "repository-archetype/1.0.0",
        })

    if "LIBRARY_PACKAGE" in classification_labels:
        archetype("library-package", "Library / package", 0.86, ["LIBRARY_PACKAGE classification"])
    if "MICROSERVICE" in classification_labels and deployment_facts:
        archetype(
            "containerized-service", "Containerized service", 0.84,
            ["API contract", "declared deployment", "container image relationship"],
        )
    if "INFRASTRUCTURE_AS_CODE" in classification_labels and not any(_is_source(path) for path in contents):
        archetype(
            "infrastructure-repository", "Infrastructure repository", 0.9,
            ["infrastructure-as-code", "no admitted application source files"],
        )
    if "DATA_ANALYTICS" in classification_labels and resource_facts:
        archetype(
            "data-platform", "Data platform", 0.78,
            ["data/analytics classification", "declared data resource relationships"],
        )
    source_fact_keys = sorted({str(fact["idempotency_key"]) for fact in facts})
    feature_payload = {
        "identity": {
            "repository_key": scan_input.repository_key,
            "repository_name": scan_input.repository_name,
            "source_revision": scan_input.source_revision,
        },
        "structure": {
            "component_count": len(component_facts),
            "source_file_count": sum(_is_source(path) for path in contents),
            "test_file_count": sum(_is_test_file(path) for path in contents),
        },
        "components": [
            {
                "key": fact["object_entity"]["key"],
                "path": fact["properties"].get("path"),
                "kind": fact["properties"].get("component_kind"),
            }
            for fact in component_facts
        ],
        "languages": list(profile.get("languages") or []) if isinstance(profile, Mapping) else [],
        "frameworks": sorted({
            framework for fact in component_facts
            for framework in fact.get("properties", {}).get("frameworks", [])
        }),
        "data_resources": sorted({
            fact["object_entity"]["key"] for fact in resource_facts
        }),
        "container_images": sorted({
            fact["object_entity"]["key"] for fact in deployment_facts
            if fact.get("object_entity", {}).get("type") == "ContainerImage"
        }),
        "deployment": {
            "relationship_count": len(deployment_facts),
            "profile": next((
                fact["object_value"] for fact in facts
                if isinstance(fact.get("object_value"), Mapping)
                and fact["object_value"].get("record_kind") == "deployment_profile"
            ), None),
        },
        "classifications": classifications,
        "architecture_archetypes": architectures,
        "dependency_count": len(dependency_facts),
        "activity": {"coverage": "NOT_AVAILABLE_TO_LOCAL_SCANNER"},
        "actor_mix": {"coverage": "NOT_AVAILABLE_TO_LOCAL_SCANNER"},
        "lifecycle": {"coverage": "NOT_COLLECTED"},
    }
    fingerprint = sha256_key("repository-fingerprint/1.0.0", feature_payload, source_fact_keys)
    value = {
        "record_kind": "repository_fingerprint",
        "schema_version": "1.0.0",
        "fingerprint": fingerprint,
        **feature_payload,
        "source_fact_keys": source_fact_keys,
        "confidence": 0.9 if component_facts else 0.7,
        "limitations": [
            "activity, actor mix, and lifecycle are joined asynchronously from connector evidence",
            "archetypes are omitted unless their direct feature threshold is met",
            "absence reflects scanner bounds and is not evidence of poor engineering performance",
        ],
    }
    evidence: list[dict[str, Any]] = []
    seen: set[str] = set()
    for fact in facts:
        for item in fact.get("evidence", []):
            key = canonical_json(item)
            if key not in seen:
                evidence.append(item)
                seen.add(key)
            if len(evidence) >= 30:
                break
        if len(evidence) >= 30:
            break
    if not evidence:
        return []
    return [{
        "fact_contract_version": "1.0.0",
        "idempotency_key": sha256_key({
            "tenant": scan_input.tenant_key,
            "repository": scan_input.repository_key,
            "record_kind": "repository_fingerprint",
            "fingerprint": fingerprint,
            "source_revision": scan_input.source_revision,
            "extractor": SCANNER_VERSION,
        }),
        "tenant_key": scan_input.tenant_key,
        "subject": _repository_ref(scan_input),
        "predicate": "HAS_PROPERTY",
        "object_value": value,
        "assertion_class": "INFERRED",
        "confidence": value["confidence"],
        "observed_at": scan_input.observed_at,
        "source_revision": scan_input.source_revision,
        "extractor": {"key": SCANNER_KEY, "version": SCANNER_VERSION},
        "properties": {"profile_schema_version": "1.0.0"},
        "evidence": evidence,
    }]


def _parse_request(request: Mapping[str, Any]) -> ScanInput:
    if request.get("scanner_contract_version") != "1.0.0":
        raise ValueError("scanner_contract_version must be 1.0.0")
    target = request.get("target")
    snapshot = request.get("snapshot")
    limits = request.get("limits")
    if not isinstance(target, Mapping) or not isinstance(snapshot, Mapping) or not isinstance(limits, Mapping):
        raise ValueError("scanner request requires target, snapshot, and limits objects")
    root = Path(str(snapshot.get("checkout_root") or "")).resolve()
    if not root.is_dir():
        raise ValueError("snapshot.checkout_root must be an existing directory")
    values = {
        "max_files": int(limits.get("max_files") or 0),
        "max_bytes": int(limits.get("max_bytes") or 0),
        "deadline_seconds": int(limits.get("deadline_seconds") or 0),
    }
    if any(value <= 0 for value in values.values()):
        raise ValueError("scanner limits must be positive")
    requested_at = str(snapshot.get("requested_at") or "")
    datetime.fromisoformat(requested_at.replace("Z", "+00:00"))
    descriptor_values = (
        snapshot.get("blob_uri"),
        snapshot.get("content_hash"),
        snapshot.get("content_size_bytes"),
    )
    if any(value is not None for value in descriptor_values) and not all(
        value is not None for value in descriptor_values
    ):
        raise ValueError(
            "snapshot.blob_uri, content_hash, and content_size_bytes must be supplied together"
        )
    snapshot_blob_uri: str | None = None
    snapshot_content_hash: str | None = None
    snapshot_content_size_bytes: int | None = None
    if all(value is not None for value in descriptor_values):
        snapshot_blob_uri = str(descriptor_values[0])
        parsed_uri = urlsplit(snapshot_blob_uri)
        if (
            not parsed_uri.scheme
            or not parsed_uri.netloc
            or parsed_uri.username is not None
            or parsed_uri.password is not None
            or parsed_uri.query
            or parsed_uri.fragment
        ):
            raise ValueError(
                "snapshot.blob_uri must be an absolute URI without credentials, query, or fragment"
            )
        snapshot_content_hash = str(descriptor_values[1])
        if not SHA256_CONTENT_HASH.fullmatch(snapshot_content_hash):
            raise ValueError("snapshot.content_hash must be a SHA-256 content hash")
        size = descriptor_values[2]
        if isinstance(size, bool) or not isinstance(size, int) or size < 0:
            raise ValueError("snapshot.content_size_bytes must be a non-negative integer")
        snapshot_content_size_bytes = size
    repository_name = str(target.get("name") or target.get("canonical_key") or "repository")
    return ScanInput(
        run_id=str(request.get("run_id") or ""),
        tenant_key=str(request.get("tenant_key") or ""),
        repository_key=str(target.get("canonical_key") or ""),
        repository_name=repository_name,
        source_revision=str(snapshot.get("source_revision") or ""),
        checkout_root=root,
        observed_at=requested_at,
        snapshot_blob_uri=snapshot_blob_uri,
        snapshot_content_hash=snapshot_content_hash,
        snapshot_content_size_bytes=snapshot_content_size_bytes,
        **values,
    )


def _discover_files(
    scan_input: ScanInput,
    diagnostics: list[Diagnostic],
    started: float,
) -> tuple[dict[str, Path], str, int]:
    selected: dict[str, Path] = {}
    total_bytes = 0
    completeness = "COMPLETE"
    for path in sorted(scan_input.checkout_root.rglob("*")):
        if time.monotonic() - started > scan_input.deadline_seconds:
            diagnostics.append(Diagnostic("ERROR", "SCAN_DEADLINE", "Scanner deadline exceeded"))
            return selected, "PARTIAL", total_bytes
        if not path.is_file() or path.is_symlink():
            continue
        relative = path.relative_to(scan_input.checkout_root).as_posix()
        if manifest_kind(relative) is None:
            continue
        size = path.stat().st_size
        if len(selected) >= scan_input.max_files or total_bytes + size > scan_input.max_bytes:
            completeness = "PARTIAL"
            diagnostics.append(
                Diagnostic("WARNING", "SCAN_LIMIT", "A scanner file or byte limit was reached", relative)
            )
            continue
        selected[relative] = path
        total_bytes += size
    return selected, completeness, total_bytes


def _decode_json(content: bytes, path: str, diagnostics: list[Diagnostic]) -> Any | None:
    try:
        return json.loads(content)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        diagnostics.append(Diagnostic("ERROR", "INVALID_JSON", str(error), path))
        return None


def _decode_toml(content: bytes, path: str, diagnostics: list[Diagnostic]) -> Any | None:
    try:
        return tomllib.loads(content.decode("utf-8"))
    except (UnicodeDecodeError, tomllib.TOMLDecodeError) as error:
        diagnostics.append(Diagnostic("ERROR", "INVALID_TOML", str(error), path))
        return None


def _scan_npm(contents: Mapping[str, bytes], diagnostics: list[Diagnostic]) -> list[Dependency]:
    dependencies: list[Dependency] = []
    npmrcs: dict[str, NpmConfig] = {}
    for path, content in contents.items():
        if PurePosixPath(path).name != ".npmrc":
            continue
        try:
            npmrcs[str(PurePosixPath(path).parent)] = parse_npmrc(
                content.decode("utf-8", errors="replace")
            )
        except ValueError as error:
            diagnostics.append(Diagnostic("ERROR", "INVALID_NPM_CONFIG", str(error), path))
    manifests = [path for path in contents if PurePosixPath(path).name == "package.json"]
    for path in manifests:
        document = _decode_json(contents[path], path, diagnostics)
        if not isinstance(document, Mapping):
            continue
        directory = str(PurePosixPath(path).parent)
        lock_path = _nearest_file(
            contents,
            directory,
            ("package-lock.json", "npm-shrinkwrap.json", "pnpm-lock.yaml", "yarn.lock"),
        )
        locked = _npm_lock_entries(contents.get(lock_path), lock_path, diagnostics) if lock_path else {}
        config_path, config = _nearest_npm_config(npmrcs, directory)
        for field, scope in (
            ("dependencies", "runtime"),
            ("devDependencies", "development"),
            ("optionalDependencies", "optional"),
            ("peerDependencies", "peer"),
            ("bundledDependencies", "bundled"),
        ):
            values = document.get(field)
            if isinstance(values, list):
                values = {str(name): "bundled" for name in values}
            if not isinstance(values, Mapping):
                continue
            for name, raw_spec in values.items():
                if not isinstance(name, str) or not isinstance(raw_spec, (str, int, float)):
                    continue
                spec = str(raw_spec)
                lock = locked.get(name.lower())
                dependency = _npm_dependency(
                    name,
                    spec,
                    scope,
                    directory,
                    path,
                    contents[path],
                    f"/{field}/{_json_pointer(name)}",
                    lock,
                    lock_path,
                    contents.get(lock_path) if lock_path else None,
                    config,
                    config_path,
                    diagnostics,
                )
                if dependency:
                    dependencies.append(dependency)
        direct_names = {item.normalized_name for item in dependencies if item.component_path == directory}
        for name, lock in locked.items():
            if normalize_package_name("npm", name) in direct_names:
                continue
            dependency = _npm_dependency(
                name,
                str(lock.get("version") or "unknown"),
                "unknown",
                directory,
                lock_path or path,
                contents.get(lock_path or path, b""),
                str(lock.get("pointer") or ""),
                lock,
                lock_path,
                contents.get(lock_path) if lock_path else None,
                config,
                config_path,
                diagnostics,
                direct=False,
            )
            if dependency:
                dependencies.append(dependency)
    return dependencies


def _npm_lock_entries(content: bytes | None, path: str | None, diagnostics: list[Diagnostic]) -> dict[str, dict[str, Any]]:
    if content is None or path is None:
        return {}
    name = PurePosixPath(path).name
    if name == "yarn.lock":
        return _yarn_lock_entries(content, path)
    if name == "pnpm-lock.yaml":
        return _pnpm_lock_entries(content, path)
    document = _decode_json(content, path, diagnostics)
    if not isinstance(document, Mapping):
        return {}
    entries: dict[str, dict[str, Any]] = {}
    packages = document.get("packages")
    if isinstance(packages, Mapping):
        for package_path, value in packages.items():
            if not isinstance(package_path, str) or not isinstance(value, Mapping) or "node_modules/" not in package_path:
                continue
            name = package_path.rsplit("node_modules/", 1)[1]
            if not name or "/node_modules/" in name:
                continue
            entries.setdefault(name.lower(), {
                **value,
                "pointer": f"/packages/{_json_pointer(package_path)}",
            })
    legacy = document.get("dependencies")
    if isinstance(legacy, Mapping):
        for name, value in legacy.items():
            if isinstance(name, str) and isinstance(value, Mapping):
                entries.setdefault(name.lower(), {
                    **value,
                    "pointer": f"/dependencies/{_json_pointer(name)}",
                })
    return entries


def _yarn_lock_entries(content: bytes, path: str) -> dict[str, dict[str, Any]]:
    text = content.decode("utf-8", errors="replace")
    entries: dict[str, dict[str, Any]] = {}
    current_name: str | None = None
    current: dict[str, Any] = {}
    start_line = 0

    def flush(end_line: int) -> None:
        if current_name and current.get("version"):
            current["locator"] = {
                "path": path,
                "line_start": start_line,
                "line_end": max(start_line, end_line),
            }
            entries.setdefault(current_name.lower(), dict(current))

    for line_number, line in enumerate(text.splitlines(), 1):
        if line and not line[0].isspace() and line.rstrip().endswith(":"):
            flush(line_number - 1)
            selector = line.rstrip()[:-1].split(",", 1)[0].strip().strip('"\'')
            current_name = _yarn_selector_name(selector)
            current = {}
            start_line = line_number
            continue
        if current_name is None:
            continue
        field = re.match(
            r"^\s+(version|resolved|integrity)\s*(?::\s*|\s+)(.+?)\s*$",
            line,
        )
        if not field:
            continue
        key, value = field.groups()
        value = value.strip().strip('"\'')
        if key == "resolved" and not value.startswith(("http://", "https://")):
            continue
        current[key] = value
    flush(len(text.splitlines()))
    return entries


def _yarn_selector_name(selector: str) -> str | None:
    selector = selector.removeprefix("__metadata:")
    if "@" not in selector[1:]:
        return None
    name = selector.rsplit("@", 1)[0]
    return name or None


def _pnpm_lock_entries(content: bytes, path: str) -> dict[str, dict[str, Any]]:
    text = content.decode("utf-8", errors="replace")
    lines = text.splitlines()
    entries: dict[str, dict[str, Any]] = {}
    in_packages = False
    current_name: str | None = None
    current: dict[str, Any] = {}
    start_line = 0

    def flush(end_line: int) -> None:
        if current_name and current.get("version"):
            current["locator"] = {
                "path": path,
                "line_start": start_line,
                "line_end": max(start_line, end_line),
            }
            entries.setdefault(current_name.lower(), dict(current))

    for line_number, line in enumerate(lines, 1):
        if line == "packages:":
            in_packages = True
            continue
        if in_packages and line and not line[0].isspace():
            flush(line_number - 1)
            break
        if not in_packages:
            continue
        header = re.match(r"^  ([^\s].*?):\s*$", line)
        if header:
            flush(line_number - 1)
            current_name, version = _pnpm_package_key(header.group(1).strip().strip('"\''))
            current = {"version": version} if version else {}
            start_line = line_number
            continue
        if current_name:
            integrity = re.search(r"\bintegrity:\s*([^,}\s]+)", line)
            if integrity:
                current["integrity"] = integrity.group(1).strip('"\'')
    else:
        flush(len(lines))
    return entries


def _pnpm_package_key(value: str) -> tuple[str | None, str | None]:
    value = value.removeprefix("/").split("(", 1)[0]
    if value.startswith("@") and "@" in value[1:]:
        name, version = value.rsplit("@", 1)
    elif "@" in value:
        name, version = value.rsplit("@", 1)
    elif "/" in value:
        name, version = value.rsplit("/", 1)
    else:
        return None, None
    return (name or None), (version or None)


def _npm_dependency(
    name: str,
    requested_spec: str,
    scope: str,
    component_path: str,
    declaration_path: str,
    declaration_content: bytes,
    pointer: str,
    lock: Mapping[str, Any] | None,
    lock_path: str | None,
    lock_content: bytes | None,
    npm_config: NpmConfig,
    config_path: str | None,
    diagnostics: list[Diagnostic],
    *,
    direct: bool = True,
) -> Dependency | None:
    declaration = Evidence(
        declaration_path,
        "MANIFEST" if direct else "LOCKFILE",
        content_hash(declaration_content),
        {"path": declaration_path, "json_pointer": pointer},
        sha256_key(requested_spec),
    )
    version = str(lock.get("version")) if lock and lock.get("version") else None
    resolution_evidence = None
    registry = None
    artifact = None
    if version:
        try:
            resolution = resolve_npm_dependency(
                name,
                requested_spec=requested_spec,
                resolved_version=version,
                npm_config=npm_config,
                config_path=config_path,
                resolved_uri=str(lock.get("resolved")) if lock and lock.get("resolved") else None,
                integrity=str(lock.get("integrity")) if lock and lock.get("integrity") else None,
            )
        except ValueError as error:
            diagnostics.append(Diagnostic("WARNING", "NPM_RESOLUTION_SKIPPED", str(error), lock_path or declaration_path))
            return None
        resolution_properties = resolution.fact_properties(
            dependency_scope=scope,
            direct=direct,
        )
        registry = resolution_properties["registry_resolution"]
        artifact = resolution_properties.get("artifact")
        if lock_path and lock_content is not None:
            resolution_evidence = Evidence(
                lock_path,
                "LOCKFILE",
                content_hash(lock_content),
                lock.get("locator") or {
                    "path": lock_path,
                    "json_pointer": str(lock.get("pointer") or ""),
                },
                sha256_key(version),
            )
    return Dependency(
        ecosystem="npm",
        name=name,
        requested_spec=requested_spec or version or "unknown",
        scope=scope,
        direct=direct,
        component_path=component_path,
        declaration=declaration,
        resolved_version=version,
        resolution_evidence=resolution_evidence,
        registry_properties=registry,
        artifact_properties=artifact,
    )


def _nearest_npm_config(configs: Mapping[str, NpmConfig], directory: str) -> tuple[str | None, NpmConfig]:
    for parent in _parents(directory):
        if parent in configs:
            path = f"{parent}/.npmrc" if parent != "." else ".npmrc"
            return path, configs[parent]
    return None, parse_npmrc("")


def _scan_python(contents: Mapping[str, bytes], diagnostics: list[Diagnostic]) -> list[Dependency]:
    dependencies: list[Dependency] = []
    lock_entries: dict[str, tuple[str, str, str, bytes]] = {}
    for path, content in contents.items():
        name = PurePosixPath(path).name
        if name in {"poetry.lock", "uv.lock"}:
            document = _decode_toml(content, path, diagnostics)
            if isinstance(document, Mapping) and isinstance(document.get("package"), list):
                for index, package in enumerate(document["package"]):
                    if isinstance(package, Mapping) and package.get("name") and package.get("version"):
                        normalized = normalize_package_name("pypi", str(package["name"]))
                        lock_entries[normalized] = (
                            str(package["version"]), path, f"/package/{index}", content,
                        )
        elif name == "Pipfile.lock":
            document = _decode_json(content, path, diagnostics)
            if isinstance(document, Mapping):
                for group in ("default", "develop"):
                    values = document.get(group)
                    if isinstance(values, Mapping):
                        for package_name, value in values.items():
                            if isinstance(value, Mapping):
                                version = str(value.get("version") or "").removeprefix("==")
                                if version:
                                    lock_entries[normalize_package_name("pypi", str(package_name))] = (
                                        version, path, f"/{group}/{_json_pointer(str(package_name))}", content,
                                    )
    for path, content in contents.items():
        name = PurePosixPath(path).name
        if name == "pyproject.toml":
            document = _decode_toml(content, path, diagnostics)
            if not isinstance(document, Mapping):
                continue
            project = document.get("project")
            if isinstance(project, Mapping):
                for index, requirement in enumerate(project.get("dependencies") or []):
                    dependency = _python_requirement(
                        str(requirement), "runtime", path, content,
                        {"path": path, "json_pointer": f"/project/dependencies/{index}"}, lock_entries,
                    )
                    if dependency:
                        dependencies.append(dependency)
                optional = project.get("optional-dependencies")
                if isinstance(optional, Mapping):
                    for group, requirements in optional.items():
                        if isinstance(requirements, list):
                            for index, requirement in enumerate(requirements):
                                dependency = _python_requirement(
                                    str(requirement), "development" if str(group).lower() in {"dev", "test", "docs"} else "optional",
                                    path, content,
                                    {"path": path, "json_pointer": f"/project/optional-dependencies/{_json_pointer(str(group))}/{index}"},
                                    lock_entries,
                                )
                                if dependency:
                                    dependencies.append(dependency)
            tool = document.get("tool")
            poetry = tool.get("poetry") if isinstance(tool, Mapping) else None
            if isinstance(poetry, Mapping):
                groups: list[tuple[str, Mapping[str, Any]]] = []
                base = poetry.get("dependencies")
                if isinstance(base, Mapping):
                    groups.append(("runtime", base))
                group_values = poetry.get("group")
                if isinstance(group_values, Mapping):
                    for group_name, group in group_values.items():
                        if isinstance(group, Mapping) and isinstance(group.get("dependencies"), Mapping):
                            groups.append(("development" if str(group_name).lower() in {"dev", "test"} else "optional", group["dependencies"]))
                for scope, values in groups:
                    for package_name, spec in values.items():
                        if str(package_name).lower() == "python":
                            continue
                        requested = spec if isinstance(spec, str) else canonical_json(spec)
                        dependency = _python_requirement(
                            f"{package_name}{requested if str(requested).startswith(('=', '<', '>', '~', '!', '^')) else ' ' + str(requested)}",
                            scope, path, content,
                            {"path": path, "json_pointer": f"/tool/poetry/dependencies/{_json_pointer(str(package_name))}"},
                            lock_entries,
                            explicit_name=str(package_name),
                            explicit_spec=str(requested),
                        )
                        if dependency:
                            dependencies.append(dependency)
        elif name.lower().startswith("requirements") and name.lower().endswith(".txt"):
            text = content.decode("utf-8", errors="replace")
            for line_number, line in enumerate(text.splitlines(), 1):
                stripped = line.strip()
                if not stripped or stripped.startswith(("#", "-")):
                    continue
                dependency = _python_requirement(
                    stripped, "development" if any(word in name.lower() for word in ("dev", "test")) else "runtime",
                    path, content, {"path": path, "line_start": line_number, "line_end": line_number}, lock_entries,
                )
                if dependency:
                    dependencies.append(dependency)
    declared_keys = {
        (dependency.normalized_name, dependency.resolved_version)
        for dependency in dependencies if dependency.ecosystem == "pypi"
    }
    for name, (version, path, pointer, content) in lock_entries.items():
        if (name, version) in declared_keys:
            continue
        evidence = Evidence(
            path, "LOCKFILE", content_hash(content),
            {"path": path, "json_pointer": pointer}, sha256_key(version),
        )
        dependencies.append(Dependency(
            ecosystem="pypi",
            name=name,
            requested_spec=version,
            scope="unknown",
            direct=False,
            component_path=str(PurePosixPath(path).parent),
            declaration=evidence,
            resolved_version=version,
            resolution_evidence=evidence,
        ))
    return dependencies


def _python_requirement(
    requirement: str,
    scope: str,
    path: str,
    content: bytes,
    locator: Mapping[str, Any],
    lock_entries: Mapping[str, tuple[str, str, str, bytes]],
    *,
    explicit_name: str | None = None,
    explicit_spec: str | None = None,
) -> Dependency | None:
    match = REQUIREMENT.match(requirement)
    if match is None and explicit_name is None:
        return None
    name = explicit_name or match.group(1)
    spec = explicit_spec or (match.group(2) if match else None) or "*"
    normalized = normalize_package_name("pypi", name)
    locked = lock_entries.get(normalized)
    version = locked[0] if locked else _exact_python_version(spec)
    resolution_evidence = None
    if locked:
        resolution_evidence = Evidence(
            locked[1], "LOCKFILE", content_hash(locked[3]),
            {"path": locked[1], "json_pointer": locked[2]}, sha256_key(locked[0]),
        )
    directory = str(PurePosixPath(path).parent)
    return Dependency(
        ecosystem="pypi",
        name=name,
        requested_spec=spec,
        scope=scope,
        direct=True,
        component_path=directory,
        declaration=Evidence(
            path, "MANIFEST", content_hash(content), locator, sha256_key(requirement),
        ),
        resolved_version=version,
        resolution_evidence=resolution_evidence,
    )


def _scan_sources(
    contents: Mapping[str, bytes],
    dependencies: Iterable[Dependency],
    diagnostics: list[Diagnostic],
) -> tuple[list[Reference], dict[str, set[str]], set[str]]:
    dependency_names = {
        (dependency.ecosystem, dependency.normalized_name)
        for dependency in dependencies
    }
    references: list[Reference] = []
    local_edges: dict[str, set[str]] = {}
    entrypoints: set[str] = set()
    for path, content in contents.items():
        suffix = PurePosixPath(path).suffix.lower()
        if suffix in {".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx", ".mts", ".cts"}:
            text = content.decode("utf-8", errors="replace")
            references.extend(_javascript_references(path, text, dependency_names))
            local_edges[path] = {
                resolved for module in JS_LOCAL_IMPORT.findall(text)
                if (resolved := _resolve_local_module(path, module, contents)) is not None
            }
        elif suffix == ".py":
            try:
                tree = ast.parse(content.decode("utf-8"), filename=path)
            except (UnicodeDecodeError, SyntaxError) as error:
                diagnostics.append(Diagnostic("WARNING", "PYTHON_PARSE_FAILED", str(error), path))
                continue
            python_refs, local = _python_references(path, tree, dependency_names, contents)
            references.extend(python_refs)
            local_edges[path] = local
        if PurePosixPath(path).name.lower() in {
            "main.py", "app.py", "manage.py", "__main__.py", "index.js", "index.ts", "server.js", "server.ts",
        }:
            entrypoints.add(path)
    entrypoints.update(_manifest_entrypoints(contents))
    return references, local_edges, entrypoints


def _javascript_references(
    path: str,
    text: str,
    dependency_names: set[tuple[str, str]],
) -> list[Reference]:
    references: dict[tuple[str, int], Reference] = {}
    for pattern in (JS_IMPORT, JS_SIDE_EFFECT_IMPORT):
        for match in pattern.finditer(text):
            module = match.group("module")
            package = _javascript_package(module)
            if package is None or ("npm", package) not in dependency_names:
                continue
            line = text.count("\n", 0, match.start()) + 1
            reference = references.setdefault((package, line), Reference("npm", package, path, line))
            clause = match.groupdict().get("clause")
            if clause:
                reference.symbols.update(_javascript_symbols(clause, module))
            elif module != package:
                reference.symbols.add(module[len(package):].lstrip("/"))
    for match in JS_REQUIRE_DESTRUCTURE.finditer(text):
        package = _javascript_package(match.group("module"))
        if package and ("npm", package) in dependency_names:
            line = text.count("\n", 0, match.start()) + 1
            reference = references.setdefault((package, line), Reference("npm", package, path, line))
            reference.symbols.update(
                value.strip().split(":", 1)[0].strip()
                for value in match.group("symbols").split(",") if value.strip()
            )
    for match in JS_REQUIRE_MEMBER.finditer(text):
        package = _javascript_package(match.group("module"))
        if package and ("npm", package) in dependency_names:
            line = text.count("\n", 0, match.start()) + 1
            references.setdefault((package, line), Reference("npm", package, path, line)).symbols.add(match.group("symbol"))
    return list(references.values())


def _python_references(
    path: str,
    tree: ast.AST,
    dependency_names: set[tuple[str, str]],
    contents: Mapping[str, bytes],
) -> tuple[list[Reference], set[str]]:
    references: list[Reference] = []
    local: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".", 1)[0]
                package = _match_python_distribution(root, dependency_names)
                if package:
                    references.append(Reference("pypi", package, path, node.lineno, {"*"}))
                elif (resolved := _resolve_python_local(path, alias.name, 0, contents)):
                    local.add(resolved)
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            root = module.split(".", 1)[0]
            package = _match_python_distribution(root, dependency_names) if node.level == 0 else None
            if package:
                references.append(Reference(
                    "pypi", package, path, node.lineno,
                    {alias.name for alias in node.names},
                ))
            elif (resolved := _resolve_python_local(path, module, node.level, contents)):
                local.add(resolved)
    return references, local


def _reachable_files(
    contents: Mapping[str, bytes],
    local_edges: Mapping[str, set[str]],
    entrypoints: set[str],
) -> set[str] | None:
    valid = {path for path in entrypoints if path in contents}
    if not valid:
        return None
    visited: set[str] = set()
    pending = list(valid)
    while pending:
        path = pending.pop()
        if path in visited:
            continue
        visited.add(path)
        pending.extend(local_edges.get(path, set()) - visited)
    return visited


def _runtime_observations(contents: Mapping[str, bytes], diagnostics: list[Diagnostic]) -> dict[tuple[str, str], set[str]] | None:
    path = next((item for item in contents if PurePosixPath(item).name == "stackgraph-runtime.json"), None)
    if path is None:
        return None
    document = _decode_json(contents[path], path, diagnostics)
    if not isinstance(document, Mapping) or not isinstance(document.get("events"), list):
        diagnostics.append(Diagnostic("WARNING", "INVALID_RUNTIME_TRACE", "Runtime trace requires an events array", path))
        return None
    observed: dict[tuple[str, str], set[str]] = {}
    for event in document["events"]:
        if not isinstance(event, Mapping):
            continue
        ecosystem = str(event.get("ecosystem") or "").lower()
        name = str(event.get("package") or "")
        if ecosystem not in {"npm", "pypi"} or not name:
            continue
        key = (ecosystem, normalize_package_name(ecosystem, name))
        observed.setdefault(key, set()).add(str(event.get("symbol") or "*"))
    return observed


def _scan_code_units(
    contents: Mapping[str, bytes],
    references: Iterable[Reference],
    local_edges: Mapping[str, set[str]],
    diagnostics: list[Diagnostic],
    *,
    max_units: int = 500,
) -> list[CodeUnit]:
    dependency_by_path: dict[str, set[str]] = {}
    for reference in references:
        dependency_by_path.setdefault(reference.path, set()).add(
            f"pkg:{reference.ecosystem}/{reference.package_name}"
        )
    coverage = _test_coverage_links(contents, local_edges)
    repository_touchpoints = _repository_touchpoints(contents)
    units: list[CodeUnit] = []
    for path in sorted(contents):
        if len(units) >= max_units:
            diagnostics.append(Diagnostic(
                "WARNING", "CODE_UNIT_LIMIT",
                f"Code-unit analysis stopped after {max_units} units.",
            ))
            break
        suffix = PurePosixPath(path).suffix.lower()
        content = contents[path]
        if suffix == ".py":
            vendored_identity = _vendored_identity(contents, path, "pypi")
            try:
                tree = ast.parse(content.decode("utf-8"), filename=path)
            except (UnicodeDecodeError, SyntaxError):
                continue
            for node in ast.walk(tree):
                if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    continue
                units.append(CodeUnit(
                    language="python",
                    symbol_kind="CLASS" if isinstance(node, ast.ClassDef) else "FUNCTION",
                    qualified_name=node.name,
                    path=path,
                    line_start=int(node.lineno),
                    line_end=int(getattr(node, "end_lineno", node.lineno)),
                    structural_fingerprint=sha256_key("python-ast-v1", _ast_shape(node)),
                    semantic_tokens=tuple(sorted(_python_semantic_tokens(node))),
                    dependency_keys=tuple(sorted(dependency_by_path.get(path, ()))),
                    covering_tests=tuple(sorted(coverage.get(path, ()))),
                    dynamic_signals=_dynamic_signals(path, content),
                    touchpoints=repository_touchpoints,
                    vendored=_is_vendored(path),
                    vendored_package_key=vendored_identity[0],
                    vendored_package_version=vendored_identity[1],
                    vendored_identity_source=vendored_identity[2],
                ))
                if len(units) >= max_units:
                    break
        elif suffix in {".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx", ".mts", ".cts"}:
            vendored_identity = _vendored_identity(contents, path, "npm")
            text = content.decode("utf-8", errors="replace")
            for match in sorted(
                [*JS_FUNCTION.finditer(text), *JS_ARROW_FUNCTION.finditer(text)],
                key=lambda item: item.start(),
            ):
                body_end = _matching_brace(text, match.end() - 1)
                if body_end is None:
                    continue
                source = text[match.start():body_end + 1]
                units.append(CodeUnit(
                    language="javascript",
                    symbol_kind="FUNCTION",
                    qualified_name=match.group("name"),
                    path=path,
                    line_start=text.count("\n", 0, match.start()) + 1,
                    line_end=text.count("\n", 0, body_end) + 1,
                    structural_fingerprint=sha256_key(
                        "javascript-structure-v1", _javascript_shape(source),
                    ),
                    semantic_tokens=tuple(sorted(_identifier_tokens(source))),
                    dependency_keys=tuple(sorted(dependency_by_path.get(path, ()))),
                    covering_tests=tuple(sorted(coverage.get(path, ()))),
                    dynamic_signals=_dynamic_signals(path, content),
                    touchpoints=repository_touchpoints,
                    vendored=_is_vendored(path),
                    vendored_package_key=vendored_identity[0],
                    vendored_package_version=vendored_identity[1],
                    vendored_identity_source=vendored_identity[2],
                ))
                if len(units) >= max_units:
                    break
    return units


def _code_unit_facts(scan_input: ScanInput, units: Iterable[CodeUnit]) -> list[dict[str, Any]]:
    facts: list[dict[str, Any]] = []
    for unit in units:
        value = {
            "record_kind": "code_implementation_summary",
            "language": unit.language,
            "symbol_kind": unit.symbol_kind,
            "qualified_name": unit.qualified_name,
            "path": unit.path,
            "line_start": unit.line_start,
            "line_end": unit.line_end,
            "structural_fingerprint": unit.structural_fingerprint,
            "semantic_tokens": list(unit.semantic_tokens),
            "dependency_keys": list(unit.dependency_keys),
            "covering_tests": list(unit.covering_tests),
            "dynamic_signals": list(unit.dynamic_signals),
            "touchpoints": [dict(item) for item in unit.touchpoints],
            "vendored": unit.vendored,
            "vendored_package_key": unit.vendored_package_key,
            "vendored_package_version": unit.vendored_package_version,
            "vendored_identity_source": unit.vendored_identity_source,
        }
        identity = {
            "tenant": scan_input.tenant_key,
            "repository": scan_input.repository_key,
            "source_revision": scan_input.source_revision,
            "path": unit.path,
            "symbol": unit.qualified_name,
            "line": unit.line_start,
            "structure": unit.structural_fingerprint,
            "extractor": SCANNER_VERSION,
        }
        evidence = Evidence(
            unit.path,
            "SOURCE_STRUCTURE",
            _content_hash_from_evidence_context(unit.path, scan_input.checkout_root),
            {"path": unit.path, "line_start": unit.line_start, "line_end": unit.line_end},
            sha256_key(unit.structural_fingerprint, unit.semantic_tokens),
            {"symbol": unit.qualified_name, "language": unit.language},
        )
        facts.append({
            "fact_contract_version": "1.0.0",
            "idempotency_key": sha256_key(identity),
            "tenant_key": scan_input.tenant_key,
            "subject": _repository_ref(scan_input),
            "predicate": "HAS_PROPERTY",
            "object_value": value,
            "assertion_class": "OBSERVED",
            "confidence": 0.95,
            "observed_at": scan_input.observed_at,
            "source_revision": scan_input.source_revision,
            "extractor": {"key": SCANNER_KEY, "version": SCANNER_VERSION},
            "properties": {"analysis_kind": "CODE_IMPLEMENTATION_SUMMARY"},
            "evidence": [_evidence_dict(evidence, scan_input)],
        })
    return facts


def _ast_shape(node: ast.AST) -> object:
    ignored = {"name", "id", "arg", "value", "ctx", "type_comment", "kind"}
    return [
        type(node).__name__,
        *[
            [field_name, _ast_shape_value(value)]
            for field_name, value in ast.iter_fields(node)
            if field_name not in ignored
        ],
    ]


def _ast_shape_value(value: object) -> object:
    if isinstance(value, ast.AST):
        return _ast_shape(value)
    if isinstance(value, list):
        return [_ast_shape_value(item) for item in value]
    if isinstance(value, (str, int, float, complex, bytes)) or value is None:
        return type(value).__name__
    return str(type(value).__name__)


def _python_semantic_tokens(node: ast.AST) -> set[str]:
    values: set[str] = set()
    for child in ast.walk(node):
        if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            values.update(_identifier_tokens(child.name))
        elif isinstance(child, ast.Name):
            values.update(_identifier_tokens(child.id))
        elif isinstance(child, ast.Attribute):
            values.update(_identifier_tokens(child.attr))
    return values


def _identifier_tokens(value: str) -> set[str]:
    return {
        part.lower()
        for raw in re.split(r"[^A-Za-z0-9]+", value)
        for part in IDENTIFIER_PART.findall(raw)
        if len(part) > 1
    }


def _javascript_shape(source: str) -> str:
    value = re.sub(r"/\*.*?\*/|//[^\n]*", " ", source, flags=re.S)
    value = re.sub(r"(?:'[^'\\]*(?:\\.[^'\\]*)*'|\"[^\"\\]*(?:\\.[^\"\\]*)*\"|`[^`]*`)", "STRING", value)
    value = re.sub(r"\b\d+(?:\.\d+)?\b", "NUMBER", value)
    value = re.sub(r"\b[A-Za-z_$][\w$]*\b", "ID", value)
    return re.sub(r"\s+", " ", value).strip()


def _matching_brace(text: str, start: int) -> int | None:
    depth = 0
    quote: str | None = None
    escaped = False
    for index in range(start, len(text)):
        character = text[index]
        if quote is not None:
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == quote:
                quote = None
            continue
        if character in {"'", '"', "`"}:
            quote = character
        elif character == "{":
            depth += 1
        elif character == "}":
            depth -= 1
            if depth == 0:
                return index
    return None


def _test_coverage_links(
    contents: Mapping[str, bytes], local_edges: Mapping[str, set[str]],
) -> dict[str, set[str]]:
    result: dict[str, set[str]] = {}
    tests = [path for path in contents if _is_test_path(path)]
    for test_path in tests:
        pending = list(local_edges.get(test_path, ()))
        visited: set[str] = set()
        while pending:
            path = pending.pop()
            if path in visited:
                continue
            visited.add(path)
            pending.extend(local_edges.get(path, ()) - visited)
        for path in visited:
            result.setdefault(path, set()).add(test_path)
    return result


def _is_test_path(path: str) -> bool:
    lowered = path.lower()
    name = PurePosixPath(lowered).name
    return (
        "/test/" in f"/{lowered}/" or "/tests/" in f"/{lowered}/"
        or name.startswith("test_") or ".test." in name or ".spec." in name
    )


def _dynamic_signals(path: str, content: bytes) -> tuple[str, ...]:
    text = content.decode("utf-8", errors="replace")
    patterns = {
        "DYNAMIC_IMPORT": r"\b(?:import\s*\(|require\s*\([^'\"]|importlib\.|__import__\s*\()",
        "REFLECTION": r"\b(?:getattr|setattr|eval|exec|Reflect\.|Proxy\s*\()",
        "PLUGIN_LOADING": r"\b(?:plugin|entry_points|load_module|ServiceLoader)\b",
        "GENERATED_CODE": r"\b(?:generated|codegen|autogenerated)\b",
    }
    return tuple(sorted(key for key, pattern in patterns.items() if re.search(pattern, text, re.I)))


def _repository_touchpoints(contents: Mapping[str, bytes]) -> tuple[Mapping[str, str], ...]:
    values: dict[tuple[str, str], Mapping[str, str]] = {}
    for path in contents:
        lowered = path.lower()
        name = PurePosixPath(lowered).name
        kind = None
        if (
            name == "dockerfile" or name.startswith("dockerfile.") or _is_compose_file(name)
            or "deploy" in lowered or "/k8s/" in f"/{lowered}/"
            or PurePosixPath(lowered).suffix == ".tf"
        ):
            kind = "DEPLOYMENT"
        elif name in {"package.json", "pyproject.toml", "requirements.txt", "makefile"} or "build" in name:
            kind = "BUILD"
        elif "config" in name or PurePosixPath(lowered).suffix in {".yaml", ".yml", ".toml"}:
            kind = "CONFIGURATION"
        if kind:
            values[(kind, path)] = {"kind": kind, "path": path}
    return tuple(values[key] for key in sorted(values)[:50])


def _is_vendored(path: str) -> bool:
    return bool({"vendor", "vendored", "third_party", "third-party"} & set(PurePosixPath(path.lower()).parts))


def _vendored_identity(
    contents: Mapping[str, bytes], path: str, ecosystem: str,
) -> tuple[str | None, str | None, str | None]:
    """Return a deterministic package identity for a vendored source path.

    Package metadata inside the vendored root is authoritative.  When it is not
    present, the first directory below the vendor marker is retained as a
    bounded path-derived identity; no version is invented in that case.
    """
    parts = PurePosixPath(path).parts
    lowered = [part.lower() for part in parts]
    marker_index = next((
        index for index, part in enumerate(lowered)
        if part in {"vendor", "vendored", "third_party", "third-party"}
    ), None)
    if marker_index is None or marker_index + 1 >= len(parts):
        return None, None, None

    package_parts = [parts[marker_index + 1]]
    if package_parts[0].startswith("@") and marker_index + 2 < len(parts):
        package_parts.append(parts[marker_index + 2])
    root = "/".join(parts[:marker_index + 1 + len(package_parts)])

    if ecosystem == "npm":
        metadata_path = f"{root}/package.json"
        if metadata_path in contents:
            try:
                document = json.loads(contents[metadata_path].decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                document = None
            if isinstance(document, Mapping):
                name = str(document.get("name") or "").strip()
                version = str(document.get("version") or "").strip() or None
                if name:
                    encoded_name = quote(name.lower(), safe="/")
                    return f"pkg:npm/{encoded_name}", version, metadata_path
    else:
        metadata_path = f"{root}/pyproject.toml"
        if metadata_path in contents:
            try:
                document = tomllib.loads(contents[metadata_path].decode("utf-8"))
            except (UnicodeDecodeError, tomllib.TOMLDecodeError):
                document = None
            project = document.get("project") if isinstance(document, Mapping) else None
            if isinstance(project, Mapping):
                name = str(project.get("name") or "").strip()
                version = str(project.get("version") or "").strip() or None
                if name:
                    return f"pkg:pypi/{normalize_package_name('pypi', name)}", version, metadata_path

    path_name = "/".join(package_parts)
    normalized = (
        quote(path_name.lower(), safe="/") if ecosystem == "npm"
        else normalize_package_name("pypi", path_name)
    )
    return f"pkg:{ecosystem}/{normalized}", None, f"path:{root}"


def _dependency_facts(
    scan_input: ScanInput,
    dependencies: list[Dependency],
    references: list[Reference],
    reachable_files: set[str] | None,
    runtime: dict[tuple[str, str], set[str]] | None,
    completeness: str,
    source_file_count: int,
) -> list[dict[str, Any]]:
    facts: list[dict[str, Any]] = []
    for dependency in dependencies:
        key = (dependency.ecosystem, dependency.normalized_name)
        matches = [reference for reference in references if (reference.ecosystem, reference.package_name) == key]
        symbols = sorted({symbol for reference in matches for symbol in reference.symbols})
        usage = {
            "declared": True,
            "resolved": dependency.resolved_version is not None,
            "referenced": bool(matches),
            "reference_count": len(matches),
            "referenced_symbols": symbols,
            "static_reachability": (
                "UNKNOWN" if reachable_files is None else
                "OBSERVED" if any(reference.path in reachable_files for reference in matches) else
                "NOT_OBSERVED"
            ),
            "runtime_observed": (
                "UNKNOWN" if runtime is None else "OBSERVED" if key in runtime else "NOT_OBSERVED"
            ),
            "source_files_scanned": source_file_count,
            "limitations": _usage_limitations(dependency.ecosystem, completeness, reachable_files, runtime),
        }
        properties: dict[str, Any] = {
            "ecosystem": dependency.ecosystem,
            "scope": dependency.scope,
            "direct": dependency.direct,
            "requested_spec": dependency.requested_spec,
            "component_path": dependency.component_path,
            "usage": usage,
        }
        if dependency.resolved_version:
            properties["resolved_version"] = dependency.resolved_version
        if dependency.registry_properties:
            properties["registry_resolution"] = dict(dependency.registry_properties)
        if dependency.artifact_properties:
            properties["artifact"] = dict(dependency.artifact_properties)
        evidence = [dependency.declaration]
        if dependency.resolution_evidence and dependency.resolution_evidence != dependency.declaration:
            evidence.append(dependency.resolution_evidence)
        for reference in matches:
            evidence.append(Evidence(
                reference.path,
                "SOURCE_REFERENCE",
                _content_hash_from_evidence_context(reference.path, scan_input.checkout_root),
                {"path": reference.path, "line_start": reference.line, "line_end": reference.line},
                sha256_key(reference.path, reference.line, sorted(reference.symbols)),
                {"symbols": sorted(reference.symbols)},
            ))
        object_entity = {
            "namespace": "TECHNOLOGY",
            "type": dependency.entity_type,
            "key": dependency.entity_key,
            "name": f"{dependency.normalized_name}{' ' + dependency.resolved_version if dependency.resolved_version else ''}",
        }
        identity = {
            "tenant": scan_input.tenant_key,
            "repository": scan_input.repository_key,
            "predicate": "DEPENDS_ON",
            "object": dependency.entity_key,
            "component": dependency.component_path,
            "scope": dependency.scope,
            "direct": dependency.direct,
            "source_revision": scan_input.source_revision,
            "extractor": SCANNER_VERSION,
        }
        facts.append({
            "fact_contract_version": "1.0.0",
            "idempotency_key": sha256_key(identity),
            "tenant_key": scan_input.tenant_key,
            "subject": _repository_ref(scan_input),
            "predicate": "DEPENDS_ON",
            "object_entity": object_entity,
            "assertion_class": "DECLARED",
            "confidence": 1,
            "observed_at": scan_input.observed_at,
            "source_revision": scan_input.source_revision,
            "extractor": {"key": SCANNER_KEY, "version": SCANNER_VERSION},
            "properties": properties,
            "evidence": [_evidence_dict(item, scan_input) for item in evidence],
        })
    return facts


def _component_dependency_facts(
    scan_input: ScanInput,
    dependencies: list[Dependency],
    references: list[Reference],
    reachable_files: set[str] | None,
    runtime: dict[tuple[str, str], set[str]] | None,
    completeness: str,
    source_file_count: int,
) -> list[dict[str, Any]]:
    """Attribute dependencies to canonical components while retaining v1 repository facts."""
    repository_facts = _dependency_facts(
        scan_input, dependencies, references, reachable_files, runtime,
        completeness, source_file_count,
    )
    facts: list[dict[str, Any]] = []
    for dependency, repository_fact in zip(dependencies, repository_facts, strict=True):
        fact = dict(repository_fact)
        component = _component_ref(scan_input, dependency.component_path)
        properties = dict(repository_fact["properties"])
        properties.update({
            "attribution": "COMPONENT",
            "repository_key": scan_input.repository_key,
        })
        fact["subject"] = component
        fact["properties"] = properties
        fact["idempotency_key"] = sha256_key({
            "tenant": scan_input.tenant_key,
            "component": component["key"],
            "predicate": "DEPENDS_ON",
            "object": repository_fact["object_entity"]["key"],
            "scope": dependency.scope,
            "direct": dependency.direct,
            "source_revision": scan_input.source_revision,
            "extractor": SCANNER_VERSION,
        })
        facts.append(fact)
    return facts


def _usage_findings(
    scan_input: ScanInput,
    dependencies: list[Dependency],
    references: list[Reference],
    reachable_files: set[str] | None,
    runtime: dict[tuple[str, str], set[str]] | None,
    completeness: str,
    source_file_count: int,
) -> list[dict[str, Any]]:
    if completeness != "COMPLETE" or source_file_count == 0:
        return []
    facts: list[dict[str, Any]] = []
    for dependency in dependencies:
        if not dependency.direct:
            continue
        key = (dependency.ecosystem, dependency.normalized_name)
        matches = [reference for reference in references if (reference.ecosystem, reference.package_name) == key]
        symbols = sorted({symbol for reference in matches for symbol in reference.symbols})
        finding_type = None
        confidence = 0.0
        if not matches and (runtime is None or key not in runtime):
            finding_type = "UNUSED_DECLARED_DEPENDENCY_CANDIDATE"
            confidence = 0.65 if runtime is None else 0.8
        elif matches and "*" not in symbols and 0 < len(symbols) <= 3:
            finding_type = "NARROW_USE_DEPENDENCY_CANDIDATE"
            confidence = 0.72
        if finding_type is None:
            continue
        limitations = _usage_limitations(dependency.ecosystem, completeness, reachable_files, runtime)
        value = {
            "finding_type": finding_type,
            "dependency_key": dependency.entity_key,
            "package": dependency.normalized_name,
            "scope": dependency.scope,
            "reference_count": len(matches),
            "referenced_symbols": symbols,
            "denominator": "public API size unknown until artifact analysis",
            "limitations": limitations,
        }
        evidence = [_evidence_dict(dependency.declaration, scan_input)]
        evidence.extend(
            _evidence_dict(
                Evidence(
                    reference.path,
                    "SOURCE_REFERENCE",
                    _content_hash_from_evidence_context(
                        reference.path, scan_input.checkout_root
                    ),
                    {
                        "path": reference.path,
                        "line_start": reference.line,
                        "line_end": reference.line,
                    },
                    sha256_key(reference.path, reference.line, sorted(reference.symbols)),
                ),
                scan_input,
            )
            for reference in matches
        )
        identity = {
            "tenant": scan_input.tenant_key,
            "repository": scan_input.repository_key,
            "finding": finding_type,
            "dependency": dependency.entity_key,
            "component": dependency.component_path,
            "source_revision": scan_input.source_revision,
            "extractor": SCANNER_VERSION,
        }
        facts.append({
            "fact_contract_version": "1.0.0",
            "idempotency_key": sha256_key(identity),
            "tenant_key": scan_input.tenant_key,
            "subject": _repository_ref(scan_input),
            "predicate": "HAS_PROPERTY",
            "object_value": value,
            "assertion_class": "OBSERVED",
            "confidence": confidence,
            "observed_at": scan_input.observed_at,
            "source_revision": scan_input.source_revision,
            "extractor": {"key": SCANNER_KEY, "version": SCANNER_VERSION},
            "properties": {
                "analysis_fingerprint": sha256_key(
                    scan_input.repository_key, scan_input.source_revision, SCANNER_VERSION,
                    dependency.entity_key, finding_type,
                ),
                "review_state": "UNREVIEWED",
            },
            "evidence": evidence,
        })
    return facts


def _repository_ref(scan_input: ScanInput) -> dict[str, str]:
    return {
        "namespace": "ENTERPRISE",
        "type": "Repository",
        "key": scan_input.repository_key,
        "name": scan_input.repository_name,
    }


def _internal_package_publication_facts(
    scan_input: ScanInput,
    contents: Mapping[str, bytes],
    diagnostics: list[Diagnostic],
) -> list[dict[str, Any]]:
    """Emit tenant-scoped package publication facts from repository manifests.

    A package is considered internal only when its publish registry is explicitly a
    non-public npm registry. Package names alone are not enough evidence, and manifests
    marked private are never treated as published libraries.
    """
    configs: dict[str, NpmConfig] = {}
    for path, content in contents.items():
        if PurePosixPath(path).name != ".npmrc":
            continue
        try:
            configs[str(PurePosixPath(path).parent)] = parse_npmrc(
                content.decode("utf-8", errors="replace"), config_path=path,
            )
        except ValueError as error:
            diagnostics.append(Diagnostic(
                "WARNING", "INTERNAL_PUBLICATION_CONFIG_SKIPPED", str(error), path,
            ))

    facts: list[dict[str, Any]] = []
    for path in sorted(
        value for value in contents if PurePosixPath(value).name == "package.json"
    ):
        document = _decode_json(contents[path], path, diagnostics)
        if not isinstance(document, Mapping) or document.get("private") is True:
            continue
        raw_name = document.get("name")
        raw_version = document.get("version")
        if not isinstance(raw_name, str) or not raw_name.strip():
            continue
        if not isinstance(raw_version, str) or not raw_version.strip():
            continue
        package_name = normalize_package_name("npm", raw_name)
        directory = str(PurePosixPath(path).parent)
        config_path, config = _nearest_npm_config(configs, directory)
        publish_config = document.get("publishConfig")
        configured_registry = (
            publish_config.get("registry") if isinstance(publish_config, Mapping) else None
        )
        try:
            if isinstance(configured_registry, str) and configured_registry.strip():
                registry_origin = normalize_registry_origin(configured_registry)
                registry_source = "PUBLISH_CONFIG"
            else:
                scope = package_name.partition("/")[0] if package_name.startswith("@") else None
                registry_origin = (
                    config.scoped_registries.get(scope, config.default_registry)
                    if scope else config.default_registry
                )
                registry_source = "NPMRC_SCOPE" if scope in config.scoped_registries else "NPMRC_DEFAULT"
        except ValueError as error:
            diagnostics.append(Diagnostic(
                "WARNING", "INTERNAL_PUBLICATION_REGISTRY_SKIPPED", str(error), path,
            ))
            continue
        if registry_origin == PUBLIC_NPM_ORIGIN:
            continue

        registry_key = f"npm-{hashlib.sha256(registry_origin.encode()).hexdigest()[:16]}"
        encoded_name = quote(package_name, safe="/")
        encoded_version = quote(raw_version.strip(), safe=".-_~+")
        package_key = f"registry:{registry_key}:pkg:npm/{encoded_name}@{encoded_version}"
        manifest_pointer = (
            "/publishConfig/registry" if registry_source == "PUBLISH_CONFIG" else "/name"
        )
        evidence = [Evidence(
            path, "PACKAGE_PUBLICATION_MANIFEST", content_hash(contents[path]),
            {"path": path, "json_pointer": manifest_pointer},
            sha256_key(package_name, raw_version.strip(), registry_origin),
        )]
        if registry_source.startswith("NPMRC") and config_path and config_path in contents:
            evidence.append(Evidence(
                config_path, "NPM_REGISTRY_CONFIG", content_hash(contents[config_path]),
                {"path": config_path}, sha256_key(registry_origin),
            ))
        identity = {
            "tenant": scan_input.tenant_key,
            "repository": scan_input.repository_key,
            "predicate": "PUBLISHES",
            "package": package_key,
            "source_revision": scan_input.source_revision,
            "extractor": SCANNER_VERSION,
        }
        facts.append({
            "fact_contract_version": "1.0.0",
            "idempotency_key": sha256_key(identity),
            "tenant_key": scan_input.tenant_key,
            "subject": _repository_ref(scan_input),
            "predicate": "PUBLISHES",
            "object_entity": {
                "namespace": "TECHNOLOGY",
                "type": "PackageVersion",
                "key": package_key,
                "name": f"{package_name} {raw_version.strip()}",
            },
            "assertion_class": "DECLARED",
            "confidence": 1,
            "observed_at": scan_input.observed_at,
            "source_revision": scan_input.source_revision,
            "extractor": {"key": SCANNER_KEY, "version": SCANNER_VERSION},
            "properties": {
                "ecosystem": "npm",
                "package_name": package_name,
                "version": raw_version.strip(),
                "component_path": directory,
                "internal": True,
                "registry_key": registry_key,
                "registry_origin": registry_origin,
                "registry_source": registry_source,
            },
            "evidence": [_evidence_dict(item, scan_input) for item in evidence],
        })
    return facts


@dataclass(frozen=True, slots=True)
class RepositoryProfileSource:
    kind: str
    value: str
    path: str
    locator: Mapping[str, Any]


def _repository_profile_facts(
    scan_input: ScanInput,
    contents: Mapping[str, bytes],
) -> list[dict[str, Any]]:
    """Describe repository intent from bounded, revision-pinned source evidence.

    README prose and manifest descriptions are declared evidence. Languages, components,
    and operational signals are deterministic inventory only; they are never used to invent
    a purpose when the repository does not state one.
    """
    if not contents:
        return []
    description_sources = _repository_description_sources(contents)
    purpose_source = description_sources[0] if description_sources else None
    languages = sorted({
        label
        for path in contents
        if (label := LANGUAGE_LABELS.get(PurePosixPath(path).suffix.lower())) is not None
    })
    components = sorted({
        _component_label(path)
        for path in contents
        if PurePosixPath(path).name in {
            "package.json", "pyproject.toml", "requirements.txt", "Pipfile",
        }
    })
    operational_signals = _repository_operational_signals(contents)
    key_files = _repository_key_files(contents)
    hygiene = _repository_hygiene(contents)
    evidence_sources = list(description_sources[:8])
    evidenced_paths = {source.path for source in evidence_sources}
    for path in key_files:
        if path in evidenced_paths or len(evidence_sources) >= 12:
            continue
        evidence_sources.append(RepositoryProfileSource(
            kind="REPOSITORY_FILE", value=path, path=path, locator={"path": path},
        ))
        evidenced_paths.add(path)
    if not evidence_sources:
        path = min(contents, key=lambda value: (len(PurePosixPath(value).parts), value))
        evidence_sources.append(RepositoryProfileSource(
            kind="REPOSITORY_FILE", value=path, path=path, locator={"path": path},
        ))

    purpose = purpose_source.value if purpose_source else None
    profile: dict[str, Any] = {
        "record_kind": "repository_profile",
        "schema_version": "1.1.0",
        "descriptions": [source.value for source in description_sources],
        "languages": languages,
        "components": components,
        "key_files": key_files,
        "hygiene": hygiene,
        "operational_signals": operational_signals,
        "classifications": _repository_classifications(contents),
        "limitations": [
            "purpose is reported only when README or manifest text states it",
            "documentation may be stale or describe only part of a monorepo",
            "language and operational signals reflect only files admitted by scanner bounds",
        ],
    }
    if purpose:
        profile["purpose"] = purpose
        profile["purpose_source"] = {
            "kind": purpose_source.kind,
            "path": purpose_source.path,
        }
    evidence = [
        _evidence_dict(Evidence(
            path=source.path,
            evidence_type="REPOSITORY_PROFILE_SOURCE",
            content_hash=content_hash(contents[source.path]),
            locator=source.locator,
            excerpt_hash=sha256_key(source.value),
            metadata={"profile_source_kind": source.kind},
        ), scan_input)
        for source in evidence_sources
    ]
    identity = {
        "tenant": scan_input.tenant_key,
        "repository": scan_input.repository_key,
        "record_kind": profile["record_kind"],
        "source_revision": scan_input.source_revision,
        "extractor": SCANNER_VERSION,
    }
    confidence = 0.95 if purpose_source and purpose_source.kind == "README" else 0.9 if purpose_source else 0.65
    return [{
        "fact_contract_version": "1.0.0",
        "idempotency_key": sha256_key(identity),
        "tenant_key": scan_input.tenant_key,
        "subject": _repository_ref(scan_input),
        "predicate": "HAS_PROPERTY",
        "object_value": profile,
        "assertion_class": "DECLARED" if purpose_source else "INFERRED",
        "confidence": confidence,
        "observed_at": scan_input.observed_at,
        "source_revision": scan_input.source_revision,
        "extractor": {"key": SCANNER_KEY, "version": SCANNER_VERSION},
        "properties": {"profile_schema_version": "1.1.0"},
        "evidence": evidence,
    }]


def _repository_description_sources(
    contents: Mapping[str, bytes],
) -> tuple[RepositoryProfileSource, ...]:
    values: list[RepositoryProfileSource] = []
    readmes = sorted(
        (path for path in contents if _is_readme(path)),
        key=lambda path: (len(PurePosixPath(path).parts), path.lower(), path),
    )
    for path in readmes:
        extracted = _readme_lead(contents[path])
        if extracted is not None:
            value, line_start, line_end = extracted
            values.append(RepositoryProfileSource(
                kind="README", value=value, path=path,
                locator={"path": path, "line_start": line_start, "line_end": line_end},
            ))
    manifests = sorted(
        (path for path in contents if PurePosixPath(path).name in {"package.json", "pyproject.toml"}),
        key=lambda path: (len(PurePosixPath(path).parts), path),
    )
    for path in manifests:
        name = PurePosixPath(path).name
        try:
            if name == "package.json":
                document = json.loads(contents[path])
                description = document.get("description") if isinstance(document, Mapping) else None
                pointer = "/description"
            else:
                document = tomllib.loads(contents[path].decode("utf-8"))
                project = document.get("project") if isinstance(document, Mapping) else None
                tool = document.get("tool") if isinstance(document, Mapping) else None
                poetry = tool.get("poetry") if isinstance(tool, Mapping) else None
                if isinstance(project, Mapping) and project.get("description"):
                    description = project.get("description")
                    pointer = "/project/description"
                else:
                    description = poetry.get("description") if isinstance(poetry, Mapping) else None
                    pointer = "/tool/poetry/description"
        except (UnicodeDecodeError, json.JSONDecodeError, tomllib.TOMLDecodeError):
            continue
        if isinstance(description, str) and (cleaned := _clean_profile_text(description)):
            values.append(RepositoryProfileSource(
                kind="MANIFEST_DESCRIPTION", value=cleaned, path=path,
                locator={"path": path, "json_pointer": pointer},
            ))
    deduped: list[RepositoryProfileSource] = []
    seen: set[str] = set()
    for source in values:
        key = source.value.casefold()
        if key not in seen:
            deduped.append(source)
            seen.add(key)
    return tuple(deduped)


def _repository_classifications(contents: Mapping[str, bytes]) -> list[dict[str, Any]]:
    """Return additive, multi-label classifications backed by visible repository files."""
    paths = tuple(sorted(contents))
    lowered = {path.lower() for path in paths}
    source_paths = [path for path in paths if _is_source(path) and not _is_test_file(path)]
    deployment_paths = [
        path for path in paths
        if _is_compose_file(PurePosixPath(path).name)
        or PurePosixPath(path).name.lower().startswith("dockerfile")
        or PurePosixPath(path).suffix.lower() == ".tf"
        or "/k8s/" in f"/{path.lower()}/"
        or "/kubernetes/" in f"/{path.lower()}/"
    ]
    values: dict[str, tuple[float, set[str]]] = {}

    def add(label: str, confidence: float, *evidence_paths: str) -> None:
        evidence = {path for path in evidence_paths if path in contents}
        if not evidence:
            return
        prior = values.get(label)
        if prior is None or confidence > prior[0]:
            values[label] = (confidence, evidence)
        else:
            prior[1].update(evidence)

    monorepo = _monorepo_signals(contents)
    for signal in monorepo:
        add("MONOREPO", 0.98, signal.split("#", 1)[0])
    terraform = [path for path in paths if PurePosixPath(path).suffix.lower() == ".tf"]
    if terraform:
        add("INFRASTRUCTURE_AS_CODE", 1.0, *terraform[:12])
    api_specs = [
        path for path in paths
        if PurePosixPath(path).name.lower() in {
            "openapi.json", "openapi.yaml", "openapi.yml", "swagger.json", "swagger.yaml", "swagger.yml",
        }
    ]
    if api_specs:
        add("API_DEFINITION", 1.0, *api_specs[:12])
    if "dbt_project.yml" in lowered or "dbt_project.yaml" in lowered:
        add("DBT", 1.0, *[path for path in paths if PurePosixPath(path).name.lower().startswith("dbt_project.")])
        add("DATA_ANALYTICS", 0.95, *[path for path in paths if PurePosixPath(path).name.lower().startswith("dbt_project.")])
    databricks = [path for path in paths if "databricks" in path.lower()]
    if databricks:
        add("DATABRICKS", 0.9, *databricks[:12])
        add("DATA_ANALYTICS", 0.85, *databricks[:12])
    notebooks = [path for path in paths if PurePosixPath(path).suffix.lower() == ".ipynb"]
    if notebooks:
        add("NOTEBOOKS", 1.0, *notebooks[:12])
        add("DATA_ANALYTICS", 0.8, *notebooks[:12])
    sql = [path for path in paths if PurePosixPath(path).suffix.lower() == ".sql"]
    migrations = [path for path in sql if {"migration", "migrations"} & set(PurePosixPath(path.lower()).parts)]
    if migrations:
        add("SQL_SCHEMA_MIGRATION", 0.95, *migrations[:12])
    docs = [path for path in paths if _is_readme(path) or "docs" in PurePosixPath(path.lower()).parts]
    if docs and len(docs) >= max(2, len(source_paths)):
        add("DOCUMENTATION", 0.8, *docs[:12])
    serverless = [
        path for path in paths
        if PurePosixPath(path).name.lower() in {"serverless.yml", "serverless.yaml", "template.yaml", "template.yml"}
    ]
    if serverless:
        add("SERVERLESS", 0.95, *serverless)
    gitops = [
        path for path in paths
        if "argocd" in path.lower() or "helmfile" in path.lower()
        or "charts" in PurePosixPath(path.lower()).parts
    ]
    if gitops:
        add("GITOPS", 0.85, *gitops[:12])
    package_manifests = [path for path in paths if PurePosixPath(path).name == "package.json"]
    python_manifests = [path for path in paths if PurePosixPath(path).name == "pyproject.toml"]
    public_manifests: list[str] = []
    cli_manifests: list[str] = []
    frontend_manifests: list[str] = []
    backend_manifests: list[str] = []
    mobile_manifests: list[str] = []
    for path in package_manifests:
        try:
            document = json.loads(contents[path])
        except (UnicodeDecodeError, json.JSONDecodeError):
            continue
        if not isinstance(document, Mapping):
            continue
        dependencies = {
            str(key).lower()
            for field in ("dependencies", "devDependencies")
            if isinstance(document.get(field), Mapping)
            for key in document[field]
        }
        if document.get("private") is not True and document.get("name"):
            public_manifests.append(path)
        if document.get("bin"):
            cli_manifests.append(path)
        if dependencies & {"react", "next", "vue", "@angular/core", "svelte"}:
            frontend_manifests.append(path)
        if dependencies & {"express", "fastify", "koa", "@nestjs/core", "hapi"}:
            backend_manifests.append(path)
        if dependencies & {"react-native", "expo", "@capacitor/core", "cordova"}:
            mobile_manifests.append(path)
    for path in python_manifests:
        try:
            document = tomllib.loads(contents[path].decode("utf-8"))
        except (UnicodeDecodeError, tomllib.TOMLDecodeError):
            continue
        project = document.get("project") if isinstance(document, Mapping) else None
        if isinstance(project, Mapping):
            public_manifests.append(path)
            if project.get("scripts"):
                cli_manifests.append(path)
            dependency_text = " ".join(map(str, project.get("dependencies") or [])).lower()
            if any(item in dependency_text for item in ("fastapi", "django", "flask", "starlette")):
                backend_manifests.append(path)
    if cli_manifests:
        add("CLI", 0.98, *cli_manifests)
    if mobile_manifests:
        add("MOBILE", 0.95, *mobile_manifests)
    if frontend_manifests and backend_manifests:
        add("FULL_STACK_APPLICATION", 0.9, *(frontend_manifests + backend_manifests))
    if public_manifests and not deployment_paths:
        add("LIBRARY_PACKAGE", 0.82, *public_manifests[:12])
    if deployment_paths and not source_paths:
        add("DEPLOYMENT_ONLY", 0.9, *deployment_paths[:12])
    if api_specs and deployment_paths and not monorepo:
        add("MICROSERVICE", 0.8, *(api_specs + deployment_paths)[:12])
    if terraform and len(deployment_paths) >= 3:
        add("PLATFORM", 0.75, *deployment_paths[:12])
    return [
        {
            "classification": label,
            "assertion_class": "INFERRED",
            "confidence": confidence,
            "evidence_paths": sorted(evidence),
            "rule_version": "repository-classification/1.0.0",
        }
        for label, (confidence, evidence) in sorted(values.items())
    ]


def _component_ref(scan_input: ScanInput, component_path: str) -> dict[str, str]:
    normalized = "." if component_path in {"", "."} else str(PurePosixPath(component_path))
    label = "Repository root" if normalized == "." else PurePosixPath(normalized).name
    return {
        "namespace": "ENTERPRISE",
        "type": "Component",
        "key": f"component:{scan_input.repository_key}:{quote(normalized, safe='/')}",
        "name": label,
    }


def _component_facts(
    scan_input: ScanInput,
    contents: Mapping[str, bytes],
    dependencies: list[Dependency],
) -> list[dict[str, Any]]:
    """Promote manifest/build roots to stable, evidence-backed Component entities."""
    descriptors: dict[str, dict[str, Any]] = {}
    for path in sorted(contents):
        name = PurePosixPath(path).name
        if name not in {"package.json", "pyproject.toml", "requirements.txt", "Pipfile"}:
            continue
        component_path = str(PurePosixPath(path).parent)
        descriptors.setdefault(component_path, {"manifests": [], "builds": []})["manifests"].append(path)
    for path in sorted(contents):
        name = PurePosixPath(path).name.lower()
        if name == "dockerfile" or name.startswith("dockerfile."):
            component_path = str(PurePosixPath(path).parent)
            descriptors.setdefault(component_path, {"manifests": [], "builds": []})["builds"].append(path)
    facts: list[dict[str, Any]] = []
    for component_path, descriptor in sorted(descriptors.items()):
        manifests = descriptor["manifests"]
        builds = descriptor["builds"]
        evidence_paths = [*manifests, *builds]
        component_dependencies = [item for item in dependencies if item.component_path == component_path]
        ecosystems = sorted({item.ecosystem for item in component_dependencies})
        component_prefix = "" if component_path == "." else f"{component_path.rstrip('/')}/"
        component_sources = [
            path for path in contents
            if path.startswith(component_prefix) and _is_source(path)
        ]
        languages = sorted({
            label for path in component_sources
            if (label := LANGUAGE_LABELS.get(PurePosixPath(path).suffix.lower())) is not None
        })
        names = {item.normalized_name for item in component_dependencies}
        frameworks = sorted(
            names & {"react", "next", "vue", "svelte", "express", "fastify", "django", "flask", "fastapi"}
        )
        tests = sorted(path for path in component_sources if _is_test_file(path))[:24]
        profile = {
            "record_kind": "component_profile",
            "schema_version": "1.0.0",
            "path": "." if component_path == "." else component_path,
            "component_kind": "SERVICE" if builds else "PACKAGE" if manifests else "APPLICATION",
            "independently_deployable": bool(builds),
            "languages": languages,
            "frameworks": frameworks,
            "ecosystems": ecosystems,
            "build_systems": sorted({
                "NPM" if PurePosixPath(path).name == "package.json" else
                "PYTHON" if PurePosixPath(path).name in {"pyproject.toml", "requirements.txt", "Pipfile"} else
                "DOCKER"
                for path in evidence_paths
            }),
            "runtime": sorted({"NODE" if item.ecosystem == "npm" else "PYTHON" for item in component_dependencies}),
            "entry_points": [],
            "tests": tests,
            "dependency_count": len(component_dependencies),
            "limitations": [
                "component identity is path-stable within a repository; rename reconciliation requires history",
                "independent deployability is declared only when a component-local container build is present",
            ],
            "rule_version": "component-decomposition/1.0.0",
        }
        relation = _entity_relationship_fact(
            scan_input, evidence_paths[0], 1, _repository_ref(scan_input), "CONTAINS",
            _component_ref(scan_input, component_path), profile,
            assertion_class="DECLARED", confidence=0.98,
            evidence_type="COMPONENT_MANIFEST",
        )
        facts.append(relation)
        facts.append({
            "fact_contract_version": "1.0.0",
            "idempotency_key": sha256_key({
                "tenant": scan_input.tenant_key,
                "component": relation["object_entity"]["key"],
                "record_kind": "component_profile",
                "source_revision": scan_input.source_revision,
                "extractor": SCANNER_VERSION,
            }),
            "tenant_key": scan_input.tenant_key,
            "subject": relation["object_entity"],
            "predicate": "HAS_PROPERTY",
            "object_value": profile,
            "assertion_class": "DECLARED",
            "confidence": 0.98,
            "observed_at": scan_input.observed_at,
            "source_revision": scan_input.source_revision,
            "extractor": {"key": SCANNER_KEY, "version": SCANNER_VERSION},
            "properties": {"profile_schema_version": "1.0.0"},
            "evidence": [
                _evidence_dict(Evidence(
                    path=path, evidence_type="COMPONENT_MANIFEST",
                    content_hash=content_hash(contents[path]), locator={"path": path},
                ), scan_input)
                for path in evidence_paths[:12]
            ],
        })
    return facts


def _is_readme(path: str) -> bool:
    pure_path = PurePosixPath(path)
    lower = pure_path.name.lower()
    return (
        (lower == "readme" or lower.startswith("readme."))
        and pure_path.suffix.lower() in README_SUFFIXES
    )


def _readme_lead(content: bytes) -> tuple[str, int, int] | None:
    text = content.decode("utf-8", errors="replace")
    lines = text.splitlines()
    paragraphs: list[tuple[str, int, int]] = []
    current: list[str] = []
    current_start = 1
    in_fence = False
    for index, raw in enumerate(lines, 1):
        stripped = raw.strip()
        if stripped.startswith(("```", "~~~")):
            in_fence = not in_fence
            if current:
                paragraphs.append((" ".join(current), current_start, index - 1))
                current = []
            continue
        if in_fence or not stripped:
            if current:
                paragraphs.append((" ".join(current), current_start, index - 1))
                current = []
            continue
        if stripped.startswith("#") or re.fullmatch(r"[-=]{3,}", stripped):
            continue
        if not current:
            current_start = index
        current.append(stripped)
    if current:
        paragraphs.append((" ".join(current), current_start, len(lines)))
    fallback: tuple[str, int, int] | None = None
    for paragraph, start, end in paragraphs:
        cleaned = _clean_profile_text(paragraph)
        if not cleaned or _readme_boilerplate(cleaned):
            continue
        candidate = (cleaned, start, end)
        if fallback is None:
            fallback = candidate
        if len(cleaned) >= 40:
            return candidate
    return fallback


def _clean_profile_text(value: str) -> str:
    cleaned = re.sub(r"!\[[^\]]*\]\([^)]*\)", " ", value)
    cleaned = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", cleaned)
    cleaned = re.sub(r"<[^>]+>", " ", cleaned)
    cleaned = re.sub(r"[`*_~]", "", cleaned)
    cleaned = re.sub(r"^(?:>|[-+*]|\d+[.)])\s*", "", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    if len(cleaned) > 600:
        shortened = cleaned[:600].rsplit(" ", 1)[0].rstrip(" ,;:-")
        cleaned = f"{shortened}…"
    return cleaned


def _readme_boilerplate(value: str) -> bool:
    lowered = value.casefold()
    return (
        not re.search(r"[a-z]{3}", lowered)
        or lowered.startswith(("table of contents", "license", "contributing", "installation"))
        or "shields.io" in lowered
    )


def _component_label(path: str) -> str:
    parent = str(PurePosixPath(path).parent)
    return "Repository root" if parent == "." else parent


def _repository_operational_signals(contents: Mapping[str, bytes]) -> list[str]:
    signals: set[str] = set()
    for path in contents:
        name = PurePosixPath(path).name.lower()
        suffix = PurePosixPath(path).suffix.lower()
        parts = {part.lower() for part in PurePosixPath(path).parts}
        if name == "dockerfile" or name.startswith("dockerfile."):
            signals.add("Container build")
        if _is_compose_file(name):
            signals.add("Compose deployment")
        if suffix == ".tf":
            signals.add("Terraform infrastructure")
        if suffix in {".yaml", ".yml"} and parts & {"k8s", "kubernetes"}:
            signals.add("Kubernetes deployment")
        if ".github" in parts and "workflows" in parts:
            signals.add("GitHub Actions")
        if name == "makefile":
            signals.add("Make build automation")
    return sorted(signals)


def _repository_key_files(contents: Mapping[str, bytes]) -> list[str]:
    values = [
        path for path in contents
        if _is_readme(path)
        or _is_license(path)
        or _is_codeowners(path)
        or _is_ci_configuration(path)
        or _is_test_file(path)
        or _is_test_configuration(path)
        or PurePosixPath(path).name in {
            "package.json", "pyproject.toml", "requirements.txt", "Pipfile", "Dockerfile", "Makefile",
        }
        or _is_compose_file(PurePosixPath(path).name)
        or PurePosixPath(path).name.lower().startswith("dockerfile.")
        or PurePosixPath(path).suffix.lower() == ".tf"
    ]
    return sorted(values, key=lambda path: (len(PurePosixPath(path).parts), path))[:24]


def _repository_hygiene(contents: Mapping[str, bytes]) -> dict[str, dict[str, Any]]:
    paths = tuple(contents)
    root_readmes = sorted(path for path in paths if len(PurePosixPath(path).parts) == 1 and _is_readme(path))
    licenses = sorted(path for path in paths if len(PurePosixPath(path).parts) == 1 and _is_license(path))
    codeowners = sorted(path for path in paths if _is_codeowners(path))
    ci_configurations = sorted(path for path in paths if _is_ci_configuration(path))
    test_files = sorted(path for path in paths if _is_test_file(path))
    test_configurations = sorted(path for path in paths if _is_test_configuration(path))
    source_files = sorted(path for path in paths if _is_source(path) and not _is_test_file(path))
    dependency_components = _dependency_component_lock_status(contents)
    missing_locks = [
        component["path"] for component in dependency_components if not component["lockfile_present"]
    ]
    return {
        "readme": {"present": bool(root_readmes), "paths": root_readmes},
        "license": {"present": bool(licenses), "paths": licenses},
        "codeowners": {"present": bool(codeowners), "paths": codeowners},
        "ci": {"present": bool(ci_configurations), "paths": ci_configurations},
        "dependency_lockfile": {
            "applicable": bool(dependency_components),
            "present": bool(dependency_components) and not missing_locks,
            "missing_component_paths": missing_locks,
            "components": dependency_components,
        },
        "tests": {
            "applicable": bool(source_files),
            "present": bool(test_files or test_configurations),
            "paths": (test_files + test_configurations)[:24],
        },
    }


def _is_license(path: str) -> bool:
    pure_path = PurePosixPath(path)
    lower = pure_path.name.lower()
    return (
        lower in {"license", "copying"}
        or lower.startswith("license.")
        or lower.startswith("copying.")
    ) and pure_path.suffix.lower() in README_SUFFIXES


def _is_codeowners(path: str) -> bool:
    pure_path = PurePosixPath(path)
    if pure_path.name.casefold() != "codeowners":
        return False
    parent = tuple(part.casefold() for part in pure_path.parts[:-1])
    return parent in {(), (".github",), ("docs",)}


def _is_ci_configuration(path: str) -> bool:
    pure_path = PurePosixPath(path)
    lower = pure_path.name.casefold()
    parts = tuple(part.casefold() for part in pure_path.parts)
    return (
        (len(parts) >= 3 and parts[0:2] == (".github", "workflows")
         and pure_path.suffix.lower() in {".yml", ".yaml"})
        or parts in {(".circleci", "config.yml"), (".circleci", "config.yaml")}
        or (len(parts) == 1 and lower in {
            ".gitlab-ci.yml", ".gitlab-ci.yaml", ".travis.yml", "jenkinsfile",
            "azure-pipelines.yml", "azure-pipelines.yaml", "bitbucket-pipelines.yml",
            "bitbucket-pipelines.yaml",
        })
    )


def _is_test_file(path: str) -> bool:
    pure_path = PurePosixPath(path)
    parts = tuple(part.casefold() for part in pure_path.parts[:-1])
    name = pure_path.name.casefold()
    stem = pure_path.stem.casefold()
    return (
        bool(set(parts) & {"test", "tests", "__tests__", "spec", "specs"})
        or name.startswith("test_")
        or stem.endswith("_test")
        or stem.endswith((".test", ".spec"))
    ) and _is_source(path)


def _is_test_configuration(path: str) -> bool:
    pure_path = PurePosixPath(path)
    lower = pure_path.name.casefold()
    return (
        lower in {"pytest.ini", "tox.ini"}
        or re.fullmatch(
            r"(?:jest|vitest|playwright|cypress)\.config\.(?:js|jsx|mjs|cjs|ts|tsx|mts|cts)",
            lower,
        ) is not None
    )


def _dependency_component_lock_status(contents: Mapping[str, bytes]) -> list[dict[str, Any]]:
    components: list[dict[str, Any]] = []
    for path in sorted(contents):
        name = PurePosixPath(path).name
        if name not in {"package.json", "pyproject.toml", "Pipfile"}:
            continue
        if not _manifest_declares_dependencies(name, contents[path]):
            continue
        directory = str(PurePosixPath(path).parent)
        lock_names = {
            "package.json": ("package-lock.json", "npm-shrinkwrap.json", "pnpm-lock.yaml", "yarn.lock"),
            "pyproject.toml": ("poetry.lock", "uv.lock"),
            "Pipfile": ("Pipfile.lock",),
        }[name]
        lock_path = _nearest_file(contents, directory, lock_names)
        components.append({
            "path": "." if directory == "." else directory,
            "manifest_path": path,
            "lockfile_present": lock_path is not None,
            "lockfile_path": lock_path,
        })
    return components


def _manifest_declares_dependencies(name: str, content: bytes) -> bool:
    try:
        if name == "package.json":
            document = json.loads(content)
            return isinstance(document, Mapping) and any(
                isinstance(document.get(field), (Mapping, list)) and bool(document.get(field))
                for field in ("dependencies", "devDependencies", "optionalDependencies", "peerDependencies")
            )
        if name == "pyproject.toml":
            document = tomllib.loads(content.decode("utf-8"))
            project = document.get("project") if isinstance(document, Mapping) else None
            tool = document.get("tool") if isinstance(document, Mapping) else None
            poetry = tool.get("poetry") if isinstance(tool, Mapping) else None
            return bool(
                (isinstance(project, Mapping) and project.get("dependencies"))
                or (isinstance(poetry, Mapping) and poetry.get("dependencies"))
            )
        return bool(re.search(r"^\s*\[(?:packages|dev-packages)\]\s*$", content.decode("utf-8"), re.M))
    except (UnicodeDecodeError, json.JSONDecodeError, tomllib.TOMLDecodeError):
        return False


def _application_boundary_facts(
    scan_input: ScanInput,
    contents: Mapping[str, bytes],
) -> list[dict[str, Any]]:
    """Emit a transparent, reviewable application boundary for pilot discovery.

    A repository is concrete scan evidence, but it is not always equivalent to one deployable
    application. Until a service catalog or curated mapping supersedes it, this fact creates a
    provisional portfolio boundary and records monorepo ambiguity instead of presenting the
    fallback as authoritative application truth.
    """
    evidence_path = _application_boundary_evidence_path(contents)
    if evidence_path is None:
        return []
    monorepo_signals = _monorepo_signals(contents)
    strategy = "REPOSITORY_PORTFOLIO" if monorepo_signals else "REPOSITORY_FALLBACK"
    confidence = 0.55 if monorepo_signals else 0.8
    application_key = f"application:{scan_input.repository_key}"
    properties = {
        "boundary_strategy": strategy,
        "provisional": True,
        "review_state": "UNREVIEWED",
        "monorepo_signals": monorepo_signals,
        "limitations": [
            "repository boundaries may not match deployable application or service boundaries",
            "replace this provisional mapping with curated catalog, CMDB, or reviewed discovery evidence",
        ],
    }
    identity = {
        "tenant": scan_input.tenant_key,
        "application": application_key,
        "predicate": "IMPLEMENTED_BY",
        "repository": scan_input.repository_key,
        "source_revision": scan_input.source_revision,
        "extractor": SCANNER_VERSION,
    }
    evidence = Evidence(
        path=evidence_path,
        evidence_type="APPLICATION_BOUNDARY",
        content_hash=content_hash(contents[evidence_path]),
        locator={"path": evidence_path},
        metadata={"boundary_strategy": strategy, "monorepo_signals": monorepo_signals},
    )
    return [{
        "fact_contract_version": "1.0.0",
        "idempotency_key": sha256_key(identity),
        "tenant_key": scan_input.tenant_key,
        "subject": {
            "namespace": "ENTERPRISE",
            "type": "Application",
            "key": application_key,
            "name": scan_input.repository_name,
        },
        "predicate": "IMPLEMENTED_BY",
        "object_entity": _repository_ref(scan_input),
        "assertion_class": "INFERRED",
        "confidence": confidence,
        "observed_at": scan_input.observed_at,
        "source_revision": scan_input.source_revision,
        "extractor": {"key": SCANNER_KEY, "version": SCANNER_VERSION},
        "properties": properties,
        "evidence": [_evidence_dict(evidence, scan_input)],
    }]


def _service_boundary_facts(
    scan_input: ScanInput,
    contents: Mapping[str, bytes],
    diagnostics: list[Diagnostic],
) -> list[dict[str, Any]]:
    """Emit logical services from API contracts and explicit deployment definitions.

    Named Compose builds and Kubernetes workloads are stronger boundaries than a bare
    Dockerfile. OpenAPI/Swagger contracts are declared service boundaries and are linked
    to an existing deployment when the match is unambiguous. A Dockerfile is used only as
    a repository-local fallback when neither a named deployment nor an API contract exists.
    Image-only Compose dependencies remain deployment resources so databases and brokers
    are not promoted into enterprise services.
    """
    openapi_definitions = _openapi_definitions(scan_input, contents, diagnostics)
    definitions: list[tuple[str, int, str, str, dict[str, str], float]] = []
    for path, content in sorted(contents.items()):
        name = PurePosixPath(path).name.lower()
        if _is_compose_file(name):
            documents = _decode_yaml_documents(content, path, diagnostics)
            root = documents[0] if documents else None
            if not isinstance(root, Mapping) or not isinstance(root.get("services"), Mapping):
                continue
            text = content.decode("utf-8", errors="replace")
            for service_name, definition in sorted(root["services"].items()):
                if not isinstance(service_name, str) or not isinstance(definition, Mapping):
                    continue
                if not _compose_service_has_local_build(definition):
                    continue
                definitions.append((
                    path,
                    _line_for_yaml_key(text, service_name),
                    service_name,
                    "COMPOSE_BUILD",
                    _deployment_ref(scan_input, path, "compose-service", service_name),
                    1.0,
                ))
        elif PurePosixPath(path).suffix.lower() in {".yaml", ".yml"} and (
            "/k8s/" in f"/{path.lower()}/"
            or "/kubernetes/" in f"/{path.lower()}/"
            or "/deploy/" in f"/{path.lower()}/"
        ):
            documents = _decode_yaml_documents(content, path, diagnostics)
            if documents is None:
                continue
            text = content.decode("utf-8", errors="replace")
            supported = {"Deployment", "StatefulSet", "DaemonSet", "Job", "CronJob", "Pod"}
            for index, document in enumerate(documents):
                if not isinstance(document, Mapping) or document.get("kind") not in supported:
                    continue
                metadata = document.get("metadata") if isinstance(document.get("metadata"), Mapping) else {}
                service_name = str(metadata.get("name") or f"document-{index + 1}")
                namespace = str(metadata.get("namespace") or "default")
                kind = str(document["kind"])
                definitions.append((
                    path,
                    _line_for_yaml_key(text, service_name),
                    service_name,
                    "KUBERNETES_WORKLOAD",
                    _deployment_ref(scan_input, path, kind.lower(), f"{namespace}/{service_name}"),
                    0.9,
                ))

    if not definitions and not openapi_definitions:
        for path, content in sorted(contents.items()):
            name = PurePosixPath(path).name.lower()
            if name != "dockerfile" and not name.startswith("dockerfile."):
                continue
            from_lines = [
                line_number
                for line_number, line in enumerate(content.decode("utf-8", errors="replace").splitlines(), 1)
                if re.match(r"^\s*FROM\s+(?:--platform=\S+\s+)?\S+", line, re.I)
                and not re.match(r"^\s*FROM\s+(?:--platform=\S+\s+)?scratch(?:\s|$)", line, re.I)
            ]
            if not from_lines:
                continue
            definitions.append((
                path,
                from_lines[-1],
                _dockerfile_service_name(scan_input, path),
                "DOCKERFILE_FALLBACK",
                _deployment_ref(scan_input, path, "dockerfile", f"stage-{from_lines[-1]}"),
                0.8,
            ))

    facts: list[dict[str, Any]] = []
    application = _application_ref(scan_input)
    for path, line, service_name, strategy, deployment, confidence in definitions:
        service = _service_ref(scan_input, service_name)
        properties = {
            "source_kind": strategy,
            "boundary_strategy": strategy,
            "provisional": strategy == "DOCKERFILE_FALLBACK",
            "service_name": service_name,
        }
        facts.append(_entity_relationship_fact(
            scan_input, path, line, service, "IMPLEMENTED_BY", _repository_ref(scan_input),
            properties,
            confidence=confidence,
        ))
        facts.append(_entity_relationship_fact(
            scan_input, path, line, application, "CONTAINS", service,
            properties,
            assertion_class="INFERRED",
            confidence=confidence,
        ))
        facts.append(_entity_relationship_fact(
            scan_input, path, line, service, "DEPLOYED_AS", deployment,
            properties,
            confidence=confidence,
        ))

    deployment_names = sorted({definition[2] for definition in definitions})
    emitted_service_keys = {
        fact["subject"]["key"]
        for fact in facts
        if fact.get("predicate") == "IMPLEMENTED_BY"
        and fact.get("subject", {}).get("type") == "Service"
    }
    for definition in openapi_definitions:
        service_name = _openapi_service_name(
            scan_input, definition, deployment_names,
        )
        service = _service_ref(scan_input, service_name)
        api = _api_ref(scan_input, definition.path, definition.title)
        properties = {
            "source_kind": "OPENAPI_CONTRACT",
            "boundary_strategy": "OPENAPI_CONTRACT",
            "provisional": False,
            "service_name": service_name,
            **definition.metadata,
        }
        if service["key"] not in emitted_service_keys:
            facts.append(_entity_relationship_fact(
                scan_input, definition.path, definition.line, service,
                "IMPLEMENTED_BY", _repository_ref(scan_input), properties,
                evidence_type="API_CONTRACT",
            ))
            facts.append(_entity_relationship_fact(
                scan_input, definition.path, definition.line, application,
                "CONTAINS", service, properties,
                assertion_class="INFERRED",
                evidence_type="API_CONTRACT",
            ))
            emitted_service_keys.add(service["key"])
        facts.append(_entity_relationship_fact(
            scan_input, definition.path, definition.line, service,
            "EXPOSES", api, properties,
            evidence_type="API_CONTRACT",
        ))
        facts.append(_openapi_profile_fact(
            scan_input, definition, service, api, properties,
        ))
    return facts


def _compose_service_has_local_build(definition: Mapping[str, Any]) -> bool:
    build = definition.get("build")
    if isinstance(build, str):
        return bool(build.strip())
    if not isinstance(build, Mapping):
        return False
    context = build.get("context")
    dockerfile = build.get("dockerfile")
    return (
        isinstance(context, str) and bool(context.strip())
    ) or (
        isinstance(dockerfile, str) and bool(dockerfile.strip())
    )


def _dockerfile_service_name(scan_input: ScanInput, path: str) -> str:
    file_name = PurePosixPath(path).name
    if "." in file_name:
        suffix = file_name.split(".", 1)[1].strip()
        if suffix:
            return suffix
    parent = PurePosixPath(path).parent
    if str(parent) != ".":
        return parent.name
    return scan_input.repository_name


def _openapi_definitions(
    scan_input: ScanInput,
    contents: Mapping[str, bytes],
    diagnostics: list[Diagnostic],
) -> list[OpenApiDefinition]:
    definitions: list[OpenApiDefinition] = []
    for path, content in sorted(contents.items()):
        if manifest_kind(path) != "API_CONTRACT":
            continue
        try:
            text = content.decode("utf-8")
            document = (
                json.loads(text)
                if PurePosixPath(path).suffix.lower() == ".json"
                else yaml.safe_load(text)
            )
        except (UnicodeDecodeError, json.JSONDecodeError, yaml.YAMLError) as error:
            diagnostics.append(Diagnostic(
                "ERROR", "INVALID_API_CONTRACT", str(error), path,
            ))
            continue
        if not isinstance(document, Mapping):
            diagnostics.append(Diagnostic(
                "WARNING", "INVALID_API_CONTRACT_SIGNATURE",
                "OpenAPI/Swagger contract must be an object", path,
            ))
            continue
        openapi_version = document.get("openapi")
        swagger_version = document.get("swagger")
        if not (
            isinstance(openapi_version, str) and openapi_version.startswith("3.")
        ) and swagger_version != "2.0":
            diagnostics.append(Diagnostic(
                "WARNING", "INVALID_API_CONTRACT_SIGNATURE",
                "Contract does not declare a supported OpenAPI 3.x or Swagger 2.0 version",
                path,
            ))
            continue

        info = document.get("info") if isinstance(document.get("info"), Mapping) else {}
        raw_title = info.get("title")
        title = raw_title.strip() if isinstance(raw_title, str) and raw_title.strip() else ""
        if not title:
            parent = PurePosixPath(path).parent
            title = parent.name if str(parent) != "." else scan_input.repository_name
            diagnostics.append(Diagnostic(
                "WARNING", "OPENAPI_TITLE_MISSING",
                f"Contract info.title is missing; using {title!r} as the service name",
                path,
            ))
        paths = document.get("paths") if isinstance(document.get("paths"), Mapping) else {}
        methods: set[str] = set()
        tags: set[str] = set()
        operation_count = 0
        operation_id_count = 0
        for path_item in paths.values():
            if not isinstance(path_item, Mapping):
                continue
            for method, operation in path_item.items():
                normalized_method = str(method).lower()
                if normalized_method not in HTTP_METHODS or not isinstance(operation, Mapping):
                    continue
                methods.add(normalized_method.upper())
                operation_count += 1
                if isinstance(operation.get("operationId"), str) and operation["operationId"].strip():
                    operation_id_count += 1
                operation_tags = operation.get("tags")
                if isinstance(operation_tags, list):
                    tags.update(
                        value.strip() for value in operation_tags
                        if isinstance(value, str) and value.strip()
                    )
        declared_tags = document.get("tags")
        if isinstance(declared_tags, list):
            tags.update(
                str(value["name"]).strip() for value in declared_tags
                if isinstance(value, Mapping) and isinstance(value.get("name"), str)
                and str(value["name"]).strip()
            )
        components = document.get("components") if isinstance(document.get("components"), Mapping) else {}
        security_schemes = (
            components.get("securitySchemes")
            if isinstance(components.get("securitySchemes"), Mapping)
            else document.get("securityDefinitions")
        )
        servers = document.get("servers")
        server_count = len(servers) if isinstance(servers, list) else int(bool(document.get("host")))
        description = info.get("description")
        metadata: dict[str, Any] = {
            "contract_format": "OPENAPI" if isinstance(openapi_version, str) else "SWAGGER",
            "specification_version": str(openapi_version or swagger_version),
            "contract_path": path,
            "path_count": len(paths),
            "operation_count": operation_count,
            "operation_id_count": operation_id_count,
            "methods": sorted(methods),
            "tags": sorted(tags)[:100],
            "server_count": server_count,
            "security_scheme_count": len(security_schemes) if isinstance(security_schemes, Mapping) else 0,
        }
        service_version = info.get("version")
        if isinstance(service_version, str) and service_version.strip():
            metadata["service_version"] = service_version.strip()[:200]
        if isinstance(description, str) and description.strip():
            metadata["description"] = re.sub(r"\s+", " ", description).strip()[:1000]
        title_pattern = re.compile(r"^[ \t]*(?:[\"']?title[\"']?)[ \t]*:", re.M)
        title_match = title_pattern.search(text)
        line = text.count("\n", 0, title_match.start()) + 1 if title_match else 1
        definitions.append(OpenApiDefinition(path, line, title[:300], metadata))
    return definitions


def _openapi_service_name(
    scan_input: ScanInput,
    definition: OpenApiDefinition,
    deployment_names: list[str],
) -> str:
    title_key = _service_name_key(definition.title)
    title_tokens = _service_identity_tokens(definition.title)
    exact = [
        name for name in deployment_names
        if _service_name_key(name) == title_key
        or (title_tokens and _service_identity_tokens(name) == title_tokens)
    ]
    if len(exact) == 1:
        return exact[0]
    parent = PurePosixPath(definition.path).parent
    parent_keys = {
        _service_name_key(part) for part in parent.parts
        if part not in {".", "docs", "api", "spec", "specs"}
    }
    directory_matches = [
        name for name in deployment_names
        if any(
            _service_name_key(name) == parent_key
            or (
                len(parent_key) >= 3
                and (
                    _service_name_key(name).startswith(parent_key)
                    or parent_key.startswith(_service_name_key(name))
                )
            )
            for parent_key in parent_keys
        )
    ]
    if len(directory_matches) == 1:
        return directory_matches[0]
    if len(deployment_names) == 1:
        return deployment_names[0]
    return definition.title or scan_input.repository_name


def _service_name_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.casefold())


def _service_identity_tokens(value: str) -> frozenset[str]:
    generic = {"api", "http", "internal", "openapi", "public", "rest", "service", "swagger"}
    return frozenset(
        token for token in re.findall(r"[a-z0-9]+", value.casefold())
        if token not in generic
    )


def _api_ref(scan_input: ScanInput, path: str, title: str) -> dict[str, str]:
    return {
        "namespace": "ENTERPRISE",
        "type": "API",
        "key": f"api:{scan_input.repository_key}:{quote(path, safe='.-_~/')}",
        "name": title,
    }


def _openapi_profile_fact(
    scan_input: ScanInput,
    definition: OpenApiDefinition,
    service: Mapping[str, str],
    api: Mapping[str, str],
    properties: Mapping[str, Any],
) -> dict[str, Any]:
    value = {
        "record_kind": "openapi_service_profile",
        "service_name": service["name"],
        "api_key": api["key"],
        "api_name": api["name"],
        **definition.metadata,
    }
    evidence = Evidence(
        path=definition.path,
        evidence_type="API_CONTRACT",
        content_hash=_content_hash_from_evidence_context(
            definition.path, scan_input.checkout_root,
        ),
        locator={
            "path": definition.path,
            "line_start": definition.line,
            "line_end": definition.line,
            "json_pointer": "/info",
        },
        excerpt_hash=sha256_key(definition.path, definition.line, value),
        metadata=properties,
    )
    return {
        "fact_contract_version": "1.0.0",
        "idempotency_key": sha256_key({
            "tenant": scan_input.tenant_key,
            "service": service["key"],
            "profile": value,
            "path": definition.path,
            "source_revision": scan_input.source_revision,
            "extractor": SCANNER_VERSION,
        }),
        "tenant_key": scan_input.tenant_key,
        "subject": dict(service),
        "predicate": "HAS_PROPERTY",
        "object_value": value,
        "assertion_class": "DECLARED",
        "confidence": 1,
        "observed_at": scan_input.observed_at,
        "source_revision": scan_input.source_revision,
        "extractor": {"key": SCANNER_KEY, "version": SCANNER_VERSION},
        "properties": dict(properties),
        "evidence": [_evidence_dict(evidence, scan_input)],
    }


def _application_ref(scan_input: ScanInput) -> dict[str, str]:
    return {
        "namespace": "ENTERPRISE",
        "type": "Application",
        "key": f"application:{scan_input.repository_key}",
        "name": scan_input.repository_name,
    }


def _service_ref(scan_input: ScanInput, name: str) -> dict[str, str]:
    normalized = quote(name.strip().casefold(), safe=".-_~")
    return {
        "namespace": "ENTERPRISE",
        "type": "Service",
        "key": f"service:{scan_input.repository_key}:{normalized}",
        "name": name,
    }


def _database_storage_facts(
    scan_input: ScanInput,
    contents: Mapping[str, bytes],
    dependencies: Iterable[Dependency],
    references: Iterable[Reference],
) -> list[dict[str, Any]]:
    """Correlate repository evidence into normalized database and storage usage.

    Configuration values are intentionally never copied into facts or evidence metadata. The
    scanner records only the key name or URL scheme that supported an inference; the existing
    content-addressed source artifact remains the auditable evidence boundary.
    """
    references_by_dependency: dict[tuple[str, str], list[Reference]] = {}
    for reference in references:
        references_by_dependency.setdefault(
            (reference.ecosystem, reference.package_name), [],
        ).append(reference)

    signals: list[ResourceSignal] = []
    for dependency in dependencies:
        if not dependency.direct:
            continue
        dependency_key = (dependency.ecosystem, dependency.normalized_name)
        resource = RESOURCE_DEPENDENCIES.get(dependency_key)
        if resource is None:
            continue
        package = f"{dependency.ecosystem}:{dependency.normalized_name}"
        signals.append(ResourceSignal(
            resource=resource,
            evidence=dependency.declaration,
            signal_kind="DEPENDENCY_DECLARATION",
            confidence=0.72,
            package=package,
        ))
        for reference in references_by_dependency.get(dependency_key, []):
            signals.append(ResourceSignal(
                resource=resource,
                evidence=Evidence(
                    reference.path,
                    "SOURCE_REFERENCE",
                    content_hash(contents[reference.path]),
                    {
                        "path": reference.path,
                        "line_start": reference.line,
                        "line_end": reference.line,
                    },
                    sha256_key(reference.path, reference.line, sorted(reference.symbols)),
                    {"symbols": sorted(reference.symbols)},
                ),
                signal_kind="SOURCE_REFERENCE",
                confidence=0.9,
                package=package,
            ))

    signals.extend(_source_client_resource_signals(contents))
    signals.extend(_infrastructure_resource_signals(contents))
    candidates = {signal.resource for signal in signals}
    signals.extend(_configuration_resource_signals(contents, candidates))

    grouped: dict[str, list[ResourceSignal]] = {}
    for signal in signals:
        grouped.setdefault(signal.resource.key, []).append(signal)

    facts: list[dict[str, Any]] = []
    for resource_key, resource_signals in sorted(grouped.items()):
        resource = resource_signals[0].resource
        unique_signals = _dedupe_resource_signals(resource_signals)
        signal_kinds = sorted({signal.signal_kind for signal in unique_signals})
        base_confidence = max(signal.confidence for signal in unique_signals)
        confidence = round(min(0.99, base_confidence + 0.03 * (len(signal_kinds) - 1)), 2)
        assertion_class = (
            "DECLARED"
            if any(signal.assertion_class == "DECLARED" for signal in unique_signals)
            else "INFERRED"
        )
        evidence = _dedupe_resource_evidence(unique_signals)
        signal_summaries: list[dict[str, str]] = []
        for signal in unique_signals:
            summary = {
                "kind": signal.signal_kind,
                "path": signal.evidence.path,
            }
            if signal.package:
                summary["package"] = signal.package
            if signal.config_key:
                summary["config_key"] = signal.config_key
            if signal.detail:
                summary["detail"] = signal.detail
            signal_summaries.append(summary)
        properties: dict[str, Any] = {
            "resource_kind": resource.entity_type.upper(),
            "engine": resource.engine,
            "inference_method": "CORRELATED_REPOSITORY_EVIDENCE",
            "signal_kinds": signal_kinds,
            "signals": signal_summaries,
            "package_dependencies": sorted({
                signal.package for signal in unique_signals if signal.package
            }),
            "config_keys": sorted({
                signal.config_key for signal in unique_signals if signal.config_key
            }),
            "source_referenced": any(
                signal.signal_kind in {"SOURCE_REFERENCE", "CLIENT_CONSTRUCTION"}
                for signal in unique_signals
            ),
            "limitations": [
                "declared client libraries can be present without a live connection",
                "configuration values and credentials are not copied into normalized facts",
                "runtime connectivity requires deployment or telemetry corroboration",
            ],
        }
        providers = sorted({
            provider
            for signal in unique_signals
            if (provider := signal.provider or signal.resource.provider)
        })
        if providers:
            properties["providers"] = providers
        facts.append({
            "fact_contract_version": "1.0.0",
            "idempotency_key": sha256_key({
                "tenant": scan_input.tenant_key,
                "repository": scan_input.repository_key,
                "predicate": "USES",
                "resource": resource_key,
                "source_revision": scan_input.source_revision,
                "extractor": SCANNER_VERSION,
            }),
            "tenant_key": scan_input.tenant_key,
            "subject": _repository_ref(scan_input),
            "predicate": "USES",
            "object_entity": {
                "namespace": "TECHNOLOGY",
                "type": resource.entity_type,
                "key": resource.key,
                "name": resource.name,
            },
            "assertion_class": assertion_class,
            "confidence": confidence,
            "observed_at": scan_input.observed_at,
            "source_revision": scan_input.source_revision,
            "extractor": {"key": SCANNER_KEY, "version": SCANNER_VERSION},
            "properties": properties,
            "evidence": [_evidence_dict(item, scan_input) for item in evidence],
        })
    return facts


def _dedupe_resource_signals(signals: Iterable[ResourceSignal]) -> list[ResourceSignal]:
    indexed: dict[tuple[object, ...], ResourceSignal] = {}
    for signal in signals:
        key = (
            signal.resource.key,
            signal.signal_kind,
            signal.evidence.path,
            canonical_json(signal.evidence.locator),
            signal.package,
            signal.config_key,
            signal.detail,
        )
        indexed.setdefault(key, signal)
    return sorted(
        indexed.values(),
        key=lambda signal: (
            signal.evidence.path,
            int(signal.evidence.locator.get("line_start", 0)),
            signal.signal_kind,
            signal.package or "",
            signal.config_key or "",
            signal.detail or "",
        ),
    )


def _dedupe_resource_evidence(signals: Iterable[ResourceSignal]) -> list[Evidence]:
    indexed: dict[tuple[object, ...], Evidence] = {}
    for signal in signals:
        evidence = signal.evidence
        key = (
            evidence.path,
            evidence.evidence_type,
            canonical_json(evidence.locator),
            evidence.excerpt_hash,
        )
        indexed.setdefault(key, evidence)
    return list(indexed.values())


def _source_client_resource_signals(contents: Mapping[str, bytes]) -> list[ResourceSignal]:
    patterns: tuple[tuple[re.Pattern[str], ResourceTechnology, str], ...] = (
        (re.compile(r"\bsqlite3\.connect\s*\("), SQLITE, "sqlite3.connect"),
        (re.compile(r"\bboto3\.(?:client|resource)\s*\(\s*[\"']s3[\"']"), AMAZON_S3, "boto3:s3"),
        (re.compile(r"\b(?:new\s+)?AWS\.S3\s*\("), AMAZON_S3, "aws-sdk:s3"),
    )
    signals: list[ResourceSignal] = []
    for path, content in sorted(contents.items()):
        if not _is_source(path):
            continue
        text = content.decode("utf-8", errors="replace")
        for line_number, line in enumerate(text.splitlines(), 1):
            for pattern, resource, detail in patterns:
                if not pattern.search(line):
                    continue
                signals.append(ResourceSignal(
                    resource=resource,
                    evidence=_resource_signal_evidence(
                        path, content, line_number, "SOURCE_REFERENCE",
                        "CLIENT_CONSTRUCTION", detail,
                    ),
                    signal_kind="CLIENT_CONSTRUCTION",
                    confidence=0.92,
                    detail=detail,
                ))
    return signals


def _configuration_resource_signals(
    contents: Mapping[str, bytes],
    candidates: set[ResourceTechnology],
) -> list[ResourceSignal]:
    signals: list[ResourceSignal] = []
    database_candidates = {
        resource for resource in candidates
        if resource.entity_type == "Database" and resource.engine != "redis"
    }
    storage_candidates = {
        resource for resource in candidates if resource.entity_type == "Storage"
    }
    for path, content in sorted(contents.items()):
        if not _is_configuration_signal_path(path):
            continue
        text = content.decode("utf-8", errors="replace")
        for line_number, line in enumerate(text.splitlines(), 1):
            for pattern, resource, scheme in URL_SCHEME_RESOURCES:
                if pattern.search(line):
                    signals.append(ResourceSignal(
                        resource=resource,
                        evidence=_resource_signal_evidence(
                            path, content, line_number, "CONFIG_REFERENCE",
                            "URL_SCHEME", scheme,
                        ),
                        signal_kind="URL_SCHEME",
                        confidence=0.96,
                        assertion_class="DECLARED",
                        detail=scheme,
                    ))
            for key in sorted(set(CONFIG_KEY.findall(line))):
                matched_resources = {
                    resource
                    for pattern, resource in CONFIG_KEY_RESOURCES
                    if pattern.search(key)
                }
                if _generic_database_config_key(key) and len(database_candidates) == 1:
                    matched_resources.update(database_candidates)
                if _generic_storage_config_key(key) and len(storage_candidates) == 1:
                    matched_resources.update(storage_candidates)
                for resource in sorted(matched_resources, key=lambda item: item.key):
                    signals.append(ResourceSignal(
                        resource=resource,
                        evidence=_resource_signal_evidence(
                            path, content, line_number, "CONFIG_REFERENCE",
                            "CONFIG_KEY", key,
                        ),
                        signal_kind="CONFIG_KEY",
                        confidence=0.84,
                        assertion_class="DECLARED",
                        config_key=key,
                    ))
    return signals


def _is_configuration_signal_path(path: str) -> bool:
    pure_path = PurePosixPath(path)
    name = pure_path.name.lower()
    parts = {part.lower() for part in pure_path.parts}
    return (
        _is_source(path)
        or name in {
            ".env.example", ".env.sample", "env.example", "env.sample",
            "application.yml", "application.yaml", "application.properties",
            "appsettings.json", "config.yml", "config.yaml", "config.json", "config.toml",
            "dockerfile",
        }
        or _is_compose_file(name)
        or name.startswith("dockerfile.")
        or (
            (name.startswith(".env.") or name.startswith("env."))
            and name.endswith((".example", ".sample", ".template"))
        )
        or bool(parts & {"config", "deploy", "deployment", "k8s", "kubernetes"})
    )


def _generic_database_config_key(key: str) -> bool:
    return key in GENERIC_DATABASE_CONFIG_KEYS or key.endswith(tuple(
        f"_{value}" for value in GENERIC_DATABASE_CONFIG_KEYS
    ))


def _generic_storage_config_key(key: str) -> bool:
    return key in GENERIC_STORAGE_CONFIG_KEYS or key.endswith(tuple(
        f"_{value}" for value in GENERIC_STORAGE_CONFIG_KEYS
    ))


def _infrastructure_resource_signals(contents: Mapping[str, bytes]) -> list[ResourceSignal]:
    signals: list[ResourceSignal] = []
    terraform_pattern = re.compile(
        r'^\s*resource\s+"(?P<type>[A-Za-z0-9_-]+)"\s+"(?P<name>[A-Za-z0-9_-]+)"',
        re.M,
    )
    for path, content in sorted(contents.items()):
        name = PurePosixPath(path).name.lower()
        text = content.decode("utf-8", errors="replace")
        if _is_compose_file(name):
            try:
                document = next(yaml.safe_load_all(text), None)
            except yaml.YAMLError:
                document = None
            services = document.get("services") if isinstance(document, Mapping) else None
            if isinstance(services, Mapping):
                for service_name, definition in sorted(services.items()):
                    image = definition.get("image") if isinstance(definition, Mapping) else None
                    resource = _resource_from_container_image(image) if isinstance(image, str) else None
                    if resource is None:
                        continue
                    line = _line_for_yaml_key(text, str(service_name))
                    signals.append(ResourceSignal(
                        resource=resource,
                        evidence=_resource_signal_evidence(
                            path, content, line, "DEPLOYMENT_CONFIG", "COMPOSE_IMAGE", image,
                        ),
                        signal_kind="COMPOSE_IMAGE",
                        confidence=0.98,
                        assertion_class="DECLARED",
                        provider=resource.provider,
                        detail=image,
                    ))
        elif PurePosixPath(path).suffix.lower() in {".yaml", ".yml"} and (
            "/k8s/" in f"/{path.lower()}/"
            or "/kubernetes/" in f"/{path.lower()}/"
            or "/deploy/" in f"/{path.lower()}/"
        ):
            try:
                documents = list(yaml.safe_load_all(text))
            except yaml.YAMLError:
                documents = []
            for document in documents:
                if not isinstance(document, Mapping):
                    continue
                for image in _kubernetes_images(document):
                    resource = _resource_from_container_image(image)
                    if resource is None:
                        continue
                    metadata = document.get("metadata") if isinstance(document.get("metadata"), Mapping) else {}
                    workload_name = str(metadata.get("name") or "document")
                    line = _line_for_yaml_key(text, workload_name)
                    signals.append(ResourceSignal(
                        resource=resource,
                        evidence=_resource_signal_evidence(
                            path, content, line, "DEPLOYMENT_CONFIG", "KUBERNETES_IMAGE", image,
                        ),
                        signal_kind="KUBERNETES_IMAGE",
                        confidence=0.98,
                        assertion_class="DECLARED",
                        provider=resource.provider,
                        detail=image,
                    ))
        elif PurePosixPath(path).suffix.lower() == ".tf":
            for match in terraform_pattern.finditer(text):
                resource_type = match.group("type").lower()
                resource_name = match.group("name")
                block = _terraform_resource_block(text, match)
                resource = _resource_from_terraform(resource_type, block)
                if resource is None:
                    continue
                line = text.count("\n", 0, match.start()) + 1
                detail = f"{resource_type}.{resource_name}"
                signals.append(ResourceSignal(
                    resource=resource,
                    evidence=_resource_signal_evidence(
                        path, content, line, "DEPLOYMENT_CONFIG", "TERRAFORM_RESOURCE", detail,
                    ),
                    signal_kind="TERRAFORM_RESOURCE",
                    confidence=0.98,
                    assertion_class="DECLARED",
                    provider=resource.provider,
                    detail=detail,
                ))
    return signals


def _resource_signal_evidence(
    path: str,
    content: bytes,
    line: int,
    evidence_type: str,
    signal_kind: str,
    safe_detail: str,
) -> Evidence:
    return Evidence(
        path=path,
        evidence_type=evidence_type,
        content_hash=content_hash(content),
        locator={"path": path, "line_start": line, "line_end": line},
        excerpt_hash=sha256_key(path, line, signal_kind, safe_detail),
        metadata={"signal_kind": signal_kind, "detail": safe_detail},
    )


def _resource_from_container_image(image: str) -> ResourceTechnology | None:
    repository = image.split("@", 1)[0].rsplit("/", 1)[-1].split(":", 1)[0].lower()
    if repository in {"postgres", "postgis", "timescaledb"}:
        return POSTGRESQL
    if repository in {"mysql", "mariadb", "percona"}:
        return MYSQL
    if repository in {"mongo", "mongodb"}:
        return MONGODB
    if repository in {"redis", "valkey", "keydb"}:
        return REDIS
    if repository in {"minio"}:
        return S3_COMPATIBLE
    if repository in {"dynamodb-local"}:
        return DYNAMODB
    return None


def _is_compose_file(name: str) -> bool:
    return COMPOSE_FILE.fullmatch(name) is not None


def _terraform_resource_block(text: str, match: re.Match[str]) -> str:
    opening = text.find("{", match.end())
    if opening < 0:
        return ""
    closing = _matching_brace(text, opening)
    return text[opening + 1:closing] if closing is not None else ""


def _resource_from_terraform(
    resource_type: str, block: str,
) -> ResourceTechnology | None:
    if "postgresql" in resource_type:
        return POSTGRESQL
    if "mysql" in resource_type or "mariadb" in resource_type:
        return MYSQL
    if "mongodb" in resource_type or resource_type.startswith("mongodbatlas_"):
        return MONGODB
    if "redis" in resource_type or resource_type.startswith("aws_elasticache_"):
        return REDIS
    resource = TERRAFORM_RESOURCE_TECHNOLOGIES.get(resource_type)
    engine_match = re.search(
        r'\b(?:engine|database_version)\s*=\s*"(?P<engine>[^"]+)"', block, re.I,
    )
    if engine_match:
        engine = engine_match.group("engine").lower()
        if "postgres" in engine:
            return POSTGRESQL
        if "mysql" in engine or "maria" in engine:
            return MYSQL
        if "mongo" in engine:
            return MONGODB
        if "redis" in engine or "valkey" in engine:
            return REDIS
    return resource


def _deployment_facts(
    scan_input: ScanInput,
    contents: Mapping[str, bytes],
    diagnostics: list[Diagnostic],
) -> list[dict[str, Any]]:
    facts: list[dict[str, Any]] = []
    for path, content in sorted(contents.items()):
        name = PurePosixPath(path).name.lower()
        if name == "dockerfile" or name.startswith("dockerfile."):
            facts.extend(_dockerfile_facts(scan_input, path, content))
        elif _is_compose_file(name):
            facts.extend(_compose_facts(scan_input, path, content, diagnostics))
        elif PurePosixPath(path).suffix.lower() in {".yaml", ".yml"} and (
            "/k8s/" in f"/{path.lower()}/"
            or "/kubernetes/" in f"/{path.lower()}/"
            or "/deploy/" in f"/{path.lower()}/"
        ):
            facts.extend(_kubernetes_facts(scan_input, path, content, diagnostics))
        elif PurePosixPath(path).suffix.lower() == ".tf":
            facts.extend(_terraform_facts(scan_input, path, content))
    facts.extend(_deployment_profile_facts(scan_input, contents, diagnostics))
    return facts


def _deployment_profile_facts(
    scan_input: ScanInput,
    contents: Mapping[str, bytes],
    diagnostics: list[Diagnostic],
) -> list[dict[str, Any]]:
    providers: set[str] = set()
    workload_types: set[str] = set()
    environments: set[str] = set()
    evidence_paths: list[str] = []
    for path, content in sorted(contents.items()):
        name = PurePosixPath(path).name.lower()
        lowered_path = path.lower()
        if name == "dockerfile" or name.startswith("dockerfile."):
            workload_types.add("CONTAINER_BUILD")
            evidence_paths.append(path)
        elif _is_compose_file(name):
            documents = _decode_yaml_documents(content, path, diagnostics)
            root = documents[0] if documents else None
            if isinstance(root, Mapping) and isinstance(root.get("services"), Mapping):
                workload_types.add("COMPOSE_SERVICE")
                environments.add("local-compose")
                evidence_paths.append(path)
        elif PurePosixPath(path).suffix.lower() in {".yaml", ".yml"} and (
            "/k8s/" in f"/{path.lower()}/"
            or "/kubernetes/" in f"/{path.lower()}/"
            or "/deploy/" in f"/{path.lower()}/"
        ):
            documents = _decode_yaml_documents(content, path, diagnostics)
            found = False
            for document in documents or []:
                if not isinstance(document, Mapping) or not document.get("kind"):
                    continue
                workload_types.add(f"KUBERNETES_{str(document['kind']).upper()}")
                metadata = document.get("metadata") if isinstance(document.get("metadata"), Mapping) else {}
                environments.add(str(metadata.get("namespace") or "default"))
                found = True
            if found:
                evidence_paths.append(path)
        elif PurePosixPath(path).suffix.lower() == ".tf":
            text = content.decode("utf-8", errors="replace")
            for provider, prefix in (("AWS", "aws_"), ("GCP", "google_"), ("AZURE", "azurerm_")):
                if re.search(rf'\bresource\s+"{prefix}', text):
                    providers.add(provider)
            if re.search(r'\bresource\s+"', text):
                workload_types.add("TERRAFORM_RESOURCE")
                evidence_paths.append(path)
        elif name == "vercel.json":
            providers.add("VERCEL")
            workload_types.add("WEB_APPLICATION")
            evidence_paths.append(path)
        elif lowered_path == "supabase/config.toml" or lowered_path.startswith("supabase/migrations/"):
            providers.add("SUPABASE")
            workload_types.add("MANAGED_BACKEND")
            if lowered_path.startswith("supabase/migrations/"):
                workload_types.add("DATABASE_MIGRATION")
            evidence_paths.append(path)
        elif name in {"serverless.yml", "serverless.yaml", "template.yaml", "template.yml"}:
            text = content.decode("utf-8", errors="replace")
            provider_match = re.search(r"(?im)^\s*name\s*:\s*(aws|google|gcp|azure)\s*$", text)
            provider_name = provider_match.group(1).lower() if provider_match else ""
            if provider_name == "aws" or "AWS::Serverless::" in text:
                providers.add("AWS")
            elif provider_name in {"google", "gcp"}:
                providers.add("GCP")
            elif provider_name == "azure":
                providers.add("AZURE")
            workload_types.add("SERVERLESS_FUNCTION")
            evidence_paths.append(path)
        elif name in {"app.yaml", "app.yml"}:
            providers.add("GCP")
            workload_types.add("APP_ENGINE_SERVICE")
            evidence_paths.append(path)
        elif name in {"cloudbuild.yaml", "cloudbuild.yml"}:
            providers.add("GCP")
            workload_types.add("BUILD_PIPELINE")
            evidence_paths.append(path)
        elif name == "azure.yaml":
            providers.add("AZURE")
            workload_types.add("AZURE_DEVELOPER_PROJECT")
            evidence_paths.append(path)
        elif name in {"host.json", "function.json"}:
            providers.add("AZURE")
            workload_types.add("SERVERLESS_FUNCTION")
            evidence_paths.append(path)
        elif name in {"databricks.yml", "databricks.yaml", "databricks.json"}:
            providers.add("DATABRICKS")
            workload_types.add("DATABRICKS_BUNDLE")
            evidence_paths.append(path)
        elif (
            name in {"item.metadata.json", "platform.json"}
            or ".platform" in PurePosixPath(lowered_path).parts
            or "fabric" in PurePosixPath(lowered_path).parts
        ):
            providers.add("MICROSOFT_FABRIC")
            workload_types.add("FABRIC_ITEM")
            evidence_paths.append(path)
    if not evidence_paths:
        return []
    profile = {
        "record_kind": "deployment_profile",
        "schema_version": "1.0.0",
        "providers": sorted(providers),
        "workload_types": sorted(workload_types),
        "environments": sorted(environments),
        "verification_level": "DECLARED_CONFIGURATION",
        "coverage": {
            "live_state": "NOT_VERIFIED",
            "registry_metadata": "NOT_COLLECTED",
            "configuration": "AVAILABLE",
        },
        "limitations": [
            "deployment configuration does not prove that a workload is currently deployed",
            "provider, environment, and workload fields are omitted when configuration does not declare them",
        ],
        "rule_version": "deployment-profile/1.1.0",
    }
    return [{
        "fact_contract_version": "1.0.0",
        "idempotency_key": sha256_key({
            "tenant": scan_input.tenant_key,
            "repository": scan_input.repository_key,
            "record_kind": "deployment_profile",
            "source_revision": scan_input.source_revision,
            "extractor": SCANNER_VERSION,
        }),
        "tenant_key": scan_input.tenant_key,
        "subject": _repository_ref(scan_input),
        "predicate": "HAS_PROPERTY",
        "object_value": profile,
        "assertion_class": "DECLARED",
        "confidence": 0.95,
        "observed_at": scan_input.observed_at,
        "source_revision": scan_input.source_revision,
        "extractor": {"key": SCANNER_KEY, "version": SCANNER_VERSION},
        "properties": {"profile_schema_version": "1.0.0"},
        "evidence": [
            _evidence_dict(Evidence(
                path=path, evidence_type="DEPLOYMENT_CONFIG",
                content_hash=content_hash(contents[path]), locator={"path": path},
            ), scan_input)
            for path in dict.fromkeys(evidence_paths)
        ],
    }]


def _dockerfile_facts(
    scan_input: ScanInput, path: str, content: bytes,
) -> list[dict[str, Any]]:
    text = content.decode("utf-8", errors="replace")
    facts: list[dict[str, Any]] = []
    for line_number, line in enumerate(text.splitlines(), 1):
        match = re.match(r"^\s*FROM\s+(?:--platform=\S+\s+)?(?P<image>\S+)", line, re.I)
        if not match:
            continue
        image = match.group("image")
        if image.lower() == "scratch":
            continue
        built_image = {
            "namespace": "DEPLOYMENT", "type": "ContainerImage",
            "key": f"container-build:{scan_input.repository_key}:{path}",
            "name": f"Local build from {path}",
        }
        component_path = str(PurePosixPath(path).parent)
        facts.append(_entity_relationship_fact(
            scan_input, path, line_number, _component_ref(scan_input, component_path),
            "BUILDS", built_image,
            {"source_kind": "DOCKERFILE", "verification_level": "DECLARED_CONFIGURATION"},
        ))
        facts.append(_entity_relationship_fact(
            scan_input, path, line_number, built_image, "BASED_ON",
            _container_image_ref(image),
            {"source_kind": "DOCKERFILE", **_container_image_properties(image)},
        ))
        deployment = _deployment_ref(scan_input, path, "dockerfile", f"stage-{line_number}")
        facts.append(_entity_relationship_fact(
            scan_input, path, line_number, _repository_ref(scan_input), "DEPLOYED_AS",
            deployment, {"source_kind": "DOCKERFILE", "stage": line_number},
        ))
        facts.append(_entity_relationship_fact(
            scan_input, path, line_number, deployment, "RUNS_ON",
            _container_image_ref(image),
            {"source_kind": "DOCKERFILE", **_container_image_properties(image)},
        ))
    return facts


def _compose_facts(
    scan_input: ScanInput, path: str, content: bytes, diagnostics: list[Diagnostic],
) -> list[dict[str, Any]]:
    document = _decode_yaml_documents(content, path, diagnostics)
    if document is None:
        return []
    root = document[0] if document else None
    if not isinstance(root, Mapping) or not isinstance(root.get("services"), Mapping):
        return []
    text = content.decode("utf-8", errors="replace")
    facts: list[dict[str, Any]] = []
    for service_name, definition in sorted(root["services"].items()):
        if not isinstance(service_name, str) or not isinstance(definition, Mapping):
            continue
        line = _line_for_yaml_key(text, service_name)
        deployment = _deployment_ref(scan_input, path, "compose-service", service_name)
        facts.append(_entity_relationship_fact(
            scan_input, path, line, _repository_ref(scan_input), "DEPLOYED_AS", deployment,
            {"source_kind": "COMPOSE", "service": service_name},
        ))
        image = definition.get("image")
        if isinstance(image, str) and image.strip():
            facts.append(_entity_relationship_fact(
                scan_input, path, line, deployment, "RUNS_ON", _container_image_ref(image.strip()),
                {"source_kind": "COMPOSE", "service": service_name,
                 **_container_image_properties(image.strip())},
            ))
    return facts


def _kubernetes_facts(
    scan_input: ScanInput, path: str, content: bytes, diagnostics: list[Diagnostic],
) -> list[dict[str, Any]]:
    documents = _decode_yaml_documents(content, path, diagnostics)
    if documents is None:
        return []
    text = content.decode("utf-8", errors="replace")
    facts: list[dict[str, Any]] = []
    supported = {"Deployment", "StatefulSet", "DaemonSet", "Job", "CronJob", "Pod"}
    for index, document in enumerate(documents):
        if not isinstance(document, Mapping):
            continue
        metadata = document.get("metadata") if isinstance(document.get("metadata"), Mapping) else {}
        workload_name = str(metadata.get("name") or f"document-{index + 1}")
        namespace = str(metadata.get("namespace") or "default")
        line = _line_for_yaml_key(text, workload_name)
        kind = str(document.get("kind") or "")
        exposure = _kubernetes_external_exposure(document)
        if exposure is not None:
            entrypoint = {
                "namespace": "DEPLOYMENT", "type": "InfrastructureResource",
                "key": f"kubernetes:{scan_input.repository_key}:{kind.lower()}:{namespace}/{workload_name}",
                "name": f"{kind} {namespace}/{workload_name}",
            }
            facts.append(_entity_relationship_fact(
                scan_input, path, line, _repository_ref(scan_input), "USES", entrypoint,
                {"source_kind": "KUBERNETES", "kind": kind, "namespace": namespace,
                 "external_exposure": exposure},
            ))
        if kind not in supported:
            continue
        deployment = _deployment_ref(
            scan_input, path, kind.lower(), f"{namespace}/{workload_name}",
        )
        facts.append(_entity_relationship_fact(
            scan_input, path, line, _repository_ref(scan_input), "DEPLOYED_AS", deployment,
            {"source_kind": "KUBERNETES", "kind": document["kind"], "namespace": namespace},
        ))
        environment = {
            "namespace": "DEPLOYMENT", "type": "Environment",
            "key": f"environment:{scan_input.repository_key}:kubernetes:{namespace}",
            "name": namespace,
        }
        facts.append(_entity_relationship_fact(
            scan_input, path, line, deployment, "LOCATED_IN", environment,
            {"source_kind": "KUBERNETES", "namespace": namespace},
        ))
        for image in _kubernetes_images(document):
            facts.append(_entity_relationship_fact(
                scan_input, path, line, deployment, "RUNS_ON", _container_image_ref(image),
                {"source_kind": "KUBERNETES", "kind": document["kind"],
                 **_container_image_properties(image)},
            ))
    return facts


def _kubernetes_external_exposure(document: Mapping[str, Any]) -> str | None:
    """Return only exposure explicitly declared by Kubernetes configuration."""
    kind = str(document.get("kind") or "")
    metadata = document.get("metadata") if isinstance(document.get("metadata"), Mapping) else {}
    annotations = metadata.get("annotations") if isinstance(metadata.get("annotations"), Mapping) else {}
    annotation_text = " ".join(f"{key}={value}" for key, value in annotations.items()).casefold()
    internal = any(token in annotation_text for token in (
        "scheme=internal", "internal=true", "internal-load-balancer=true",
    ))
    if kind == "Service":
        spec = document.get("spec") if isinstance(document.get("spec"), Mapping) else {}
        if spec.get("type") == "LoadBalancer":
            return "PRIVATE" if internal else "PUBLIC"
    if kind == "Ingress":
        if internal:
            return "PRIVATE"
        if any(token in annotation_text for token in ("internet-facing", "external", "public")):
            return "PUBLIC"
    return None


def _terraform_facts(
    scan_input: ScanInput, path: str, content: bytes,
) -> list[dict[str, Any]]:
    text = content.decode("utf-8", errors="replace")
    facts: list[dict[str, Any]] = []
    pattern = re.compile(
        r'^\s*resource\s+"(?P<type>[A-Za-z0-9_-]+)"\s+"(?P<name>[A-Za-z0-9_-]+)"',
        re.M,
    )
    for match in pattern.finditer(text):
        line = text.count("\n", 0, match.start()) + 1
        resource_type = match.group("type")
        resource_name = match.group("name")
        resource = {
            "namespace": "DEPLOYMENT", "type": "InfrastructureResource",
            "key": f"terraform:{scan_input.repository_key}:{resource_type}:{resource_name}",
            "name": f"{resource_type}.{resource_name}",
        }
        facts.append(_entity_relationship_fact(
            scan_input, path, line, _repository_ref(scan_input), "USES", resource,
            {"source_kind": "TERRAFORM", "resource_type": resource_type,
             "resource_name": resource_name},
        ))
    return facts


def _decode_yaml_documents(
    content: bytes, path: str, diagnostics: list[Diagnostic],
) -> list[Any] | None:
    try:
        return list(yaml.safe_load_all(content.decode("utf-8")))
    except (UnicodeDecodeError, yaml.YAMLError) as error:
        diagnostics.append(Diagnostic("ERROR", "INVALID_DEPLOYMENT_YAML", str(error), path))
        return None


def _kubernetes_images(document: Mapping[str, Any]) -> list[str]:
    spec = document.get("spec")
    if not isinstance(spec, Mapping):
        return []
    if document.get("kind") == "CronJob":
        spec = spec.get("jobTemplate", {}).get("spec", {}) if isinstance(spec.get("jobTemplate"), Mapping) else {}
    template = spec.get("template") if isinstance(spec, Mapping) else None
    pod_spec = template.get("spec") if isinstance(template, Mapping) else spec
    if not isinstance(pod_spec, Mapping):
        return []
    values: set[str] = set()
    for key in ("initContainers", "containers"):
        containers = pod_spec.get(key)
        if not isinstance(containers, list):
            continue
        for container in containers:
            image = container.get("image") if isinstance(container, Mapping) else None
            if isinstance(image, str) and image.strip():
                values.add(image.strip())
    return sorted(values)


def _line_for_yaml_key(text: str, key: str) -> int:
    pattern = re.compile(rf"^\s*(?:name:\s*)?{re.escape(key)}\s*:\s*|^\s*name:\s*{re.escape(key)}\s*$", re.M)
    match = pattern.search(text)
    return text.count("\n", 0, match.start()) + 1 if match else 1


def _deployment_ref(
    scan_input: ScanInput, path: str, kind: str, name: str,
) -> dict[str, str]:
    return {
        "namespace": "DEPLOYMENT", "type": "Deployment",
        "key": f"deployment:{scan_input.repository_key}:{path}:{kind}:{name}",
        "name": name,
    }


def _container_image_ref(image: str) -> dict[str, str]:
    properties = _container_image_properties(image)
    identity = properties["image_digest"] or image
    return {
        "namespace": "DEPLOYMENT", "type": "ContainerImage",
        "key": f"container-image:{identity}", "name": image,
    }


def _container_image_properties(image: str) -> dict[str, Any]:
    digest_match = re.search(r"@(?P<digest>sha256:[a-fA-F0-9]{64})$", image)
    without_digest = image.rsplit("@", 1)[0] if digest_match else image
    last_segment = without_digest.rsplit("/", 1)[-1]
    tag = last_segment.rsplit(":", 1)[1] if ":" in last_segment else None
    repository = (
        without_digest.rsplit(":", 1)[0]
        if tag is not None else without_digest
    )
    digest = digest_match.group("digest").lower() if digest_match else None
    return {
        "image": image,
        "image_repository": repository,
        "image_tag": tag,
        "image_digest": digest,
        "identity_state": "DIGEST_RESOLVED" if digest else "MUTABLE_TAG_UNRESOLVED",
        "verification_level": "DECLARED_CONFIGURATION",
        "limitations": [] if digest else [
            "mutable image tag is an observation and does not identify immutable composition",
        ],
    }


def _entity_relationship_fact(
    scan_input: ScanInput,
    path: str,
    line: int,
    subject: Mapping[str, str],
    predicate: str,
    object_entity: Mapping[str, str],
    properties: Mapping[str, Any],
    *,
    assertion_class: str = "DECLARED",
    confidence: float = 1,
    evidence_type: str = "DEPLOYMENT_CONFIG",
) -> dict[str, Any]:
    evidence = Evidence(
        path=path,
        evidence_type=evidence_type,
        content_hash=_content_hash_from_evidence_context(path, scan_input.checkout_root),
        locator={"path": path, "line_start": line, "line_end": line},
        excerpt_hash=sha256_key(path, line, predicate, object_entity["key"]),
        metadata=properties,
    )
    return {
        "fact_contract_version": "1.0.0",
        "idempotency_key": sha256_key({
            "tenant": scan_input.tenant_key,
            "subject": subject["key"],
            "predicate": predicate,
            "object": object_entity["key"],
            "path": path,
            "line": line,
            "source_revision": scan_input.source_revision,
            "extractor": SCANNER_VERSION,
        }),
        "tenant_key": scan_input.tenant_key,
        "subject": dict(subject),
        "predicate": predicate,
        "object_entity": dict(object_entity),
        "assertion_class": assertion_class,
        "confidence": confidence,
        "observed_at": scan_input.observed_at,
        "source_revision": scan_input.source_revision,
        "extractor": {"key": SCANNER_KEY, "version": SCANNER_VERSION},
        "properties": dict(properties),
        "evidence": [_evidence_dict(evidence, scan_input)],
    }


def _application_boundary_evidence_path(contents: Mapping[str, bytes]) -> str | None:
    preferred_names = (
        "package.json", "pyproject.toml", "requirements.txt", "Dockerfile",
        "compose.yaml", "compose.yml", "docker-compose.yaml", "docker-compose.yml",
        "openapi.json", "openapi.yaml", "openapi.yml",
    )
    for name in preferred_names:
        matches = sorted(path for path in contents if PurePosixPath(path).name == name)
        if matches:
            return min(matches, key=lambda path: (len(PurePosixPath(path).parts), path))
    deployment_configs = sorted(
        path for path in contents
        if _is_compose_file(PurePosixPath(path).name)
        or PurePosixPath(path).name.lower().startswith("dockerfile.")
    )
    if deployment_configs:
        return min(deployment_configs, key=lambda path: (len(PurePosixPath(path).parts), path))
    return min(contents, default=None, key=lambda path: (len(PurePosixPath(path).parts), path))


def _monorepo_signals(contents: Mapping[str, bytes]) -> list[str]:
    signals: list[str] = []
    if "pnpm-workspace.yaml" in contents:
        signals.append("pnpm-workspace.yaml")
    root_manifest = contents.get("package.json")
    if root_manifest is not None:
        try:
            document = json.loads(root_manifest)
        except (UnicodeDecodeError, json.JSONDecodeError):
            document = None
        if isinstance(document, Mapping) and isinstance(document.get("workspaces"), (list, Mapping)):
            signals.append("package.json#workspaces")
    manifest_directories = {
        str(PurePosixPath(path).parent)
        for path in contents
        if PurePosixPath(path).name in {"package.json", "pyproject.toml"}
        and str(PurePosixPath(path).parent) != "."
    }
    if len(manifest_directories) > 1:
        signals.append("multiple-component-manifests")
    return signals


def _usage_limitations(
    ecosystem: str,
    completeness: str,
    reachable_files: set[str] | None,
    runtime: Mapping[tuple[str, str], set[str]] | None,
) -> list[str]:
    values = [
        "dynamic imports, reflection, generated code, plugins, and framework conventions may be missed",
        "distribution-to-import-name matching is heuristic" if ecosystem == "pypi" else "bundler aliases and custom module resolvers may be missed",
    ]
    if completeness != "COMPLETE":
        values.append("repository scan was partial")
    if reachable_files is None:
        values.append("no deterministic entry point was identified; static reachability is unknown")
    if runtime is None:
        values.append("no runtime trace was supplied")
    return values


def normalize_package_name(ecosystem: str, value: str) -> str:
    name = value.strip().lower()
    return PYPI_NORMALIZE.sub("-", name) if ecosystem == "pypi" else name


def _dedupe_dependencies(dependencies: Iterable[Dependency]) -> list[Dependency]:
    indexed: dict[tuple[str, str, str, str, bool, str | None], Dependency] = {}
    for item in dependencies:
        key = (
            item.ecosystem, item.normalized_name, item.component_path,
            item.scope, item.direct, item.resolved_version,
        )
        indexed.setdefault(key, item)
    return list(indexed.values())


def _nearest_file(contents: Mapping[str, bytes], directory: str, names: tuple[str, ...]) -> str | None:
    for parent in _parents(directory):
        for name in names:
            candidate = f"{parent}/{name}" if parent != "." else name
            if candidate in contents:
                return candidate
    return None


def _parents(directory: str) -> Iterable[str]:
    current = PurePosixPath(directory)
    while True:
        value = current.as_posix()
        yield value
        if value == ".":
            return
        current = current.parent


def _json_pointer(value: str) -> str:
    return value.replace("~", "~0").replace("/", "~1")


def _exact_python_version(spec: str) -> str | None:
    match = re.fullmatch(r"\s*==\s*([A-Za-z0-9][A-Za-z0-9._+!-]*)\s*", spec)
    return match.group(1) if match else None


def _javascript_package(module: str) -> str | None:
    if module.startswith((".", "/", "#", "node:", "http:" , "https:")):
        return None
    parts = module.split("/")
    return "/".join(parts[:2]) if module.startswith("@") and len(parts) >= 2 else parts[0]


def _javascript_symbols(clause: str, module: str) -> set[str]:
    values: set[str] = set()
    named = re.search(r"\{([^}]+)\}", clause)
    if named:
        values.update(
            item.strip().split(" as ", 1)[0].strip()
            for item in named.group(1).split(",") if item.strip()
        )
    if "* as" in clause:
        values.add("*")
    prefix = _javascript_package(module)
    if prefix and module != prefix:
        values.add(module[len(prefix):].lstrip("/"))
    if clause.strip() and not named and "* as" not in clause:
        values.add("default")
    return values


def _match_python_distribution(root: str, dependency_names: set[tuple[str, str]]) -> str | None:
    normalized_import = root.lower().replace("_", "-")
    candidates = [name for ecosystem, name in dependency_names if ecosystem == "pypi" and name.replace("_", "-") == normalized_import]
    return candidates[0] if len(candidates) == 1 else None


def _resolve_local_module(path: str, module: str, contents: Mapping[str, bytes]) -> str | None:
    base = PurePosixPath(path).parent.joinpath(module)
    candidates = [base, *[PurePosixPath(str(base) + suffix) for suffix in (".js", ".ts", ".jsx", ".tsx", ".mjs", ".cjs")]]
    candidates.extend(base / name for name in ("index.js", "index.ts", "index.jsx", "index.tsx"))
    for candidate in candidates:
        normalized = _collapse_posix(candidate)
        if normalized in contents:
            return normalized
    return None


def _resolve_python_local(path: str, module: str, level: int, contents: Mapping[str, bytes]) -> str | None:
    base = PurePosixPath(path).parent
    for _ in range(max(0, level - 1)):
        base = base.parent
    parts = [part for part in module.split(".") if part]
    candidate = base.joinpath(*parts)
    for value in (PurePosixPath(str(candidate) + ".py"), candidate / "__init__.py"):
        normalized = _collapse_posix(value)
        if normalized in contents:
            return normalized
    return None


def _collapse_posix(path: PurePosixPath) -> str:
    parts: list[str] = []
    for part in path.parts:
        if part == "..":
            if parts:
                parts.pop()
        elif part not in {".", ""}:
            parts.append(part)
    return "/".join(parts)


def _manifest_entrypoints(contents: Mapping[str, bytes]) -> set[str]:
    entrypoints: set[str] = set()
    for path, content in contents.items():
        if PurePosixPath(path).name == "package.json":
            try:
                document = json.loads(content)
            except (UnicodeDecodeError, json.JSONDecodeError):
                continue
            if not isinstance(document, Mapping):
                continue
            directory = PurePosixPath(path).parent
            for field in ("main", "module"):
                if isinstance(document.get(field), str):
                    entrypoints.add(_collapse_posix(directory / document[field]))
            binary = document.get("bin")
            values = [binary] if isinstance(binary, str) else list(binary.values()) if isinstance(binary, Mapping) else []
            for value in values:
                if isinstance(value, str):
                    entrypoints.add(_collapse_posix(directory / value))
    return entrypoints


def _content_hash_from_evidence_context(path: str, checkout_root: Path) -> str:
    try:
        resolved = (checkout_root / path).resolve()
        if not resolved.is_relative_to(checkout_root) or not resolved.is_file():
            raise OSError
        return content_hash(resolved.read_bytes())
    except OSError:
        return sha256_key(path, "unavailable")


def _is_source(path: str) -> bool:
    return PurePosixPath(path).suffix.lower() in {
        ".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx", ".mts", ".cts", ".py",
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Scan a repository snapshot for dependency and usage evidence")
    parser.add_argument("request", type=Path)
    parser.add_argument("--output", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        request = json.loads(args.request.read_text(encoding="utf-8"))
        result = scan_repository(request)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(json.dumps({"error": type(error).__name__, "message": str(error)}), file=sys.stderr)
        return 2
    output = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.write_text(output, encoding="utf-8")
    else:
        print(output, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
