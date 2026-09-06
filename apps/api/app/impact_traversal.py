"""Predicate-aware impact traversal driven by a versioned, persisted `ImpactPolicy`.

Phase 2 §12 is explicit that blast radius must not mean generic N-hop traversal: the edges
walked, the direction, the depth, and the classification of what is reached all follow from
`predicate + subject type + impact policy`. M1 adds that the policy must be persisted and
versioned, and that repeated traversal over the same snapshot and policy must be deterministic.

This module is the engine that reads such a policy and walks it. It holds no knowledge of any
particular predicate: the seed set is supplied by the caller (resolving a package name to its
dependents is package-specific work), and everything after the seed is decided by the policy's
edge rules. Adding `DEPRECATE API` therefore means seeding differently and inserting a policy
row, not writing a second traversal.

Determinism is a property of the walk, not an accident of the query planner. Every expansion is
ordered by `(depth, canonical key, entity id)`, budgets are consumed in that order, and a
truncated traversal reports which budget stopped it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping, Sequence
from uuid import UUID


CLASSIFICATIONS = ("DIRECT", "TRANSITIVE", "CONTEXT", "STOP", "INFORMATIONAL")
DIRECTIONS = ("INBOUND", "OUTBOUND")


class ImpactPolicyError(RuntimeError):
    """Raised when a persisted policy cannot be interpreted.

    A policy that cannot be read is a refusal, never a silent fallback to a default walk: a
    simulation whose traversal did not follow its pinned policy would carry a policy version
    that does not describe how it was produced.
    """


@dataclass(frozen=True)
class EdgeRule:
    predicate: str
    direction: str
    from_types: frozenset[str]
    to_types: frozenset[str]
    classification: str
    max_depth: int
    weight: float

    @classmethod
    def from_json(cls, value: Mapping[str, Any], *, policy_key: str) -> "EdgeRule":
        predicate = str(value.get("predicate") or "")
        direction = str(value.get("direction") or "")
        classification = str(value.get("classification") or "")
        if not predicate:
            raise ImpactPolicyError(f"policy {policy_key} has an edge rule without a predicate")
        if direction not in DIRECTIONS:
            raise ImpactPolicyError(
                f"policy {policy_key} edge {predicate} has unknown direction {direction!r}"
            )
        if classification not in CLASSIFICATIONS:
            raise ImpactPolicyError(
                f"policy {policy_key} edge {predicate} has unknown classification {classification!r}"
            )
        from_types = frozenset(str(item) for item in value.get("from_types") or ())
        if not from_types:
            raise ImpactPolicyError(
                f"policy {policy_key} edge {predicate} does not say which entity types it expands from"
            )
        return cls(
            predicate=predicate,
            direction=direction,
            from_types=from_types,
            to_types=frozenset(str(item) for item in value.get("to_types") or ()),
            classification=classification,
            max_depth=int(value.get("max_depth") or 1),
            weight=float(value.get("weight") if value.get("weight") is not None else 0.5),
        )


@dataclass(frozen=True)
class CapabilityRule:
    """How business capability reaches a simulation.

    Kept separate from `EdgeRule` because the capability-to-application relationship is a
    curated business map, not a projected fact edge. Treating it as an ordinary edge would let
    curation be cited as observed evidence.
    """

    classification: str
    from_types: frozenset[str]
    max_depth: int
    tier_zero_criticality: int

    @classmethod
    def from_json(cls, value: Mapping[str, Any], *, policy_key: str) -> "CapabilityRule":
        classification = str(value.get("classification") or "TRANSITIVE")
        if classification not in CLASSIFICATIONS:
            raise ImpactPolicyError(
                f"policy {policy_key} capability rule has unknown classification {classification!r}"
            )
        return cls(
            classification=classification,
            from_types=frozenset(str(item) for item in value.get("from_types") or ("Application",)),
            max_depth=int(value.get("max_depth") or 4),
            tier_zero_criticality=int(value.get("tier_zero_criticality") or 1),
        )


@dataclass(frozen=True)
class ImpactPolicyConfiguration:
    policy_key: str
    schema_version: str
    max_depth: int
    max_nodes: int
    max_edges: int
    minimum_confidence: float
    seed_kind: str
    seed_subject_types: frozenset[str]
    seed_classification: str
    edges: tuple[EdgeRule, ...]
    capability_rule: CapabilityRule | None
    stop_conditions: frozenset[str]

    @classmethod
    def from_row(cls, row: Mapping[str, Any]) -> "ImpactPolicyConfiguration":
        policy_key = str(row.get("policy_key") or "unknown")
        configuration = row.get("configuration")
        if not isinstance(configuration, Mapping):
            raise ImpactPolicyError(f"policy {policy_key} has no configuration object")
        seed = configuration.get("seed")
        if not isinstance(seed, Mapping):
            raise ImpactPolicyError(f"policy {policy_key} does not declare a seed")
        seed_classification = str(seed.get("classification") or "DIRECT")
        if seed_classification not in CLASSIFICATIONS:
            raise ImpactPolicyError(
                f"policy {policy_key} seed has unknown classification {seed_classification!r}"
            )
        edges = configuration.get("edges")
        if not isinstance(edges, Sequence) or isinstance(edges, (str, bytes)):
            raise ImpactPolicyError(f"policy {policy_key} does not declare an edge list")
        capability = configuration.get("capability_rule")
        return cls(
            policy_key=policy_key,
            schema_version=str(configuration.get("schema_version") or "impact-policy/1.0.0"),
            max_depth=int(configuration.get("max_depth") or 1),
            max_nodes=int(configuration.get("max_nodes") or 0),
            max_edges=int(configuration.get("max_edges") or 0),
            minimum_confidence=float(configuration.get("minimum_confidence") or 0),
            seed_kind=str(seed.get("kind") or "PACKAGE_DEPENDENTS"),
            seed_subject_types=frozenset(
                str(item) for item in seed.get("subject_types") or ("Repository",)
            ),
            seed_classification=seed_classification,
            edges=tuple(
                EdgeRule.from_json(item, policy_key=policy_key)
                for item in edges
                if isinstance(item, Mapping)
            ),
            capability_rule=(
                CapabilityRule.from_json(capability, policy_key=policy_key)
                if isinstance(capability, Mapping) else None
            ),
            stop_conditions=frozenset(
                str(item) for item in configuration.get("stop_conditions") or ()
            ),
        )

    def rules_for(self, entity_type: str, depth: int) -> tuple[EdgeRule, ...]:
        """Edge rules that may expand a node of `entity_type` sitting at `depth`.

        A rule's `max_depth` is the deepest hop it may *produce*, so a node at depth d is
        expandable by it only while `d + 1` stays within both the rule's and the policy's bound.
        """
        return tuple(
            rule for rule in self.edges
            if entity_type in rule.from_types
            and depth + 1 <= min(rule.max_depth, self.max_depth)
        )


@dataclass
class TraversedNode:
    entity_id: UUID
    entity_type: str
    name: str
    canonical_key: str | None
    depth: int
    classification: str
    weight: float
    predicate: str | None
    origin_id: UUID | None
    fact_id: UUID | None
    confidence: float
    path: tuple[UUID, ...]
    properties: Mapping[str, Any] = field(default_factory=dict)


@dataclass
class StoppedBranch:
    entity_id: UUID
    entity_type: str
    name: str
    depth: int
    predicate: str | None
    reason: str
    fact_id: UUID | None
    confidence: float
    path: tuple[UUID, ...]


@dataclass
class TraversalResult:
    nodes: list[TraversedNode] = field(default_factory=list)
    stopped: list[StoppedBranch] = field(default_factory=list)
    limitations: list[dict[str, Any]] = field(default_factory=list)
    scanner_versions: set[str] = field(default_factory=set)
    truncated: bool = False
    edges_walked: int = 0

    def by_classification(self, classification: str) -> list[TraversedNode]:
        return [node for node in self.nodes if node.classification == classification]

    def entity_ids_of_type(self, entity_type: str) -> list[UUID]:
        return [node.entity_id for node in self.nodes if node.entity_type == entity_type]

    def note(self, code: str, message: str) -> None:
        if not any(item["code"] == code for item in self.limitations):
            self.limitations.append({"code": code, "message": message, "evidence_fact_ids": []})


def eligibility(
    *, has_evidence: bool, confidence: float, minimum_confidence: float,
) -> str | None:
    """Return the stop reason for an ineligible edge, or None when it may be walked.

    §19 and §9.1 together mean an edge without evidence is not a weak edge, it is an edge the
    simulator may not assert. It becomes a recorded STOP rather than a silent omission.
    """
    if not has_evidence:
        return "missing evidence"
    if confidence < minimum_confidence:
        return f"confidence below {minimum_confidence:.2f}"
    return None


class ImpactTraversal:
    """Walks the estate for one mutation under one pinned policy."""

    def __init__(self, database: Any, *, tenant_id: UUID, policy: ImpactPolicyConfiguration):
        self.database = database
        self.tenant_id = tenant_id
        self.policy = policy

    async def expand(
        self,
        seeds: Iterable[TraversedNode],
        *,
        node_budget: int,
        edge_budget: int,
    ) -> TraversalResult:
        result = TraversalResult()
        seen: dict[UUID, TraversedNode] = {}
        frontier: list[TraversedNode] = []
        for seed in sorted(seeds, key=lambda item: (item.canonical_key or "", str(item.entity_id))):
            if seed.entity_id in seen:
                continue
            seen[seed.entity_id] = seed
            result.nodes.append(seed)
            frontier.append(seed)

        depth = max((seed.depth for seed in frontier), default=0)
        while frontier and depth < self.policy.max_depth:
            grouped: dict[tuple[str, str, str], list[TraversedNode]] = {}
            for node in frontier:
                for rule in self.policy.rules_for(node.entity_type, node.depth):
                    key = (rule.predicate, rule.direction, rule.classification)
                    grouped.setdefault(key, []).append(node)
            if not grouped:
                break
            next_frontier: list[TraversedNode] = []
            for key in sorted(grouped):
                predicate, direction, classification = key
                rule = next(
                    item for item in self.policy.edges
                    if item.predicate == predicate
                    and item.direction == direction
                    and item.classification == classification
                )
                origins = {node.entity_id: node for node in grouped[key]}
                remaining_edges = edge_budget - result.edges_walked
                if remaining_edges <= 0:
                    result.truncated = True
                    result.note(
                        "TRAVERSAL_BUDGET",
                        "The edge budget stopped the traversal before every policy rule ran.",
                    )
                    break
                rows = await self._fetch(rule, list(origins), limit=remaining_edges + 1)
                if len(rows) > remaining_edges:
                    rows = rows[:remaining_edges]
                    result.truncated = True
                    result.note(
                        "TRAVERSAL_BUDGET",
                        "The edge budget truncated the traversal.",
                    )
                result.edges_walked += len(rows)
                for row in rows:
                    origin = origins[row["origin_id"]]
                    confidence = float(row["confidence"])
                    reason = eligibility(
                        has_evidence=row["has_evidence"],
                        confidence=confidence,
                        minimum_confidence=self.policy.minimum_confidence,
                    )
                    path = (*origin.path, row["id"])
                    if reason is not None:
                        result.stopped.append(StoppedBranch(
                            entity_id=row["id"], entity_type=row["entity_type"],
                            name=row["name"], depth=origin.depth + 1, predicate=rule.predicate,
                            reason=reason,
                            fact_id=row["fact_id"] if row["has_evidence"] else None,
                            confidence=confidence, path=path,
                        ))
                        continue
                    if row["id"] in seen:
                        continue
                    if len(seen) >= node_budget:
                        result.truncated = True
                        result.note(
                            "TRAVERSAL_BUDGET",
                            "The node budget truncated the traversal.",
                        )
                        break
                    node = TraversedNode(
                        entity_id=row["id"], entity_type=row["entity_type"], name=row["name"],
                        canonical_key=row["canonical_key"], depth=origin.depth + 1,
                        classification=rule.classification, weight=rule.weight,
                        predicate=rule.predicate, origin_id=origin.entity_id,
                        fact_id=row["fact_id"], confidence=confidence, path=path,
                    )
                    seen[row["id"]] = node
                    result.nodes.append(node)
                    next_frontier.append(node)
                    result.scanner_versions.add(
                        f"{row['extractor_key']}/{row['extractor_version']}"
                    )
            frontier = sorted(
                next_frontier, key=lambda item: (item.canonical_key or "", str(item.entity_id)),
            )
            depth += 1

        if frontier and depth >= self.policy.max_depth and "MAX_DEPTH" in self.policy.stop_conditions:
            result.note(
                "MAX_DEPTH",
                f"The policy's depth bound of {self.policy.max_depth} stopped further expansion.",
            )
        return result

    async def _fetch(
        self, rule: EdgeRule, origin_ids: list[UUID], *, limit: int,
    ) -> list[dict[str, Any]]:
        # INBOUND means the edge arrives at the origin, so the origin is the fact's object and
        # the entity we reach is its subject. `Application IMPLEMENTED_BY Repository` is walked
        # inbound from the repository to find the application it implements.
        if rule.direction == "INBOUND":
            anchor, reached = "object_entity_id", "subject_entity_id"
        else:
            anchor, reached = "subject_entity_id", "object_entity_id"
        type_filter = " AND related.entity_type=ANY(%s::text[])" if rule.to_types else ""
        parameters: list[Any] = [origin_ids, self.tenant_id, rule.predicate]
        if rule.to_types:
            parameters.append(sorted(rule.to_types))
        parameters.append(limit)
        return await self.database.fetch_all(
            f"""
            SELECT relationship.id fact_id,relationship.confidence,
                   relationship.extractor_key,relationship.extractor_version,
                   origin.id origin_id,
                   related.id,related.entity_type,related.name,related.canonical_key,
                   EXISTS(
                     SELECT 1 FROM evidence WHERE fact_assertion_id=relationship.id
                   ) has_evidence
            FROM fact_assertion relationship
            JOIN entity origin ON origin.id=relationship.{anchor}
                             AND origin.id=ANY(%s::uuid[])
            JOIN entity related ON related.id=relationship.{reached}
            WHERE relationship.tenant_id=%s AND relationship.system_to IS NULL
              AND relationship.predicate=%s
              AND related.id<>origin.id
              {type_filter}
            ORDER BY origin.canonical_key,related.canonical_key,related.id,relationship.id
            LIMIT %s
            """,
            tuple(parameters), tenant_id=self.tenant_id,
        )

    async def capabilities(
        self, application_ids: list[UUID], *, limit: int,
    ) -> list[dict[str, Any]]:
        """Curated business capability impact for the reached applications.

        §22 is the reason this exists: "73 repositories" is a much weaker statement than
        "Payment Authorization, a Tier-0 capability, is affected". The relationship is curated
        on the business map, so it carries a revision identifier rather than a fact identifier
        and the caller must record it as curated provenance.
        """
        if not application_ids:
            return []
        return await self.database.fetch_all(
            """
            SELECT DISTINCT
                   link.capability_entity_id,link.application_entity_id,link.business_map_id,
                   link.evidence_revision_id,link.analysis_fingerprint,link.confidence,
                   link.criticality,link.observed_at,
                   capability.entity_type,capability.name,capability.canonical_key
            FROM current_capability_application_relationship link
            JOIN entity capability ON capability.id=link.capability_entity_id
            WHERE link.tenant_id=%s AND link.application_entity_id=ANY(%s::uuid[])
            ORDER BY link.criticality,capability.canonical_key,capability.name,
                     link.capability_entity_id,link.application_entity_id
            LIMIT %s
            """,
            (self.tenant_id, sorted(application_ids, key=str), limit),
            tenant_id=self.tenant_id,
        )
