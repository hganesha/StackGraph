from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping
from uuid import UUID

from stackgraph_ai.models import canonical_json, sha256_key


ANALYZER_KEY = "repository-modernization-intelligence"
ANALYZER_VERSION = "2.0.0"


@dataclass(frozen=True, slots=True)
class AlternativeDefinition:
    capability_key: str
    kind: str
    key: str
    name: str
    rationale: str
    validation_gaps: tuple[str, ...] = ()
    provided_symbols: tuple[str, ...] = ()
    runtime_constraints: Mapping[str, str] = field(default_factory=dict)
    license: str | None = None
    security_status: str = "UNKNOWN"
    policy_tags: tuple[str, ...] = ()
    behavior_verified: bool = False


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
                provided_symbols=tuple(str(value) for value in item.get("provided_symbols") or ()),
                runtime_constraints={
                    str(key): str(value)
                    for key, value in (item.get("runtime_constraints") or {}).items()
                },
                license=str(item["license"]) if item.get("license") else None,
                security_status=str(item.get("security_status") or "UNKNOWN").upper(),
                policy_tags=tuple(str(value) for value in item.get("policy_tags") or ()),
                behavior_verified=bool(item.get("behavior_verified", False)),
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
class CodeUnitEvidence:
    id: UUID
    repository_id: UUID
    fact_id: UUID
    source_revision: str
    language: str
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
    vendored: bool = False
    limitations: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ModernizationPolicyInput:
    id: UUID | None = None
    key: str = "default"
    version: str = "unconfigured"
    runtime_versions: Mapping[str, str] = field(default_factory=dict)
    allowed_licenses: tuple[str, ...] = ()
    denied_option_keys: tuple[str, ...] = ()
    allowed_security_statuses: tuple[str, ...] = ("CLEAR", "UNKNOWN")
    required_policy_tags: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class InternalComponentInput:
    id: UUID
    entity_id: UUID
    capability_definition_id: UUID
    key: str
    name: str
    version: str
    status: str
    api_symbols: tuple[str, ...]
    runtime_constraints: Mapping[str, str]
    behavior_verified: bool
    license: str | None
    security_status: str
    policy_tags: tuple[str, ...]
    supporting_fact_ids: tuple[UUID, ...]


@dataclass(frozen=True, slots=True)
class OptionEligibility:
    policy_id: UUID | None
    capability_fit: str
    api_fit: str
    behavior_fit: str
    runtime_fit: str
    license_fit: str
    security_fit: str
    policy_fit: str
    eligible: bool
    evidence: Mapping[str, Any]
    disqualifiers: tuple[str, ...]
    unknowns: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ImpactEstimate:
    affected_call_sites: int
    affected_files: int
    covered_call_sites: int
    uncovered_call_sites: int
    affected_test_files: tuple[str, ...]
    dynamic_signals: tuple[str, ...]
    configuration_touchpoints: tuple[Mapping[str, str], ...]
    build_touchpoints: tuple[Mapping[str, str], ...]
    deployment_touchpoints: tuple[Mapping[str, str], ...]
    evidence_locations: tuple[Mapping[str, Any], ...]
    confidence: float
    effort_points: int
    effort_model_version: str = "phase3-effort/v2"
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
    eligibility: OptionEligibility


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
    duplicate_candidate_id: UUID | None
    repository_id: UUID
    source_revision: str
    capability_definition_id: UUID | None
    candidate_kind: str
    summary: str
    confidence: float
    subject_entity_ids: tuple[UUID, ...]
    supporting_fact_ids: tuple[UUID, ...]
    source_locations: tuple[Mapping[str, Any], ...]
    validation_gaps: tuple[str, ...]
    input_fingerprint: str
    analysis_fingerprint: str
    source_code_unit_ids: tuple[UUID, ...]
    options: tuple[ModernizationOption, ...]
    recommendation: ModernizationRecommendation
    impact: ImpactEstimate


def _policy_payload(policy: ModernizationPolicyInput) -> Mapping[str, Any]:
    return {
        "id": str(policy.id) if policy.id else None,
        "key": policy.key,
        "version": policy.version,
        "runtime_versions": dict(sorted(policy.runtime_versions.items())),
        "allowed_licenses": sorted(policy.allowed_licenses),
        "denied_option_keys": sorted(policy.denied_option_keys),
        "allowed_security_statuses": sorted(policy.allowed_security_statuses),
        "required_policy_tags": sorted(policy.required_policy_tags),
    }


