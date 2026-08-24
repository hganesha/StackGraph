from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass
from math import isfinite
from typing import Iterable


@dataclass(frozen=True, slots=True)
class RankedMetric:
    entity_id: str
    metric_key: str
    numeric_value: float
    percentile: float
    rank: int
    components: dict[str, object]
    limitations: tuple[dict[str, object], ...] = ()


@dataclass(frozen=True, slots=True)
class ReachabilityResult:
    reachable: dict[str, int]
    depth: dict[str, int]
    limited_entities: frozenset[str]


@dataclass(frozen=True, slots=True)
class BridgeResult:
    articulation_entities: frozenset[str]
    bridge_fact_ids: frozenset[str]


@dataclass(frozen=True, slots=True)
class MaterializedImpactPath:
    source_entity_id: str
    target_entity_id: str
    target_kind: str
    distance: int
    entity_ids: tuple[str, ...]
    fact_ids: tuple[str, ...]
    minimum_confidence: float


@dataclass(frozen=True, slots=True)
class CircularDependencyMotif:
    entity_ids: tuple[str,...]
    fact_ids: tuple[str,...]
    minimum_confidence: float


@dataclass(frozen=True, slots=True)
class CohortAnomaly:
    entity_id: str
    metric_key: str
    score: float
    cohort_key: str
    cohort_size: int
    numeric_value: float


def rank_metrics(
    metric_key: str,
    values: Iterable[tuple[str, float, dict[str, object]]],
    *,
    limitations: tuple[dict[str, object], ...] = (),
) -> list[RankedMetric]:
    ordered = sorted(
        (
            (entity_id, float(value), components)
            for entity_id, value, components in values
            if isfinite(float(value))
        ),
        key=lambda item: (-item[1], item[0]),
    )
    count = len(ordered)
    value_counts: dict[float, int] = defaultdict(int)
    for _, value, _ in ordered:
        value_counts[value] += 1
    below_by_value: dict[float, int] = {}
    below = 0
    for value in sorted(value_counts):
        below_by_value[value] = below
        below += value_counts[value]
    ranked: list[RankedMetric] = []
    prior_value: float | None = None
    prior_rank = 0
    for position, (entity_id, value, components) in enumerate(ordered, start=1):
        if prior_value is None or value != prior_value:
            prior_rank = position
            prior_value = value
        percentile = 0.5 if count == 1 else (
            below_by_value[value]+0.5*(value_counts[value]-1)
        )/(count-1)
        ranked.append(
            RankedMetric(
                entity_id=entity_id,
                metric_key=metric_key,
                numeric_value=value,
                percentile=percentile,
                rank=prior_rank,
                components=components,
                limitations=limitations,
            )
        )
    return ranked


def reachability_metrics(
    nodes: Iterable[str],
    directed_edges: Iterable[tuple[str, str]],
    *,
    exact_node_limit: int = 10_000,
    bounded_max_depth: int = 4,
    bounded_visit_cap: int = 50_000,
) -> ReachabilityResult:
    node_list = tuple(dict.fromkeys(nodes))
    adjacency: dict[str, list[str]] = defaultdict(list)
    for source, target in directed_edges:
        adjacency[source].append(target)

    exact = len(node_list) <= exact_node_limit
    reachable: dict[str, int] = {}
    depth: dict[str, int] = {}
    limited: set[str] = set()
    for source in node_list:
        seen = {source}
        queue = deque([(source, 0)])
        greatest_depth = 0
        capped = False
        while queue:
            current, current_depth = queue.popleft()
            if not exact and current_depth >= bounded_max_depth:
                if adjacency.get(current):
                    capped = True
                continue
            for target in adjacency.get(current, ()):
                if target in seen:
                    continue
                seen.add(target)
                next_depth = current_depth + 1
                greatest_depth = max(greatest_depth, next_depth)
                queue.append((target, next_depth))
                if not exact and len(seen) - 1 >= bounded_visit_cap:
                    queue.clear()
                    capped = True
                    break
        reachable[source] = len(seen) - 1
        depth[source] = greatest_depth
        if capped:
            limited.add(source)
    return ReachabilityResult(reachable, depth, frozenset(limited))


def articulation_points_and_bridges(
    nodes: Iterable[str],
    edges: Iterable[tuple[str, str, str]],
) -> BridgeResult:
    adjacency: dict[str, list[tuple[str, int]]] = defaultdict(list)
    indexed_edges: list[tuple[str, str, str]] = []
    for source, target, fact_id in edges:
        edge_index = len(indexed_edges)
        indexed_edges.append((source, target, fact_id))
        adjacency[source].append((target, edge_index))
        adjacency[target].append((source, edge_index))

    discovery: dict[str, int] = {}
    low: dict[str, int] = {}
    articulation: set[str] = set()
    bridges: set[str] = set()
    clock = 0

    def visit(node: str, parent_edge: int | None) -> None:
        nonlocal clock
        clock += 1
        discovery[node] = low[node] = clock
        children = 0
        for neighbor, edge_index in adjacency.get(node, ()):
            if edge_index == parent_edge:
                continue
            if neighbor not in discovery:
                children += 1
                visit(neighbor, edge_index)
                low[node] = min(low[node], low[neighbor])
                if parent_edge is not None and low[neighbor] >= discovery[node]:
                    articulation.add(node)
                if low[neighbor] > discovery[node]:
                    bridges.add(indexed_edges[edge_index][2])
            else:
                low[node] = min(low[node], discovery[neighbor])
        if parent_edge is None and children > 1:
            articulation.add(node)

    for node in nodes:
        if node not in discovery:
            visit(node, None)
    return BridgeResult(frozenset(articulation), frozenset(bridges))


