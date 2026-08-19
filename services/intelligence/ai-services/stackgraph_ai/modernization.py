from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping
from uuid import UUID

from stackgraph_ai.models import canonical_json, sha256_key


ANALYZER_KEY = "repository-modernization-intelligence"
ANALYZER_VERSION = "1.0.0"


@dataclass(frozen=True, slots=True)
class AlternativeDefinition:
    capability_key: str
    kind: str
    key: str
    name: str
    rationale: str
    validation_gaps: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class AlternativeCatalog:
    key: str
    version: str
    policy_version: str
    alternatives: tuple[AlternativeDefinition, ...]
    content_hash: str

    @classmethod
    def load(cls, path: Path | str) -> "AlternativeCatalog":
        source = Path(path)
        payload = json.loads(source.read_text(encoding="utf-8"))
        if not isinstance(payload, Mapping) or not isinstance(payload.get("catalog"), Mapping):
            raise ValueError(f"invalid modernization alternative catalog: {source}")
        record = payload["catalog"]
        values = tuple(
            AlternativeDefinition(
                capability_key=str(item["capability"]),
                kind=str(item["kind"]).upper(),
                key=str(item["key"]),
                name=str(item["name"]),
                rationale=str(item["rationale"]),
                validation_gaps=tuple(str(value) for value in item.get("validation_gaps") or ()),
            )
            for item in payload.get("alternatives") or ()
            if isinstance(item, Mapping)
        )
        if not values or any(item.kind not in {"NATIVE", "INTERNAL", "UPGRADE", "PACKAGE"} for item in values):
            raise ValueError(f"invalid modernization alternatives in {source}")
        canonical = {"catalog": dict(record), "alternatives": payload.get("alternatives")}
        return cls(
            key=str(record["key"]),
            version=str(record["version"]),
            policy_version=str(record["policy_version"]),
            alternatives=values,
            content_hash=f"sha256:{hashlib.sha256(canonical_json(canonical).encode()).hexdigest()}",
        )


@dataclass(frozen=True, slots=True)
class DependencyUsage:
    entity_id: UUID
    canonical_key: str
    name: str
    inference_id: UUID
    supporting_fact_ids: tuple[UUID, ...]
    confidence: float
    reference_count: int
    referenced_symbols: tuple[str, ...]
    source_locations: tuple[Mapping[str, Any], ...]
    runtime_observed: str = "UNKNOWN"
    limitations: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class DuplicateInput:
    id: UUID
    repository_id: UUID
    source_revision: str
    capability_definition_id: UUID
    capability_key: str
    capability_name: str
    confidence: float
    dependencies: tuple[DependencyUsage, ...]


@dataclass(frozen=True, slots=True)
class ModernizationOption:
    kind: str
    canonical_key: str
    name: str
    target_entity_id: UUID | None
    compatibility: str
    score: float
    score_components: Mapping[str, float]
    rationale: str
    tradeoffs: tuple[str, ...]
    disqualifiers: tuple[str, ...]
    validation_gaps: tuple[str, ...]
    supporting_fact_ids: tuple[UUID, ...]


@dataclass(frozen=True, slots=True)
class ModernizationRecommendation:
    action: str
    objective: str
    title: str
    rationale: str
    confidence: float
    estimated_effort: str
    affected_call_sites: int
    affected_files: int
    validation_gaps: tuple[str, ...]
    migration_plan: tuple[str, ...]
    rollback_plan: tuple[str, ...]
    supporting_fact_ids: tuple[UUID, ...]
    counter_signals: tuple[str, ...]
    selected_option_key: str
    input_fingerprint: str
    analysis_fingerprint: str
    policy_version: str