def _internal_components_payload(
    components: tuple[InternalComponentInput, ...],
) -> list[Mapping[str, Any]]:
    return [{
        "id": str(component.id),
        "entity_id": str(component.entity_id),
        "capability_definition_id": str(component.capability_definition_id),
        "key": component.key,
        "version": component.version,
        "status": component.status,
        "api_symbols": sorted(component.api_symbols),
        "runtime_constraints": dict(sorted(component.runtime_constraints.items())),
        "behavior_verified": component.behavior_verified,
        "license": component.license,
        "security_status": component.security_status,
        "policy_tags": sorted(component.policy_tags),
        "supporting_fact_ids": sorted(str(value) for value in component.supporting_fact_ids),
    } for component in sorted(
        components, key=lambda item: (item.key, item.version, str(item.id)),
    )]


def _alternatives_payload(
    alternatives: tuple[AlternativeDefinition, ...],
) -> list[Mapping[str, Any]]:
    return [{
        "capability_key": alternative.capability_key,
        "kind": alternative.kind,
        "key": alternative.key,
        "name": alternative.name,
        "rationale": alternative.rationale,
        "validation_gaps": sorted(alternative.validation_gaps),
        "provided_symbols": sorted(alternative.provided_symbols),
        "runtime_constraints": dict(sorted(alternative.runtime_constraints.items())),
        "license": alternative.license,
        "security_status": alternative.security_status,
        "policy_tags": sorted(alternative.policy_tags),
        "behavior_verified": alternative.behavior_verified,
    } for alternative in sorted(
        alternatives, key=lambda item: (item.capability_key, item.kind, item.key),
    )]


def analyze_duplicate(
    duplicate: DuplicateInput,
    catalog: AlternativeCatalog,
    *,
    policy: ModernizationPolicyInput | None = None,
    internal_components: tuple[InternalComponentInput, ...] = (),
    code_units: tuple[CodeUnitEvidence, ...] = (),
    additional_alternatives: tuple[AlternativeDefinition, ...] = (),
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
        "additional_alternatives": _alternatives_payload(additional_alternatives),
        "policy": _policy_payload(policy or ModernizationPolicyInput()),
        "internal_components": _internal_components_payload(internal_components),
    })
    analysis_fingerprint = sha256_key({
        "input": input_fingerprint,
        "analyzer": f"{ANALYZER_KEY}/{ANALYZER_VERSION}",
    })
    active_policy = policy or ModernizationPolicyInput()
    options = _options(
        duplicate, dependencies, facts, catalog,
        policy=active_policy,
        internal_components=internal_components,
        additional_alternatives=additional_alternatives,
    )
    selected = options[0]
    replaced_calls = sum(
        item.reference_count
        for item in dependencies
        if _package_key(item.canonical_key) != selected.canonical_key
    )
    impact = _impact_estimate(replaced_calls, locations, code_units)
    effort = _effort(impact.effort_points)
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
        affected_files=impact.affected_files,
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
        source_code_unit_ids=tuple(sorted({unit.id for unit in code_units}, key=str)),
        options=options,
        recommendation=recommendation,
        impact=impact,
    )


