from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass
from itertools import combinations
from typing import AbstractSet, Mapping


@dataclass(frozen=True)
class ApplicationFeatures:
    dependencies: frozenset[str]
    transitive_dependencies: frozenset[str] = frozenset()
    capabilities: frozenset[str] = frozenset()
    technologies: frozenset[str] = frozenset()
    owners: frozenset[str] = frozenset()
    deployments: frozenset[str] = frozenset()


def weighted_jaccard(
    left: AbstractSet[str],
    right: AbstractSet[str],
    *,
    document_frequency: Mapping[str, int],
    corpus_size: int,
) -> tuple[float, list[str]]:
    union = left | right
    if not union:
        return 0.0, []
    weights = {
        item: math.log((1 + max(1, corpus_size)) / (1 + document_frequency.get(item, 0))) + 1
        for item in union
    }
    denominator = sum(weights.values())
    overlap = sorted(left & right)
    numerator = sum(weights[item] for item in overlap)
    return (numerator / denominator if denominator else 0.0), overlap


def jaccard(left: AbstractSet[str], right: AbstractSet[str]) -> tuple[float, list[str]]:
    union = left | right
    overlap = sorted(left & right)
    return (len(overlap) / len(union) if union else 0.0), overlap


def dependency_frequencies(features: Mapping[str, ApplicationFeatures]) -> Counter[str]:
    return Counter(item for feature in features.values() for item in feature.dependencies)


def candidate_pairs(features: Mapping[str,ApplicationFeatures],*,max_pairs: int=100_000) -> list[tuple[str,str]]:
    buckets: dict[tuple[str,str],set[str]] = {}
    for application_id,feature in features.items():
        for kind,items in (
            ("dependency",feature.dependencies),("capability",feature.capabilities),
            ("technology",feature.technologies),
        ):
            for item in items:
                buckets.setdefault((kind,item),set()).add(application_id)
    pairs: set[tuple[str,str]] = set()
    for bucket in sorted(buckets):
        members = sorted(buckets[bucket])
        for left,right in combinations(members,2):
            pairs.add((left,right))
            if len(pairs)>max_pairs:
                raise ValueError(f"similarity candidate budget exceeded ({max_pairs})")
    return sorted(pairs)


def deterministic_application_similarity(
    left: ApplicationFeatures,
    right: ApplicationFeatures,
    *,
    dependency_frequency: Mapping[str, int],
    corpus_size: int,
) -> dict[str, object]:
    direct, direct_overlap = weighted_jaccard(
        left.dependencies, right.dependencies,
        document_frequency=dependency_frequency, corpus_size=corpus_size,
    )
    transitive, transitive_overlap = weighted_jaccard(
        left.transitive_dependencies, right.transitive_dependencies,
        document_frequency=dependency_frequency, corpus_size=corpus_size,
    )
    capability, capability_overlap = jaccard(left.capabilities, right.capabilities)
    technology, technology_overlap = jaccard(left.technologies, right.technologies)
    owner_overlap, shared_owners = jaccard(left.owners, right.owners)
    deployment_overlap, shared_deployments = jaccard(left.deployments, right.deployments)
    missing_business_context = not left.capabilities or not right.capabilities
    weights = {"direct": 0.35, "transitive": 0.15, "capability": 0.30, "technology": 0.20}
    available = {
        "direct": bool(left.dependencies or right.dependencies),
        "transitive": bool(left.transitive_dependencies or right.transitive_dependencies),
        "capability": not missing_business_context,
        "technology": bool(left.technologies and right.technologies),
    }
    weights = {key:value for key,value in weights.items() if available[key]}
    total = sum(weights.values())
    weights = {key:value/total for key,value in weights.items()} if total else {}
    components = {
        "direct": direct, "transitive": transitive,
        "capability": capability, "technology": technology,
    }
    score = sum(components[key] * weight for key, weight in weights.items())
    return {
        "score": max(0.0, min(1.0, score)),
        "components": components,
        "overlaps": {
            "direct_dependencies": direct_overlap,
            "transitive_dependencies": transitive_overlap,
            "capabilities": capability_overlap,
            "technologies": technology_overlap,
            "owners": shared_owners,
            "deployments": shared_deployments,
        },
        "differences": {
            "dependencies_only_left": sorted(left.dependencies - right.dependencies),
            "dependencies_only_right": sorted(right.dependencies - left.dependencies),
            "capabilities_only_left": sorted(left.capabilities - right.capabilities),
            "capabilities_only_right": sorted(right.capabilities - left.capabilities),
            "different_ownership": bool(left.owners and right.owners and owner_overlap == 0),
            "different_deployments": bool(left.deployments and right.deployments and deployment_overlap == 0),
        },
        "coverage": {
            "deterministic_signal_available": bool(weights),
            "business_context_complete": not missing_business_context,
            "left_dependency_count": len(left.dependencies),
            "right_dependency_count": len(right.dependencies),
        },
        "limitations": ([{"code": "BUSINESS_CONTEXT_MISSING", "message": "Capability overlap was omitted and remaining weights were renormalized."}] if missing_business_context else []),
    }


def hybrid_application_similarity(
    deterministic: Mapping[str, object],
    *,
    semantic_score: float | None = None,
    structural_score: float | None = None,
) -> dict[str, object]:
    deterministic_coverage = deterministic.get("coverage")
    deterministic_available = not isinstance(deterministic_coverage,Mapping) or bool(
        deterministic_coverage.get("deterministic_signal_available",True)
    )
    signals = {
        "deterministic": float(deterministic.get("score") or 0) if deterministic_available else None,
        "semantic": semantic_score,
        "structural": structural_score,
    }
    configured_weights = {"deterministic": 0.65, "semantic": 0.25, "structural": 0.10}
    available_weights = {
        key: weight for key, weight in configured_weights.items()
        if signals[key] is not None
    }
    total_weight = sum(available_weights.values())
    weights = {key: weight / total_weight for key, weight in available_weights.items()}
    score = sum(float(signals[key] or 0) * weight for key, weight in weights.items())
    limitations = list(deterministic.get("limitations") or [])
    if not deterministic_available:
        limitations.append({
            "code": "DETERMINISTIC_SIGNAL_UNAVAILABLE",
            "message": "No governed dependency, capability, or technology features were available; vector signals were renormalized.",
        })
    if semantic_score is None:
        limitations.append({
            "code": "SEMANTIC_SIGNAL_UNAVAILABLE",
            "message": "No active semantic embedding was available; remaining signals were renormalized.",
        })
    if structural_score is None:
        limitations.append({
            "code": "STRUCTURAL_SIGNAL_UNAVAILABLE",
            "message": "No evaluated structural embedding was active; remaining signals were renormalized.",
        })
    components = dict(deterministic.get("components") or {})
    components.update({
        "deterministic_score": signals["deterministic"],
        "semantic_score": semantic_score,
        "structural_score": structural_score,
        "hybrid_weights": weights,
    })
    return {
        **deterministic,
        "score": max(0.0, min(1.0, score)),
        "components": components,
        "limitations": limitations,
    }
