from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

from app.models import (
    ArchitectureReferenceModel,
    ArchitectureReferenceModelList,
    ArchitectureTaxonomyResponse,
    CanvasTemplateList,
    CanvasTemplateModel,
)


CATALOG_FILE = Path(__file__).with_name("architecture") / "stackgraph-reference-v1.json"


def canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def sha256_fingerprint(value: object) -> str:
    return "sha256:" + hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class ArchitectureCatalog:
    taxonomy: ArchitectureTaxonomyResponse
    reference_model: ArchitectureReferenceModel
    template: CanvasTemplateModel
    capability_aliases: dict[str, str]

    @property
    def cells_by_key(self) -> dict[str, Any]:
        return {cell.key: cell for cell in self.reference_model.cells}

    @property
    def concerns_by_key(self) -> dict[str, Any]:
        return {concern.key: concern for concern in self.taxonomy.concerns}

    def canonical_capability_key(self, key: str) -> str | None:
        normalized = key.strip().lower()
        return self.capability_aliases.get(normalized)

    def reference_models(self) -> ArchitectureReferenceModelList:
        return ArchitectureReferenceModelList(models=[self.reference_model])

    def templates(self) -> CanvasTemplateList:
        return CanvasTemplateList(templates=[self.template])


def _unique(values: list[str], label: str) -> None:
    if len(values) != len(set(values)):
        raise ValueError(f"architecture catalog contains duplicate {label}")


def _load_document(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise RuntimeError(f"architecture catalog is missing: {path}") from error
    if not isinstance(value, dict):
        raise ValueError("architecture catalog root must be an object")
    return value


@lru_cache(maxsize=1)
def load_architecture_catalog() -> ArchitectureCatalog:
    document = _load_document(CATALOG_FILE)
    taxonomy_payload = dict(document["taxonomy"])
    taxonomy_payload["content_hash"] = sha256_fingerprint(taxonomy_payload)
    taxonomy = ArchitectureTaxonomyResponse.model_validate(taxonomy_payload)

    domain_keys = [item.key for item in taxonomy.domains]
    concern_keys = [item.key for item in taxonomy.concerns]
    capability_keys = [item.key for item in taxonomy.capabilities]
    aspect_keys = [item.key for item in taxonomy.aspects]
    _unique(domain_keys, "domain keys")
    _unique(concern_keys, "concern keys")
    _unique(capability_keys, "capability keys")
    _unique(aspect_keys, "aspect keys")
    known_domains = set(domain_keys)
    known_concerns = set(concern_keys)
    known_aspects = set(aspect_keys)
    for concern in taxonomy.concerns:
        if concern.domain_key not in known_domains:
            raise ValueError(f"concern {concern.key} references an unknown domain")
    for capability in taxonomy.capabilities:
        if capability.concern_key not in known_concerns:
            raise ValueError(f"capability {capability.key} references an unknown concern")

    aliases: dict[str, str] = {}
    for capability in taxonomy.capabilities:
        for value in (capability.key, *capability.aliases):
            alias = value.strip().lower()
            existing = aliases.get(alias)
            if existing is not None and existing != capability.key:
                raise ValueError(
                    f"capability alias {alias!r} maps to both {existing!r} and {capability.key!r}"
                )
            aliases[alias] = capability.key

    reference_payload = dict(document["reference_model"])
    reference_payload.update({
        "taxonomy_key": taxonomy.key,
        "taxonomy_version": taxonomy.version,
        "taxonomy_content_hash": taxonomy.content_hash,
    })
    reference_payload["content_hash"] = sha256_fingerprint(reference_payload)
    reference_model = ArchitectureReferenceModel.model_validate(reference_payload)

    cell_keys = [cell.key for cell in reference_model.cells]
    _unique(cell_keys, "cell keys")
    bound_capabilities: dict[str, str] = {}
    for cell in reference_model.cells:
        if cell.concern_key not in known_concerns:
            raise ValueError(f"cell {cell.key} references an unknown concern")
        unknown_aspects = set(cell.aspect_keys) - known_aspects
        if unknown_aspects:
            raise ValueError(f"cell {cell.key} references unknown aspects: {sorted(unknown_aspects)}")
        for binding in cell.bindings:
            if binding.kind != "CAPABILITY":
                continue
            for capability_key in binding.keys:
                if capability_key not in set(capability_keys):
                    raise ValueError(
                        f"cell {cell.key} binds unknown canonical capability {capability_key}"
                    )
                prior = bound_capabilities.get(capability_key)
                if prior is not None and prior != cell.key:
                    raise ValueError(
                        f"capability {capability_key} is bound to both {prior} and {cell.key}"
                    )
                bound_capabilities[capability_key] = cell.key

    template_payload = dict(document["template"])
    template_payload.update({
        "reference_model_key": reference_model.key,
        "reference_model_version": reference_model.version,
    })
    template_payload["content_hash"] = sha256_fingerprint(template_payload)
    template = CanvasTemplateModel.model_validate(template_payload)
    layout_keys = [layout.cell_key for band in template.bands for layout in band.cells]
    _unique(layout_keys, "template cell keys")
    if set(layout_keys) != set(cell_keys):
        missing = sorted(set(cell_keys) - set(layout_keys))
        extra = sorted(set(layout_keys) - set(cell_keys))
        raise ValueError(f"template/reference mismatch; missing={missing}, extra={extra}")

    return ArchitectureCatalog(
        taxonomy=taxonomy,
        reference_model=reference_model,
        template=template,
        capability_aliases=aliases,
    )