def analyze_structural_duplication(
    *,
    repository_id: UUID,
    source_revision: str,
    units: tuple[CodeUnitEvidence, ...],
    policy: ModernizationPolicyInput | None = None,
    capability_definition_id: UUID | None = None,
    capability_name: str | None = None,
) -> ModernizationAnalysis:
    if len(units) < 2 or len({unit.structural_fingerprint for unit in units}) != 1:
        raise ValueError("structural duplication requires two units with one fingerprint")
    if repository_id not in {unit.repository_id for unit in units}:
        raise ValueError("structural duplication must include the analyzed repository")
    active_policy = policy or ModernizationPolicyInput()
    ordered = tuple(sorted(units, key=lambda item: (str(item.repository_id), item.path, item.line_start)))
    facts = tuple(sorted({unit.fact_id for unit in ordered}, key=str))
    locations = tuple({
        "repository_id": str(unit.repository_id),
        "path": unit.path,
        "line_start": unit.line_start,
        "line_end": unit.line_end,
        "symbol": unit.qualified_name,
    } for unit in ordered)
    gaps = {
        "Matching structure does not prove matching behavior or intent.",
        *[value for unit in ordered for value in unit.limitations],
    }
    if any(unit.dynamic_signals for unit in ordered):
        gaps.add("Dynamic behavior signals require runtime comparison.")
    input_fingerprint = sha256_key({
        "repository_id": str(repository_id),
        "source_revision": source_revision,
        "structural_fingerprint": ordered[0].structural_fingerprint,
        "units": [str(unit.id) for unit in ordered],
        "policy": _policy_payload(active_policy),
    })
    analysis_fingerprint = sha256_key({
        "input": input_fingerprint,
        "analyzer": f"{ANALYZER_KEY}/{ANALYZER_VERSION}",
        "kind": "structural-duplication",
    })
    options: list[ModernizationOption] = []
    for unit in ordered:
        key = f"internal-code:{unit.repository_id}:{unit.path}:{unit.qualified_name}"
        eligibility = _observed_eligibility(active_policy, key, (unit.fact_id,))
        score = round(
            0.65 + (0.15 if unit.covering_tests else 0.0)
            - (0.1 if unit.dynamic_signals else 0.0),
            4,
        )
        options.append(ModernizationOption(
            kind="INTERNAL", canonical_key=key, name=unit.qualified_name,
            target_entity_id=unit.repository_id,
            compatibility="INCOMPATIBLE" if eligibility.disqualifiers else "OBSERVED",
            score=0.0 if eligibility.disqualifiers else score,
            score_components={
                "structural_match": 1.0,
                "test_evidence": 1.0 if unit.covering_tests else 0.0,
                "dynamic_risk": 1.0 if unit.dynamic_signals else 0.0,
            },
            rationale="This implementation is directly observed with the same structural fingerprint.",
            tradeoffs=("A shared implementation may introduce repository or release coupling.",),
            disqualifiers=eligibility.disqualifiers,
            validation_gaps=tuple(sorted(gaps)), supporting_fact_ids=(unit.fact_id,),
            eligibility=eligibility,
        ))
    ranked = tuple(sorted(options, key=lambda item: (-item.score, item.canonical_key)))
    selected = ranked[0]
    current_units = tuple(unit for unit in ordered if unit.repository_id == repository_id)
    impact = _impact_estimate(len(current_units), tuple(
        item for item in locations if item["repository_id"] == str(repository_id)
    ), current_units)
    recommendation_fingerprint = sha256_key({
        "analysis": analysis_fingerprint,
        "selected_option": selected.canonical_key,
        "policy": f"{active_policy.key}/{active_policy.version}",
    })
    label = capability_name or "implementation"
    recommendation = ModernizationRecommendation(
        action="REFACTOR", objective="INTERNAL_CONSOLIDATION",
        title=f"Review duplicated {label} implementations",
        rationale=(
            f"{len(ordered)} code units share a structural fingerprint across "
            f"{len({unit.repository_id for unit in ordered})} repositories. "
            "Confirm behavioral equivalence before extracting or adopting a shared implementation."
        ),
        confidence=0.9 if all(unit.covering_tests for unit in ordered) else 0.78,
        estimated_effort=_effort(impact.effort_points),
        affected_call_sites=impact.affected_call_sites,
        affected_files=impact.affected_files,
        validation_gaps=tuple(sorted({*gaps, *impact.limitations})),
        migration_plan=(
            "Compare behavior, error handling, side effects, and tests for every matched code unit.",
            "Choose or create a supported shared implementation with explicit ownership.",
            "Migrate one repository at a time and run linked tests plus runtime checks.",
        ),
        rollback_plan=(
            "Keep each repository migration in a reversible change.",
            "Restore the prior local implementation if shared behavior or release coupling fails validation.",
        ),
        supporting_fact_ids=facts,
        counter_signals=tuple(sorted({*gaps, *impact.limitations})),
        selected_option_key=selected.canonical_key,
        input_fingerprint=input_fingerprint,
        analysis_fingerprint=recommendation_fingerprint,
        policy_version=f"{active_policy.key}/{active_policy.version}",
    )
    return ModernizationAnalysis(
        duplicate_candidate_id=None,
        repository_id=repository_id,
        source_revision=source_revision,
        capability_definition_id=capability_definition_id,
        candidate_kind=(
            "VENDORED_DUPLICATION" if any(unit.vendored for unit in ordered)
            else "INTERNAL_DUPLICATION"
        ),
        summary=(
            f"{len(ordered)} code units share structural fingerprint "
            f"{ordered[0].structural_fingerprint}."
        ),
        confidence=recommendation.confidence,
        subject_entity_ids=tuple(sorted({unit.repository_id for unit in ordered}, key=str)),
        supporting_fact_ids=facts,
        source_locations=locations,
        validation_gaps=tuple(sorted({*gaps, *impact.limitations})),
        input_fingerprint=input_fingerprint,
        analysis_fingerprint=analysis_fingerprint,
        source_code_unit_ids=tuple(unit.id for unit in ordered),
        options=ranked,
        recommendation=recommendation,
        impact=impact,
    )


