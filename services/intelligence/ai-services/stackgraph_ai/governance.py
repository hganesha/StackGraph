from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping, Sequence


GOVERNANCE_FINGERPRINT_VERSION = "modernization-governance/v1"
PORTFOLIO_SCORING_VERSION = "modernization-portfolio/v1"
CALIBRATION_GATE_VERSION = "modernization-calibration/v1"
ECOSYSTEM_ADMISSION_VERSION = "ecosystem-admission/v1"


def canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_fingerprint(value: object) -> str:
    return "sha256:" + hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def governance_fingerprint(
    *,
    analyzer_key: str,
    analyzer_version: str,
    taxonomy_hash: str,
    alternatives_hash: str,
    policy: Mapping[str, Any],
    internal_components: Sequence[Mapping[str, Any]],
) -> str:
    """Return the explicit replay boundary for governed modernization analysis."""
    return sha256_fingerprint({
        "fingerprint_version": GOVERNANCE_FINGERPRINT_VERSION,
        "analyzer": {"key": analyzer_key, "version": analyzer_version},
        "taxonomy_hash": taxonomy_hash,
        "alternatives_hash": alternatives_hash,
        "policy": policy,
        "internal_components": sorted(
            (dict(component) for component in internal_components),
            key=lambda item: (str(item.get("key", "")), str(item.get("version", ""))),
        ),
    })


@dataclass(frozen=True, slots=True)
class CalibrationMetrics:
    candidate_precision: float | None
    recommendation_acceptance: float | None
    validation_success: float | None
    affected_scope_mae: float | None
    effort_accuracy: float | None
    reviewed_cases: int


@dataclass(frozen=True, slots=True)
class CalibrationThresholds:
    minimum_candidate_precision: float = 0.8
    minimum_recommendation_acceptance: float = 0.5
    minimum_validation_success: float = 0.8
    maximum_affected_scope_mae: float = 0.25
    minimum_effort_accuracy: float = 0.7
    minimum_reviewed_cases: int = 20


@dataclass(frozen=True, slots=True)
class PromotionGateResult:
    passed: bool
    failures: tuple[str, ...]
    fingerprint: str


def evaluate_promotion_gate(
    metrics: CalibrationMetrics,
    thresholds: CalibrationThresholds,
) -> PromotionGateResult:
    failures: list[str] = []
    checks = (
        ("candidate_precision", metrics.candidate_precision, thresholds.minimum_candidate_precision, ">="),
        (
            "recommendation_acceptance",
            metrics.recommendation_acceptance,
            thresholds.minimum_recommendation_acceptance,
            ">=",
        ),
        ("validation_success", metrics.validation_success, thresholds.minimum_validation_success, ">="),
        ("affected_scope_mae", metrics.affected_scope_mae, thresholds.maximum_affected_scope_mae, "<="),
        ("effort_accuracy", metrics.effort_accuracy, thresholds.minimum_effort_accuracy, ">="),
    )
    if metrics.reviewed_cases < thresholds.minimum_reviewed_cases:
        failures.append(
            f"reviewed_cases {metrics.reviewed_cases} < {thresholds.minimum_reviewed_cases}"
        )
    for name, actual, expected, operator in checks:
        if actual is None:
            failures.append(f"{name} is unavailable")
        elif operator == ">=" and actual < expected:
            failures.append(f"{name} {actual:.4f} < {expected:.4f}")
        elif operator == "<=" and actual > expected:
            failures.append(f"{name} {actual:.4f} > {expected:.4f}")
    payload = {
        "gate_version": CALIBRATION_GATE_VERSION,
        "metrics": {
            field: getattr(metrics, field)
            for field in metrics.__dataclass_fields__
        },
        "thresholds": {
            field: getattr(thresholds, field)
            for field in thresholds.__dataclass_fields__
        },
        "failures": failures,
    }
    return PromotionGateResult(
        passed=not failures,
        failures=tuple(failures),
        fingerprint=sha256_fingerprint(payload),
    )


@dataclass(frozen=True, slots=True)
class CapabilityFootprint:
    application_count: int
    repository_count: int
    technology_counts: Mapping[str, int] = field(default_factory=dict)

    @property
    def technology_entropy(self) -> float:
        counts = [value for value in self.technology_counts.values() if value > 0]
        total = sum(counts)
        if total == 0 or len(counts) <= 1:
            return 0.0
        raw = -sum((value / total) * math.log(value / total) for value in counts)
        return raw / math.log(len(counts))

    @property
    def reuse_signal(self) -> float:
        return min(1.0, math.log1p(self.application_count + self.repository_count) / math.log(21))


@dataclass(frozen=True, slots=True)
class PortfolioScoringPolicy:
    business_weight: float = 0.25
    viability_gap_weight: float = 0.2
    entropy_weight: float = 0.2
    reuse_weight: float = 0.2
    confidence_weight: float = 0.15
    effort_penalty_weight: float = 0.2
    version: str = PORTFOLIO_SCORING_VERSION

    def __post_init__(self) -> None:
        values = (
            self.business_weight,
            self.viability_gap_weight,
            self.entropy_weight,
            self.reuse_weight,
            self.confidence_weight,
            self.effort_penalty_weight,
        )
        if any(value < 0 or value > 1 for value in values):
            raise ValueError("portfolio weights must be between zero and one")
        if sum(values[:5]) <= 0:
            raise ValueError("at least one positive portfolio benefit weight is required")


