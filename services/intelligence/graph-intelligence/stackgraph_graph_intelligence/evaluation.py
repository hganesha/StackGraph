from __future__ import annotations

import math
from dataclasses import dataclass
from typing import AbstractSet, Sequence


@dataclass(frozen=True,slots=True)
class RelevanceCaseResult:
    ranked_entity_ids: tuple[str,...]
    relevant_entity_ids: frozenset[str]
    hard_negative_entity_ids: frozenset[str] = frozenset()


def evaluate_relevance(cases: Sequence[RelevanceCaseResult]) -> dict[str,float | int]:
    if not cases:
        return {
            "case_count":0,"precision_at_k":0.0,"recall_at_k":0.0,
            "ndcg_at_k":0.0,"hard_negative_rate":0.0,
        }
    precision_total = 0.0
    recall_total = 0.0
    ndcg_total = 0.0
    hard_negative_hits = 0
    hard_negative_total = 0
    for case in cases:
        ranked = case.ranked_entity_ids
        relevant = case.relevant_entity_ids
        hits = sum(entity_id in relevant for entity_id in ranked)
        precision_total += hits / max(1,len(ranked))
        recall_total += hits / max(1,len(relevant))
        discounted_gain = sum(
            1 / math.log2(rank + 2)
            for rank,entity_id in enumerate(ranked) if entity_id in relevant
        )
        ideal_gain = sum(1 / math.log2(rank + 2) for rank in range(min(len(relevant),len(ranked))))
        ndcg_total += discounted_gain / ideal_gain if ideal_gain else 0.0
        hard_negative_hits += sum(entity_id in case.hard_negative_entity_ids for entity_id in ranked)
        hard_negative_total += len(case.hard_negative_entity_ids)
    count = len(cases)
    return {
        "case_count":count,
        "precision_at_k":precision_total/count,
        "recall_at_k":recall_total/count,
        "ndcg_at_k":ndcg_total/count,
        "hard_negative_rate":hard_negative_hits/max(1,hard_negative_total),
    }


def top_k_stability(previous: AbstractSet[str],current: AbstractSet[str]) -> float:
    union = previous|current
    return len(previous&current)/len(union) if union else 1.0