def analyze_native_replacement(
    *,
    repository_id: UUID,
    source_revision: str,
    capability_definition_id: UUID,
    capability_key: str,
    capability_name: str,
    dependency: DependencyUsage,
    catalog: AlternativeCatalog,
    policy: ModernizationPolicyInput | None = None,
    internal_components: tuple[InternalComponentInput, ...] = (),
    code_units: tuple[CodeUnitEvidence, ...] = (),
    additional_alternatives: tuple[AlternativeDefinition, ...] = (),
) -> ModernizationAnalysis | None:
    active_policy = policy or ModernizationPolicyInput()
    synthetic = DuplicateInput(
        id=dependency.inference_id,
        repository_id=repository_id,
        source_revision=source_revision,
        capability_definition_id=capability_definition_id,
        capability_key=capability_key,
        capability_name=capability_name,
        confidence=dependency.confidence,
        dependencies=(dependency,),
    )
    options = _options(
        synthetic, (dependency,), dependency.supporting_fact_ids, catalog,
        policy=active_policy, internal_components=internal_components,
        additional_alternatives=additional_alternatives,
    )
    alternatives = tuple(option for option in options if option.kind in {"NATIVE", "UPGRADE", "INTERNAL"})
    if not alternatives:
        return None
    compatible = tuple(option for option in alternatives if option.compatibility == "COMPATIBLE")
    selected = compatible[0] if compatible else options[0]
    action = "REPLACE" if selected in compatible else "INVESTIGATE"
    locations = _unique_locations((dependency,))
    impact = _impact_estimate(dependency.reference_count, locations, code_units)
    facts = dependency.supporting_fact_ids
    input_fingerprint = sha256_key({
        "repository_id": str(repository_id), "source_revision": source_revision,
        "capability": capability_key, "dependency": dependency.canonical_key,
        "catalog": catalog.content_hash,
        "additional_alternatives": _alternatives_payload(additional_alternatives),
        "policy": _policy_payload(active_policy),
        "internal_components": _internal_components_payload(internal_components),
    })
    analysis_fingerprint = sha256_key({
        "input": input_fingerprint, "kind": "native-replacement",
        "analyzer": f"{ANALYZER_KEY}/{ANALYZER_VERSION}",
    })
    unknowns = tuple(sorted({
        value for option in alternatives for value in option.validation_gaps
    }))
    recommendation_fingerprint = sha256_key({
        "analysis": analysis_fingerprint, "selected_option": selected.canonical_key,
        "policy": f"{active_policy.key}/{active_policy.version}",
    })
    recommendation = ModernizationRecommendation(
        action=action, objective="NATIVE_OR_APPROVED_REPLACEMENT",
        title=(
            f"Replace {dependency.name} with {selected.name}"
            if action == "REPLACE" else f"Validate alternatives to {dependency.name}"
        ),
        rationale=(
            f"{selected.name} passed all configured eligibility gates."
            if action == "REPLACE"
            else "Alternatives exist, but one or more compatibility dimensions remain unknown."
        ),
        confidence=min(dependency.confidence, selected.score),
        estimated_effort=_effort(impact.effort_points),
        affected_call_sites=impact.affected_call_sites,
        affected_files=impact.affected_files,
        validation_gaps=tuple(sorted({*unknowns, *impact.limitations})),
        migration_plan=(
            "Resolve every unknown compatibility and policy dimension.",
            "Add tests for uncovered affected behavior and dynamic-use signals.",
            f"Migrate observed {capability_name} usage to {selected.name} only after validation passes.",
            "Remove the superseded dependency and run build, deployment, and runtime checks.",
        ),
        rollback_plan=(
            "Keep the replacement isolated in a reversible change.",
            f"Restore {dependency.name} and its prior manifest/lockfile state if validation fails.",
        ),
        supporting_fact_ids=facts,
        counter_signals=tuple(sorted({*unknowns, *impact.limitations})),
        selected_option_key=selected.canonical_key,
        input_fingerprint=input_fingerprint,
        analysis_fingerprint=recommendation_fingerprint,
        policy_version=f"{active_policy.key}/{active_policy.version}",
    )
    return ModernizationAnalysis(
        duplicate_candidate_id=None, repository_id=repository_id,
        source_revision=source_revision, capability_definition_id=capability_definition_id,
        candidate_kind="NATIVE_REPLACEMENT",
        summary=f"{len(alternatives)} native, upgrade, or approved internal options were evaluated.",
        confidence=recommendation.confidence,
        subject_entity_ids=(dependency.entity_id,), supporting_fact_ids=facts,
        source_locations=locations,
        validation_gaps=recommendation.validation_gaps,
        input_fingerprint=input_fingerprint, analysis_fingerprint=analysis_fingerprint,
        source_code_unit_ids=tuple(unit.id for unit in code_units),
        options=options, recommendation=recommendation, impact=impact,
    )