def materialize_impact_paths(
    node_kinds: dict[str, str],
    directed_edges: Iterable[tuple[str, str, str, float]],
    *,
    target_kinds: frozenset[str] = frozenset({"Application", "BusinessCapability"}),
    per_source_limit: int = 20,
    max_depth: int | None = None,
) -> tuple[MaterializedImpactPath, ...]:
    adjacency: dict[str, list[tuple[str, str, float]]] = defaultdict(list)
    for source, target, fact_id, confidence in directed_edges:
        adjacency[source].append((target,fact_id,confidence))
    for neighbors in adjacency.values():
        neighbors.sort(key=lambda item:(item[0],item[1]))

    result: list[MaterializedImpactPath] = []
    for source in sorted(node_kinds):
        predecessor: dict[str, tuple[str, str, float]] = {}
        queue = deque([(source,0)])
        targets: list[str] = []
        while queue and len(targets)<per_source_limit:
            current,depth = queue.popleft()
            if max_depth is not None and depth>=max_depth:
                continue
            for target,fact_id,confidence in adjacency.get(current,()):
                if target==source or target in predecessor:
                    continue
                predecessor[target]=(current,fact_id,confidence)
                queue.append((target,depth+1))
                if node_kinds.get(target) in target_kinds:
                    targets.append(target)
                    if len(targets)>=per_source_limit:
                        break
        for target in targets:
            reverse_entities=[target]
            reverse_facts: list[str]=[]
            confidences: list[float]=[]
            cursor=target
            while cursor!=source:
                parent,fact_id,confidence=predecessor[cursor]
                reverse_facts.append(fact_id)
                confidences.append(confidence)
                reverse_entities.append(parent)
                cursor=parent
            entity_ids=tuple(reversed(reverse_entities))
            fact_ids=tuple(reversed(reverse_facts))
            result.append(MaterializedImpactPath(
                source_entity_id=source,target_entity_id=target,
                target_kind=node_kinds[target],distance=len(fact_ids),
                entity_ids=entity_ids,fact_ids=fact_ids,
                minimum_confidence=min(confidences),
            ))
    return tuple(result)


def circular_dependency_motifs(
    nodes: Iterable[str],
    edges: Iterable[tuple[str,str,str,float]],
) -> tuple[CircularDependencyMotif,...]:
    node_list = tuple(dict.fromkeys(nodes))
    edge_list = tuple(edges)
    adjacency: dict[str,list[str]] = defaultdict(list)
    reverse: dict[str,list[str]] = defaultdict(list)
    for source,target,_,_ in edge_list:
        adjacency[source].append(target)
        reverse[target].append(source)
    visited: set[str] = set()
    order: list[str] = []
    for node in node_list:
        if node in visited:
            continue
        stack: list[tuple[str,bool]] = [(node,False)]
        while stack:
            current,expanded = stack.pop()
            if expanded:
                order.append(current)
                continue
            if current in visited:
                continue
            visited.add(current)
            stack.append((current,True))
            stack.extend((target,False) for target in reversed(adjacency.get(current,())) if target not in visited)
    assigned: set[str] = set()
    components: list[set[str]] = []
    for node in reversed(order):
        if node in assigned:
            continue
        component: set[str] = set()
        queue = [node]
        assigned.add(node)
        while queue:
            current = queue.pop()
            component.add(current)
            for source in reverse.get(current,()):
                if source not in assigned:
                    assigned.add(source)
                    queue.append(source)
        if len(component)>1 or any(source==target==node for source,target,_,_ in edge_list):
            components.append(component)
    motifs: list[CircularDependencyMotif] = []
    for component in components:
        internal = sorted(
            (fact_id,confidence) for source,target,fact_id,confidence in edge_list
            if source in component and target in component
        )
        if internal:
            motifs.append(CircularDependencyMotif(
                entity_ids=tuple(sorted(component)),
                fact_ids=tuple(fact_id for fact_id,_ in internal),
                minimum_confidence=min(confidence for _,confidence in internal),
            ))
    return tuple(sorted(motifs,key=lambda motif:motif.entity_ids))


def cohort_percentile_anomalies(
    metric_key: str,
    values: Iterable[tuple[str,float]],
    *,
    cohort_key: str,
    minimum_cohort_size: int=5,
    percentile_threshold: float=0.95,
) -> tuple[CohortAnomaly,...]:
    rows = list(values)
    if len(rows)<minimum_cohort_size:
        return ()
    ranked = rank_metrics(metric_key,((entity_id,value,{}) for entity_id,value in rows))
    return tuple(CohortAnomaly(
        entity_id=item.entity_id,metric_key=metric_key,score=item.percentile,
        cohort_key=cohort_key,cohort_size=len(rows),numeric_value=item.numeric_value,
    ) for item in ranked if item.percentile>=percentile_threshold)