@dataclass(frozen=True, slots=True)
class PortfolioCandidate:
    id: str
    business_importance: float
    viability_gap: float
    confidence: float
    effort_points: int
    footprint: CapabilityFootprint
    mutually_exclusive_group: str | None = None


@dataclass(frozen=True, slots=True)
class ScoredPortfolioCandidate:
    candidate: PortfolioCandidate
    score: float
    components: Mapping[str, float]
    policy_version: str


def score_portfolio_candidate(
    candidate: PortfolioCandidate,
    policy: PortfolioScoringPolicy,
) -> ScoredPortfolioCandidate:
    business = _bounded(candidate.business_importance)
    viability_gap = _bounded(candidate.viability_gap)
    confidence = _bounded(candidate.confidence)
    entropy = candidate.footprint.technology_entropy
    reuse = candidate.footprint.reuse_signal
    effort_penalty = min(1.0, max(0, candidate.effort_points) / 34.0)
    benefits = {
        "business": business * policy.business_weight,
        "viability_gap": viability_gap * policy.viability_gap_weight,
        "entropy": entropy * policy.entropy_weight,
        "reuse": reuse * policy.reuse_weight,
        "confidence": confidence * policy.confidence_weight,
    }
    denominator = sum((
        policy.business_weight,
        policy.viability_gap_weight,
        policy.entropy_weight,
        policy.reuse_weight,
        policy.confidence_weight,
    ))
    gross = sum(benefits.values()) / denominator
    score = _bounded(gross - effort_penalty * policy.effort_penalty_weight)
    return ScoredPortfolioCandidate(
        candidate=candidate,
        score=score,
        components={
            "business": business,
            "viability_gap": viability_gap,
            "entropy": entropy,
            "reuse": reuse,
            "confidence": confidence,
            "effort_penalty": effort_penalty,
        },
        policy_version=policy.version,
    )


def optimize_portfolio(
    candidates: Iterable[ScoredPortfolioCandidate],
    *,
    budget_points: int,
) -> tuple[ScoredPortfolioCandidate, ...]:
    """Deterministic 0/1 budget optimization with mutual-exclusion support."""
    if budget_points < 0:
        raise ValueError("budget_points must be non-negative")
    ordered = tuple(sorted(candidates, key=lambda item: item.candidate.id))
    states: dict[tuple[int, tuple[str, ...]], tuple[float, tuple[str, ...]]] = {
        (0, ()): (0.0, ())
    }
    by_id = {item.candidate.id: item for item in ordered}
    for item in ordered:
        effort = max(1, item.candidate.effort_points)
        group = item.candidate.mutually_exclusive_group
        next_states = dict(states)
        for (used, groups), (value, selected) in states.items():
            if used + effort > budget_points or (group is not None and group in groups):
                continue
            next_groups = tuple(sorted((*groups, group))) if group is not None else groups
            key = (used + effort, next_groups)
            proposal = (value + item.score, (*selected, item.candidate.id))
            prior = next_states.get(key)
            if prior is None or proposal[0] > prior[0] or (
                math.isclose(proposal[0], prior[0]) and proposal[1] < prior[1]
            ):
                next_states[key] = proposal
        states = next_states
    _, selected = max(
        states.values(),
        key=lambda value: (value[0], tuple(reversed(value[1]))),
    )
    return tuple(by_id[item] for item in selected)


@dataclass(frozen=True, slots=True)
class EcosystemDemand:
    ecosystem: str
    observed_repositories: int
    observed_dependency_share: float
    metadata_parity: bool
    calibration_gate_passed: bool


@dataclass(frozen=True, slots=True)
class EcosystemAdmissionDecision:
    admitted: bool
    reasons: tuple[str, ...]
    fingerprint: str


def evaluate_ecosystem_admission(
    demand: EcosystemDemand,
    *,
    predecessor_admitted: bool,
    minimum_repositories: int = 10,
    minimum_dependency_share: float = 0.02,
) -> EcosystemAdmissionDecision:
    reasons: list[str] = []
    if not predecessor_admitted:
        reasons.append("predecessor ecosystem has not been admitted")
    if demand.observed_repositories < minimum_repositories:
        reasons.append("observed repository demand is below threshold")
    if demand.observed_dependency_share < minimum_dependency_share:
        reasons.append("observed dependency share is below threshold")
    if not demand.metadata_parity:
        reasons.append("metadata parity is incomplete")
    if not demand.calibration_gate_passed:
        reasons.append("calibration promotion gate has not passed")
    payload = {
        "version": ECOSYSTEM_ADMISSION_VERSION,
        "demand": {
            field: getattr(demand, field) for field in demand.__dataclass_fields__
        },
        "predecessor_admitted": predecessor_admitted,
        "minimum_repositories": minimum_repositories,
        "minimum_dependency_share": minimum_dependency_share,
        "reasons": reasons,
    }
    return EcosystemAdmissionDecision(
        admitted=not reasons,
        reasons=tuple(reasons),
        fingerprint=sha256_fingerprint(payload),
    )


def _bounded(value: float) -> float:
    return min(1.0, max(0.0, float(value)))