def _options(
    duplicate: DuplicateInput,
    dependencies: tuple[DependencyUsage, ...],
    facts: tuple[UUID, ...],
    catalog: AlternativeCatalog,
    *,
    policy: ModernizationPolicyInput,
    internal_components: tuple[InternalComponentInput, ...],
    additional_alternatives: tuple[AlternativeDefinition, ...],
) -> tuple[ModernizationOption, ...]:
    total_references = max(1, sum(item.reference_count for item in dependencies))
    required_symbols = tuple(sorted({symbol for item in dependencies for symbol in item.referenced_symbols}))
    values: list[ModernizationOption] = []
    for dependency in dependencies:
        migration_surface = dependency.reference_count / total_references
        evidence_completeness = 1.0 if dependency.supporting_fact_ids else 0.0
        score = round(
            0.55 * dependency.confidence + 0.30 * migration_surface + 0.15 * evidence_completeness,
            4,
        )
        eligibility = _observed_eligibility(
            policy, _package_key(dependency.canonical_key), dependency.supporting_fact_ids,
        )
        values.append(ModernizationOption(
            kind="PACKAGE",
            canonical_key=_package_key(dependency.canonical_key),
            name=dependency.name,
            target_entity_id=dependency.entity_id,
            compatibility="INCOMPATIBLE" if eligibility.disqualifiers else "OBSERVED",
            score=0.0 if eligibility.disqualifiers else score,
            score_components={
                "capability_fit": round(dependency.confidence, 4),
                "migration_surface": round(migration_surface, 4),
                "evidence_completeness": evidence_completeness,
            },
            rationale="Already referenced in this repository for the required capability.",
            tradeoffs=("Retaining this package still requires migrating the other observed dependency usage.",),
            disqualifiers=eligibility.disqualifiers,
            validation_gaps=tuple(dependency.limitations),
            supporting_fact_ids=dependency.supporting_fact_ids,
            eligibility=eligibility,
        ))
    observed_keys = {_package_key(item.canonical_key) for item in dependencies}
    for alternative in (*catalog.alternatives, *additional_alternatives):
        if alternative.capability_key != duplicate.capability_key or alternative.key in observed_keys:
            continue
        eligibility = evaluate_alternative(
            alternative,
            required_symbols=required_symbols,
            policy=policy,
            supporting_fact_ids=facts,
        )
        compatibility = (
            "INCOMPATIBLE" if eligibility.disqualifiers
            else "COMPATIBLE" if not eligibility.unknowns
            else "UNKNOWN"
        )
        base_score = 0.7 if compatibility == "COMPATIBLE" else 0.35
        values.append(ModernizationOption(
            kind=alternative.kind,
            canonical_key=alternative.key,
            name=alternative.name,
            target_entity_id=None,
            compatibility=compatibility,
            score=0.0 if compatibility == "INCOMPATIBLE" else base_score,
            score_components={
                "capability_fit": 0.7,
                "compatibility": 1.0 if compatibility == "COMPATIBLE" else 0.0,
                "evidence_completeness": 1.0 if not eligibility.unknowns else 0.0,
            },
            rationale=alternative.rationale,
            tradeoffs=("This option is curated but is not observed in the repository.",),
            disqualifiers=eligibility.disqualifiers,
            validation_gaps=tuple(sorted({*alternative.validation_gaps, *eligibility.unknowns})),
            supporting_fact_ids=facts,
            eligibility=eligibility,
        ))
    for component in internal_components:
        if component.capability_definition_id != duplicate.capability_definition_id:
            continue
        definition = AlternativeDefinition(
            capability_key=duplicate.capability_key,
            kind="INTERNAL",
            key=component.key,
            name=component.name,
            rationale="Tenant-approved internal component for this capability.",
            provided_symbols=component.api_symbols,
            runtime_constraints=component.runtime_constraints,
            license=component.license,
            security_status=component.security_status,
            policy_tags=component.policy_tags,
            behavior_verified=component.behavior_verified,
        )
        eligibility = evaluate_alternative(
            definition, required_symbols=required_symbols, policy=policy,
            supporting_fact_ids=component.supporting_fact_ids,
        )
        if component.status != "APPROVED":
            eligibility = _with_disqualifier(eligibility, f"Internal component status is {component.status}.")
        compatibility = (
            "INCOMPATIBLE" if eligibility.disqualifiers
            else "COMPATIBLE" if not eligibility.unknowns
            else "UNKNOWN"
        )
        values.append(ModernizationOption(
            kind="INTERNAL", canonical_key=component.key, name=component.name,
            target_entity_id=component.entity_id, compatibility=compatibility,
            score=0.75 if compatibility == "COMPATIBLE" else 0.35 if compatibility == "UNKNOWN" else 0.0,
            score_components={
                "capability_fit": 1.0,
                "compatibility": 1.0 if compatibility == "COMPATIBLE" else 0.0,
                "organizational_fit": 1.0 if component.status == "APPROVED" else 0.0,
            },
            rationale=definition.rationale,
            tradeoffs=("Adoption depends on the tenant component's support and release process.",),
            disqualifiers=eligibility.disqualifiers,
            validation_gaps=eligibility.unknowns,
            supporting_fact_ids=component.supporting_fact_ids,
            eligibility=eligibility,
        ))
    return tuple(sorted(
        values,
        key=lambda item: (
            item.compatibility == "INCOMPATIBLE",
            item.compatibility == "UNKNOWN",
            -item.score,
            item.kind,
            item.canonical_key,
        ),
    ))


