from __future__ import annotations

import fnmatch
import hashlib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping
from uuid import UUID

from stackgraph_ai.models import PromptInvocation, canonical_json, sha256_key
from stackgraph_ai.service import AIService


ANALYZER_KEY = "repository-capability-inference"
ANALYZER_VERSION = "1.0.0"
CAPABILITY_KEY = re.compile(r"^[a-z][a-z0-9.-]{1,127}$")


@dataclass(frozen=True, slots=True)
class CapabilityDefinition:
    key: str
    name: str
    description: str
    parent_key: str | None = None
    aliases: tuple[str, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class CapabilityMapping:
    ecosystem: str
    package_name: str
    capability_key: str
    confidence: float
    rationale: str
    symbol_pattern: str | None = None
    evidence: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class CapabilityTaxonomy:
    key: str
    version: str
    status: str
    name: str
    description: str
    capabilities: tuple[CapabilityDefinition, ...]
    mappings: tuple[CapabilityMapping, ...]
    content_hash: str
    metadata: Mapping[str, Any] = field(default_factory=dict)

    @property
    def capability_by_key(self) -> dict[str, CapabilityDefinition]:
        return {item.key: item for item in self.capabilities}

    def prompt_payload(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "version": self.version,
            "content_hash": self.content_hash,
            "capabilities": [
                {"key": item.key, "name": item.name, "description": item.description}
                for item in self.capabilities
            ],
        }


@dataclass(frozen=True, slots=True)
class PackageUsage:
    repository_id: UUID
    repository_key: str
    subject_entity_id: UUID
    subject_key: str
    source_revision: str
    ecosystem: str
    package_name: str
    referenced_symbols: tuple[str, ...]
    supporting_fact_ids: tuple[UUID, ...]
    counter_evidence_fact_ids: tuple[UUID, ...] = ()
    referenced: bool = True
    runtime_observed: str = "UNKNOWN"

    @property
    def active(self) -> bool:
        return self.referenced or self.runtime_observed == "OBSERVED"


@dataclass(frozen=True, slots=True)
class InferenceProposal:
    usage: PackageUsage
    capability_key: str
    assertion_class: str
    confidence: float
    confidence_band: str
    rationale: str
    input_fingerprint: str
    analysis_fingerprint: str
    supporting_fact_ids: tuple[UUID, ...]
    counter_evidence_fact_ids: tuple[UUID, ...]
    policy_version: str
    model_invocation_id: UUID | None = None
    model_provider: str | None = None
    model_name: str | None = None


@dataclass(frozen=True, slots=True)
class PersistedInference:
    id: UUID
    proposal: InferenceProposal


@dataclass(frozen=True, slots=True)
class DuplicateCapabilityProposal:
    repository_id: UUID
    source_revision: str
    capability_key: str
    dependency_entity_ids: tuple[UUID, ...]
    capability_inference_ids: tuple[UUID, ...]
    supporting_fact_ids: tuple[UUID, ...]
    confidence: float
    analysis_fingerprint: str
    summary: str
    limitations: tuple[str, ...]


class LocalCapabilityCatalog:
    def __init__(self, root: Path | str) -> None:
        self.root = Path(root)

    def definitions(self) -> tuple[CapabilityTaxonomy, ...]:
        if not self.root.is_dir():
            raise ValueError(f"capability catalog does not exist: {self.root}")
        definitions = tuple(
            _parse_taxonomy(json.loads(path.read_text(encoding="utf-8")), path)
            for path in sorted(self.root.rglob("*.json"))
        )
        identities = [(item.key, item.version) for item in definitions]
        if len(identities) != len(set(identities)):
            raise ValueError("capability catalog contains duplicate taxonomy versions")
        active_keys = [item.key for item in definitions if item.status == "ACTIVE"]
        if len(active_keys) != len(set(active_keys)):
            raise ValueError("capability catalog contains multiple ACTIVE versions")
        return definitions


def curated_inferences(
    taxonomy: CapabilityTaxonomy,
    usage: PackageUsage,
) -> tuple[InferenceProposal, ...]:
    if not usage.active:
        return ()
    matches: dict[str, CapabilityMapping] = {}
    package_name = _normalize_package(usage.ecosystem, usage.package_name)
    for mapping in taxonomy.mappings:
        if mapping.ecosystem != usage.ecosystem or mapping.package_name != package_name:
            continue
        if mapping.symbol_pattern is not None and not any(
            fnmatch.fnmatchcase(symbol, mapping.symbol_pattern)
            for symbol in usage.referenced_symbols
        ):
            continue
        prior = matches.get(mapping.capability_key)
        if prior is None or mapping.confidence > prior.confidence:
            matches[mapping.capability_key] = mapping

    proposals = []
    for capability_key, mapping in sorted(matches.items()):
        input_fingerprint = sha256_key({
            "taxonomy": taxonomy.content_hash,
            "subject": usage.subject_key,
            "revision": usage.source_revision,
            "symbols": list(usage.referenced_symbols),
            "supporting_facts": sorted(str(item) for item in usage.supporting_fact_ids),
        })
        proposals.append(InferenceProposal(
            usage=usage,
            capability_key=capability_key,
            assertion_class="CURATED",
            confidence=mapping.confidence,
            confidence_band=confidence_band(mapping.confidence),
            rationale=mapping.rationale,
            input_fingerprint=input_fingerprint,
            analysis_fingerprint=_analysis_fingerprint(
                taxonomy, usage, capability_key, input_fingerprint,
            ),
            supporting_fact_ids=usage.supporting_fact_ids,
            counter_evidence_fact_ids=usage.counter_evidence_fact_ids,
            policy_version=str(taxonomy.metadata.get("policy_version") or "capability-taxonomy/v1"),
        ))
    return tuple(proposals)


async def infer_with_ai(
    ai: AIService,
    taxonomy: CapabilityTaxonomy,
    usage: PackageUsage,
    *,
    tenant_id: UUID,
    route: str = "default",
) -> InferenceProposal:
    if not usage.active:
        raise ValueError("AI inference requires referenced or runtime-observed usage")
    evidence_refs = tuple(str(item) for item in usage.supporting_fact_ids)
    invocation = await ai.invoke(
        "capability.inference",
        {
            "subject": {
                "key": usage.subject_key,
                "ecosystem": usage.ecosystem,
                "package": usage.package_name,
                "source_revision": usage.source_revision,
            },
            "taxonomy": taxonomy.prompt_payload(),
            "evidence_bundle": {
                "evidence_refs": list(evidence_refs),
                "counter_evidence_refs": [str(item) for item in usage.counter_evidence_fact_ids],
                "referenced_symbols": list(usage.referenced_symbols),
                "runtime_observed": usage.runtime_observed,
            },
        },
        route=route,
        tenant_id=tenant_id,
        metadata={"taxonomy_key": taxonomy.key, "taxonomy_version": taxonomy.version},
    )
    return _proposal_from_ai(invocation, taxonomy, usage)


def duplicate_capability_candidates(
    inferences: tuple[PersistedInference, ...],
) -> tuple[DuplicateCapabilityProposal, ...]:
    grouped: dict[tuple[UUID, str, str], list[PersistedInference]] = {}
    for inference in inferences:
        proposal = inference.proposal
        key = (
            proposal.usage.repository_id,
            proposal.usage.source_revision,
            proposal.capability_key,
        )
        grouped.setdefault(key, []).append(inference)
    candidates = []
    for (repository_id, source_revision, capability_key), values in sorted(
        grouped.items(), key=lambda item: tuple(str(value) for value in item[0]),
    ):
        subjects = sorted({item.proposal.usage.subject_entity_id for item in values}, key=str)
        if len(subjects) < 2:
            continue
        inference_ids = tuple(sorted({item.id for item in values}, key=str))
        fact_ids = tuple(sorted({
            fact_id for item in values for fact_id in item.proposal.supporting_fact_ids
        }, key=str))
        confidence = min(item.proposal.confidence for item in values)
        fingerprint = sha256_key({
            "repository_id": str(repository_id),
            "source_revision": source_revision,
            "capability": capability_key,
            "dependency_entity_ids": [str(item) for item in subjects],
            "inference_ids": [str(item) for item in inference_ids],
            "analyzer": f"{ANALYZER_KEY}/{ANALYZER_VERSION}",
        })
        candidates.append(DuplicateCapabilityProposal(
            repository_id=repository_id,
            source_revision=source_revision,
            capability_key=capability_key,
            dependency_entity_ids=tuple(subjects),
            capability_inference_ids=inference_ids,
            supporting_fact_ids=fact_ids,
            confidence=confidence,
            analysis_fingerprint=fingerprint,
            summary=f"{len(subjects)} dependencies provide the {capability_key} capability.",
            limitations=(
                "shared capability does not prove behavioral equivalence",
                "validate runtime, framework, and configuration constraints before consolidation",
            ),
        ))
    return tuple(candidates)


def confidence_band(confidence: float) -> str:
    if not 0 <= confidence <= 1:
        raise ValueError("confidence must be between zero and one")
    return "HIGH" if confidence >= 0.85 else "MEDIUM" if confidence >= 0.6 else "LOW"


def _parse_taxonomy(payload: Any, path: Path) -> CapabilityTaxonomy:
    if not isinstance(payload, Mapping) or not isinstance(payload.get("taxonomy"), Mapping):
        raise ValueError(f"invalid capability catalog: {path}")
    record = payload["taxonomy"]
    capabilities = tuple(
        CapabilityDefinition(
            key=str(item["key"]),
            name=str(item["name"]),
            description=str(item["description"]),
            parent_key=str(item["parent_key"]) if item.get("parent_key") else None,
            aliases=tuple(str(value) for value in item.get("aliases") or ()),
            metadata=item.get("metadata") or {},
        )
        for item in payload.get("capabilities") or ()
        if isinstance(item, Mapping)
    )
    keys = [item.key for item in capabilities]
    if not capabilities or len(keys) != len(set(keys)) or any(not CAPABILITY_KEY.fullmatch(key) for key in keys):
        raise ValueError(f"invalid or duplicate capabilities in {path}")
    mappings = tuple(
        CapabilityMapping(
            ecosystem=str(item["ecosystem"]).lower(),
            package_name=_normalize_package(str(item["ecosystem"]), str(item["package"])),
            capability_key=str(item["capability"]),
            confidence=float(item["confidence"]),
            rationale=str(item["rationale"]),
            symbol_pattern=str(item["symbol"]) if item.get("symbol") else None,
            evidence=item.get("evidence") or {},
        )
        for item in payload.get("mappings") or ()
        if isinstance(item, Mapping)
    )
    if any(item.ecosystem not in {"npm", "pypi"} for item in mappings):
        raise ValueError(f"unsupported mapping ecosystem in {path}")
    if any(item.capability_key not in set(keys) for item in mappings):
        raise ValueError(f"mapping references an unknown capability in {path}")
    if any(not 0 <= item.confidence <= 1 for item in mappings):
        raise ValueError(f"mapping confidence is outside zero to one in {path}")
    canonical = {"taxonomy": dict(record), "capabilities": payload.get("capabilities"), "mappings": payload.get("mappings")}
    return CapabilityTaxonomy(
        key=str(record["key"]),
        version=str(record["version"]),
        status=str(record["status"]).upper(),
        name=str(record["name"]),
        description=str(record["description"]),
        capabilities=capabilities,
        mappings=mappings,
        content_hash=f"sha256:{hashlib.sha256(canonical_json(canonical).encode()).hexdigest()}",
        metadata=record.get("metadata") or {},
    )


def _proposal_from_ai(
    invocation: PromptInvocation,
    taxonomy: CapabilityTaxonomy,
    usage: PackageUsage,
) -> InferenceProposal:
    output = invocation.response.structured_output
    if not isinstance(output, Mapping):
        raise ValueError("AI capability response is not an object")
    capability_key = str(output.get("capabilityKey") or "")
    if capability_key not in taxonomy.capability_by_key:
        raise ValueError("AI capability response references an unknown taxonomy capability")
    evidence = tuple(UUID(str(item)) for item in output.get("supportingEvidenceRefs") or ())
    counters = tuple(UUID(str(item)) for item in output.get("counterEvidenceRefs") or ())
    if not evidence or not set(evidence) <= set(usage.supporting_fact_ids):
        raise ValueError("AI capability response contains unsupported evidence references")
    if not set(counters) <= set(usage.counter_evidence_fact_ids):
        raise ValueError("AI capability response contains unsupported counter-evidence references")
    confidence = float(output["confidence"])
    fingerprint = _analysis_fingerprint(
        taxonomy, usage, capability_key, invocation.input_fingerprint,
    )
    return InferenceProposal(
        usage=usage,
        capability_key=capability_key,
        assertion_class="INFERRED",
        confidence=confidence,
        confidence_band=confidence_band(confidence),
        rationale=str(output["rationale"]),
        input_fingerprint=invocation.input_fingerprint,
        analysis_fingerprint=fingerprint,
        supporting_fact_ids=evidence,
        counter_evidence_fact_ids=counters,
        policy_version=str(invocation.prompt.metadata.get("policy_version") or "capability-inference/v1.1"),
        model_invocation_id=invocation.invocation_id,
        model_provider=invocation.response.provider,
        model_name=invocation.response.model,
    )


def _analysis_fingerprint(
    taxonomy: CapabilityTaxonomy,
    usage: PackageUsage,
    capability_key: str,
    input_fingerprint: str,
) -> str:
    return sha256_key({
        "taxonomy": taxonomy.content_hash,
        "analyzer": f"{ANALYZER_KEY}/{ANALYZER_VERSION}",
        "repository": str(usage.repository_id),
        "revision": usage.source_revision,
        "subject": str(usage.subject_entity_id),
        "capability": capability_key,
        "input": input_fingerprint,
    })


def _normalize_package(ecosystem: str, value: str) -> str:
    name = value.strip().lower()
    return re.sub(r"[-_.]+", "-", name) if ecosystem.lower() == "pypi" else name
