from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


JsonObject = dict[str, Any]


def canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_key(*parts: object) -> str:
    payload = "\x1f".join(
        part if isinstance(part, str) else canonical_json(part)
        for part in parts
    )
    return f"sha256:{hashlib.sha256(payload.encode('utf-8')).hexdigest()}"


@dataclass(frozen=True, slots=True)
class Catalog:
    seed_dir: Path
    manifest: JsonObject
    domains: list[JsonObject]
    categories: list[JsonObject]
    capabilities: list[JsonObject]
    technologies: list[JsonObject]
    relationships: list[JsonObject]
    assessments: list[JsonObject]
    source_rows: list[JsonObject]

    @property
    def seed_id(self) -> str:
        return str(self.manifest["seed_id"])

    @property
    def seed_version(self) -> str:
        return str(self.manifest["seed_version"])

    @property
    def observed_at(self) -> datetime:
        return datetime.fromisoformat(str(self.manifest["generated_at"]))

    @property
    def bundle_hash(self) -> str:
        return sha256_key(
            self.manifest,
            self.domains,
            self.categories,
            self.capabilities,
            self.technologies,
            self.relationships,
            self.assessments,
            self.source_rows,
        )


def _load_json(path: Path) -> Any:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def load_catalog(seed_dir: Path) -> Catalog:
    catalog = Catalog(
        seed_dir=seed_dir,
        manifest=_load_json(seed_dir / "seed-manifest.json"),
        domains=_load_json(seed_dir / "domains.json"),
        categories=_load_json(seed_dir / "categories.json"),
        capabilities=_load_json(seed_dir / "capabilities.json"),
        technologies=_load_json(seed_dir / "technologies.json"),
        relationships=_load_json(seed_dir / "relationships.json"),
        assessments=_load_json(seed_dir / "assessments.json"),
        source_rows=_load_json(seed_dir / "source-rows.json"),
    )
    validate_catalog(catalog)
    return catalog


def _unique_by_id(records: list[JsonObject], label: str) -> dict[str, JsonObject]:
    indexed: dict[str, JsonObject] = {}
    for record in records:
        record_id = str(record["id"])
        if record_id in indexed:
            raise ValueError(f"duplicate {label} id: {record_id}")
        indexed[record_id] = record
    return indexed


def validate_catalog(catalog: Catalog) -> None:
    hydration = catalog.manifest["hydration"]
    expected_counts = {
        "technology_records": len(catalog.technologies),
        "category_records": len(catalog.categories),
        "capability_records": len(catalog.capabilities),
        "relationship_records": len(catalog.relationships),
        "assessment_records": len(catalog.assessments),
        "raw_table_rows": len(catalog.source_rows),
    }
    for key, actual in expected_counts.items():
        if hydration.get(key) != actual:
            raise ValueError(
                f"manifest {key}={hydration.get(key)!r} does not match {actual}"
            )

    domains = _unique_by_id(catalog.domains, "domain")
    categories = _unique_by_id(catalog.categories, "category")
    capabilities = _unique_by_id(catalog.capabilities, "capability")
    technologies = _unique_by_id(catalog.technologies, "technology")

    for category_id, category in categories.items():
        if category["domain_id"] not in domains:
            raise ValueError(f"category {category_id} references an unknown domain")

    for capability_id, capability in capabilities.items():
        if capability["domain_id"] not in domains:
            raise ValueError(f"capability {capability_id} references an unknown domain")

    for technology_id, technology in technologies.items():
        domain_id = technology["domain_id"]
        category_id = technology["category_id"]
        if domain_id not in domains:
            raise ValueError(f"technology {technology_id} references an unknown domain")
        if category_id not in categories:
            raise ValueError(f"technology {technology_id} references an unknown category")
        if categories[category_id]["domain_id"] != domain_id:
            raise ValueError(f"technology {technology_id} category/domain mismatch")

    known_targets = set(technologies) | set(capabilities)
    for index, relationship in enumerate(catalog.relationships):
        if relationship["source"] not in technologies:
            raise ValueError(f"relationship {index} has an unknown source")
        if relationship["target"] not in known_targets:
            raise ValueError(f"relationship {index} has an unknown target")
        if relationship["assertion_class"] != "CURATED":
            raise ValueError(f"relationship {index} is not CURATED")

    for index, assessment in enumerate(catalog.assessments):
        if assessment["technology_id"] not in technologies:
            raise ValueError(f"assessment {index} has an unknown technology")