def _unique_locations(dependencies: tuple[DependencyUsage, ...]) -> tuple[Mapping[str, Any], ...]:
    values: dict[str, Mapping[str, Any]] = {}
    for dependency in dependencies:
        for location in dependency.source_locations:
            key = canonical_json(dict(location))
            values[key] = dict(location)
    return tuple(values[key] for key in sorted(values))


def evaluate_alternative(
    alternative: AlternativeDefinition,
    *,
    required_symbols: tuple[str, ...],
    policy: ModernizationPolicyInput,
    supporting_fact_ids: tuple[UUID, ...],
) -> OptionEligibility:
    statuses: dict[str, str] = {"capability_fit": "PASS"}
    unknowns: list[str] = []
    disqualifiers: list[str] = []

    if required_symbols:
        if not alternative.provided_symbols:
            statuses["api_fit"] = "UNKNOWN"
            unknowns.append("Required API symbols have not been mapped for this option.")
        elif set(required_symbols).issubset(alternative.provided_symbols):
            statuses["api_fit"] = "PASS"
        else:
            statuses["api_fit"] = "FAIL"
            missing = sorted(set(required_symbols) - set(alternative.provided_symbols))
            disqualifiers.append(f"Required API symbols are missing: {', '.join(missing)}.")
    else:
        statuses["api_fit"] = "UNKNOWN"
        unknowns.append("No required API symbols were observed for compatibility comparison.")

    if alternative.behavior_verified:
        statuses["behavior_fit"] = "PASS"
    else:
        statuses["behavior_fit"] = "UNKNOWN"
        unknowns.append("Behavioral equivalence has not been verified.")

    runtime_status = "PASS"
    for runtime, constraint in alternative.runtime_constraints.items():
        observed = policy.runtime_versions.get(runtime)
        if observed is None:
            runtime_status = "UNKNOWN"
            unknowns.append(f"Deployed {runtime} version is unknown; option requires {constraint}.")
        elif not _version_satisfies(observed, constraint):
            runtime_status = "FAIL"
            disqualifiers.append(
                f"Deployed {runtime} {observed} does not satisfy {constraint}."
            )
    statuses["runtime_fit"] = runtime_status

    if alternative.license is None:
        statuses["license_fit"] = "UNKNOWN"
        unknowns.append("Option license is unknown.")
    elif not policy.allowed_licenses:
        statuses["license_fit"] = "UNKNOWN"
        unknowns.append("No tenant license allowlist is configured.")
    elif alternative.license in policy.allowed_licenses:
        statuses["license_fit"] = "PASS"
    else:
        statuses["license_fit"] = "FAIL"
        disqualifiers.append(f"License {alternative.license} is not tenant-approved.")

    security = alternative.security_status.upper()
    if security == "UNKNOWN":
        statuses["security_fit"] = "UNKNOWN"
        unknowns.append("Option security status is unknown.")
    elif security in policy.allowed_security_statuses:
        statuses["security_fit"] = "PASS"
    else:
        statuses["security_fit"] = "FAIL"
        disqualifiers.append(f"Security status {security} is not tenant-approved.")

    if alternative.key in policy.denied_option_keys:
        statuses["policy_fit"] = "FAIL"
        disqualifiers.append("The option is denied by tenant policy.")
    else:
        missing_tags = sorted(set(policy.required_policy_tags) - set(alternative.policy_tags))
        if missing_tags:
            statuses["policy_fit"] = "FAIL"
            disqualifiers.append(f"Required policy tags are missing: {', '.join(missing_tags)}.")
        else:
            statuses["policy_fit"] = "PASS"

    return OptionEligibility(
        policy_id=policy.id,
        capability_fit=statuses["capability_fit"],
        api_fit=statuses["api_fit"],
        behavior_fit=statuses["behavior_fit"],
        runtime_fit=statuses["runtime_fit"],
        license_fit=statuses["license_fit"],
        security_fit=statuses["security_fit"],
        policy_fit=statuses["policy_fit"],
        eligible=not disqualifiers,
        evidence={
            "policy": f"{policy.key}/{policy.version}",
            "required_symbols": list(required_symbols),
            "provided_symbols": list(alternative.provided_symbols),
            "supporting_fact_ids": [str(value) for value in supporting_fact_ids],
            "runtime_constraints": dict(alternative.runtime_constraints),
            "observed_runtime_versions": dict(policy.runtime_versions),
        },
        disqualifiers=tuple(sorted(set(disqualifiers))),
        unknowns=tuple(sorted(set(unknowns))),
    )