@dataclass(frozen=True, slots=True)
class ModernizationAnalysis:
    duplicate_candidate_id: UUID
    repository_id: UUID
    source_revision: str
    capability_definition_id: UUID
    candidate_kind: str
    summary: str
    confidence: float
    subject_entity_ids: tuple[UUID, ...]
    supporting_fact_ids: tuple[UUID, ...]
    source_locations: tuple[Mapping[str, Any], ...]
    validation_gaps: tuple[str, ...]
    input_fingerprint: str
    analysis_fingerprint: str
    options: tuple[ModernizationOption, ...]
    recommendation: ModernizationRecommendation


def analyze_duplicate(
    duplicate: DuplicateInput,
    catalog: AlternativeCatalog,
) -> ModernizationAnalysis:
    if len({item.entity_id for item in duplicate.dependencies}) < 2:
        raise ValueError("modernization analysis requires two distinct dependencies")
    dependencies = tuple(sorted(duplicate.dependencies, key=lambda item: item.canonical_key))
    facts = tuple(sorted({fact for item in dependencies for fact in item.supporting_fact_ids}, key=str))
    locations = _unique_locations(dependencies)
    gaps = {
        "Static similarity and shared capability do not prove behavioral equivalence.",
        "Test coverage for affected behavior has not been measured.",
    }
    for dependency in dependencies:
        gaps.update(dependency.limitations)
        if dependency.runtime_observed == "UNKNOWN":
            gaps.add(f"Runtime use of {dependency.name} is unknown.")
    input_fingerprint = sha256_key({
        "duplicate_candidate_id": str(duplicate.id),
        "repository_id": str(duplicate.repository_id),
        "source_revision": duplicate.source_revision,
        "capability": duplicate.capability_key,
        "dependencies": [
            {
                "id": str(item.entity_id),
                "key": item.canonical_key,
                "inference_id": str(item.inference_id),
                "facts": [str(value) for value in item.supporting_fact_ids],
                "references": item.reference_count,
                "symbols": list(item.referenced_symbols),
            }
            for item in dependencies
        ],
        "alternative_catalog": catalog.content_hash,
    })
    analysis_fingerprint = sha256_key({
        "input": input_fingerprint,
        "analyzer": f"{ANALYZER_KEY}/{ANALYZER_VERSION}",
    })
    options = _options(duplicate, dependencies, facts, catalog)
    selected = options[0]
    replaced_calls = sum(
        item.reference_count
        for item in dependencies
        if _package_key(item.canonical_key) != selected.canonical_key
    )
    affected_files = len({str(item.get("path")) for item in locations if item.get("path")})
    effort = _effort(replaced_calls, affected_files)
    counter_signals = tuple(sorted(gaps))
    recommendation_fingerprint = sha256_key({
        "analysis": analysis_fingerprint,
        "selected_option": selected.canonical_key,
        "policy": catalog.policy_version,
    })
    recommendation = ModernizationRecommendation(
        action="CONSOLIDATE",
        objective="DEPENDENCY_CONSOLIDATION",
        title=f"Consolidate {duplicate.capability_name} dependencies on {selected.name}",
        rationale=(
            f"{len(dependencies)} referenced dependencies provide {duplicate.capability_name}. "
            f"Retaining {selected.name} minimizes the observed replacement surface; validate the listed gaps before changing code."
        ),
        confidence=min(duplicate.confidence, selected.score),
        estimated_effort=effort,
        affected_call_sites=replaced_calls,
        affected_files=affected_files,
        validation_gaps=counter_signals,
        migration_plan=(
            f"Confirm {selected.name} covers the observed {duplicate.capability_name} behavior.",
            "Add or identify tests for every affected behavior and dynamic-use gap.",
            f"Replace the {replaced_calls} observed call sites belonging to the other dependencies.",
            "Remove superseded manifests and lockfile entries, then run unit, integration, and deployment checks.",
        ),
        rollback_plan=(
            "Keep the dependency change isolated in a reversible commit.",
            "Restore the prior manifest and lockfile entries if validation or production checks fail.",
        ),
        supporting_fact_ids=facts,
        counter_signals=counter_signals,
        selected_option_key=selected.canonical_key,
        input_fingerprint=input_fingerprint,
        analysis_fingerprint=recommendation_fingerprint,
        policy_version=catalog.policy_version,
    )
    return ModernizationAnalysis(
        duplicate_candidate_id=duplicate.id,
        repository_id=duplicate.repository_id,
        source_revision=duplicate.source_revision,
        capability_definition_id=duplicate.capability_definition_id,
        candidate_kind="DEPENDENCY_CONSOLIDATION",
        summary=(
            f"{len(dependencies)} active dependencies appear to provide "
            f"{duplicate.capability_name}; {len(locations)} evidence locations were found."
        ),
        confidence=duplicate.confidence,
        subject_entity_ids=tuple(item.entity_id for item in dependencies),
        supporting_fact_ids=facts,
        source_locations=locations,
        validation_gaps=counter_signals,
        input_fingerprint=input_fingerprint,
        analysis_fingerprint=analysis_fingerprint,
        options=options,
        recommendation=recommendation,
    )