def _observed_eligibility(
    policy: ModernizationPolicyInput,
    canonical_key: str,
    supporting_fact_ids: tuple[UUID, ...],
) -> OptionEligibility:
    disqualifiers = (
        ("The observed option is denied by tenant policy.",)
        if canonical_key in policy.denied_option_keys else ()
    )
    return OptionEligibility(
        policy_id=policy.id,
        capability_fit="PASS", api_fit="PASS", behavior_fit="PASS", runtime_fit="PASS",
        license_fit="UNKNOWN", security_fit="UNKNOWN",
        policy_fit="FAIL" if disqualifiers else "PASS",
        eligible=not disqualifiers,
        evidence={
            "policy": f"{policy.key}/{policy.version}",
            "supporting_fact_ids": [str(value) for value in supporting_fact_ids],
            "observed_in_repository": True,
        },
        disqualifiers=disqualifiers,
        unknowns=(
            "Observed use does not prove license or security policy compliance.",
        ),
    )


def _with_disqualifier(eligibility: OptionEligibility, message: str) -> OptionEligibility:
    return OptionEligibility(
        policy_id=eligibility.policy_id,
        capability_fit=eligibility.capability_fit,
        api_fit=eligibility.api_fit,
        behavior_fit=eligibility.behavior_fit,
        runtime_fit=eligibility.runtime_fit,
        license_fit=eligibility.license_fit,
        security_fit=eligibility.security_fit,
        policy_fit="FAIL",
        eligible=False,
        evidence=eligibility.evidence,
        disqualifiers=tuple(sorted({*eligibility.disqualifiers, message})),
        unknowns=eligibility.unknowns,
    )


def _version_satisfies(observed: str, constraint: str) -> bool:
    observed_parts = _version_parts(observed)
    match = constraint.strip()
    operator = next((value for value in (">=", "<=", ">", "<", "=") if match.startswith(value)), "=")
    required_parts = _version_parts(match[len(operator):].strip() if match.startswith(operator) else match)
    if not observed_parts or not required_parts:
        return False
    width = max(len(observed_parts), len(required_parts))
    left = observed_parts + (0,) * (width - len(observed_parts))
    right = required_parts + (0,) * (width - len(required_parts))
    return {
        ">=": left >= right,
        "<=": left <= right,
        ">": left > right,
        "<": left < right,
        "=": left == right,
    }[operator]


def _version_parts(value: str) -> tuple[int, ...]:
    match = re.match(r"^[vV]?(\d+(?:\.\d+)*)", value)
    return tuple(int(part) for part in match.group(1).split(".")) if match else ()


def _impact_estimate(
    call_sites: int,
    locations: tuple[Mapping[str, Any], ...],
    code_units: tuple[CodeUnitEvidence, ...],
) -> ImpactEstimate:
    paths = {str(item.get("path")) for item in locations if item.get("path")}
    relevant_units = tuple(unit for unit in code_units if unit.path in paths)
    tests = tuple(sorted({test for unit in relevant_units for test in unit.covering_tests}))
    covered_paths = {unit.path for unit in relevant_units if unit.covering_tests}
    location_paths = [str(item.get("path")) for item in locations if item.get("path")]
    covered = min(call_sites, sum(path in covered_paths for path in location_paths))
    dynamic = tuple(sorted({value for unit in relevant_units for value in unit.dynamic_signals}))
    touchpoints = {
        (str(item.get("kind")), str(item.get("path"))): dict(item)
        for unit in relevant_units for item in unit.touchpoints
    }
    configuration = tuple(
        touchpoints[key] for key in sorted(touchpoints) if key[0] == "CONFIGURATION"
    )
    build = tuple(touchpoints[key] for key in sorted(touchpoints) if key[0] == "BUILD")
    deployment = tuple(
        touchpoints[key] for key in sorted(touchpoints) if key[0] == "DEPLOYMENT"
    )
    uncovered = max(0, call_sites - covered)
    points = (
        call_sites + 2 * len(paths) + uncovered + 2 * len(dynamic)
        + len(configuration) + len(build) + 2 * len(deployment)
    )
    limitations: list[str] = []
    if uncovered:
        limitations.append(f"{uncovered} affected call sites have no statically linked test file.")
    if dynamic:
        limitations.append("Dynamic behavior signals require runtime validation.")
    if not code_units:
        limitations.append("No code-unit evidence was available for test or touchpoint mapping.")
    confidence = 0.9 if call_sites and not uncovered and not dynamic else 0.72 if call_sites else 0.5
    return ImpactEstimate(
        affected_call_sites=call_sites,
        affected_files=len(paths),
        covered_call_sites=covered,
        uncovered_call_sites=uncovered,
        affected_test_files=tests,
        dynamic_signals=dynamic,
        configuration_touchpoints=configuration,
        build_touchpoints=build,
        deployment_touchpoints=deployment,
        evidence_locations=locations,
        confidence=confidence,
        effort_points=points,
        limitations=tuple(limitations),
    )


def _effort(points: int) -> str:
    if points <= 15:
        return "LOW"
    if points <= 60:
        return "MEDIUM"
    return "HIGH"


def _package_key(canonical_key: str) -> str:
    return canonical_key.rsplit("@", 1)[0] if "@" in canonical_key else canonical_key