def _options(
    duplicate: DuplicateInput,
    dependencies: tuple[DependencyUsage, ...],
    facts: tuple[UUID, ...],
    catalog: AlternativeCatalog,
) -> tuple[ModernizationOption, ...]:
    total_references = max(1, sum(item.reference_count for item in dependencies))
    values: list[ModernizationOption] = []
    for dependency in dependencies:
        migration_surface = dependency.reference_count / total_references
        evidence_completeness = 1.0 if dependency.supporting_fact_ids else 0.0
        score = round(
            0.55 * dependency.confidence + 0.30 * migration_surface + 0.15 * evidence_completeness,
            4,
        )
        values.append(ModernizationOption(
            kind="PACKAGE",
            canonical_key=_package_key(dependency.canonical_key),
            name=dependency.name,
            target_entity_id=dependency.entity_id,
            compatibility="OBSERVED",
            score=score,
            score_components={
                "capability_fit": round(dependency.confidence, 4),
                "migration_surface": round(migration_surface, 4),
                "evidence_completeness": evidence_completeness,
            },
            rationale="Already referenced in this repository for the required capability.",
            tradeoffs=("Retaining this package still requires migrating the other observed dependency usage.",),
            disqualifiers=(),
            validation_gaps=tuple(dependency.limitations),
            supporting_fact_ids=dependency.supporting_fact_ids,
        ))
    observed_keys = {_package_key(item.canonical_key) for item in dependencies}
    for alternative in catalog.alternatives:
        if alternative.capability_key != duplicate.capability_key or alternative.key in observed_keys:
            continue
        values.append(ModernizationOption(
            kind=alternative.kind,
            canonical_key=alternative.key,
            name=alternative.name,
            target_entity_id=None,
            compatibility="UNKNOWN",
            score=0.35,
            score_components={"capability_fit": 0.7, "compatibility": 0.0, "evidence_completeness": 0.0},
            rationale=alternative.rationale,
            tradeoffs=("This option is curated but is not observed in the repository.",),
            disqualifiers=(),
            validation_gaps=alternative.validation_gaps,
            supporting_fact_ids=facts,
        ))
    return tuple(sorted(values, key=lambda item: (-item.score, item.kind, item.canonical_key)))


def _unique_locations(dependencies: tuple[DependencyUsage, ...]) -> tuple[Mapping[str, Any], ...]:
    values: dict[str, Mapping[str, Any]] = {}
    for dependency in dependencies:
        for location in dependency.source_locations:
            key = canonical_json(dict(location))
            values[key] = dict(location)
    return tuple(values[key] for key in sorted(values))


def _effort(call_sites: int, files: int) -> str:
    if call_sites <= 5 and files <= 3:
        return "LOW"
    if call_sites <= 25 and files <= 12:
        return "MEDIUM"
    return "HIGH"


def _package_key(canonical_key: str) -> str:
    return canonical_key.rsplit("@", 1)[0] if "@" in canonical_key else canonical_key
