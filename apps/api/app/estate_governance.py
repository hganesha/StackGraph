from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from psycopg.types.json import Jsonb

from app.errors import APIError
from app.models import (
    AISupplyChain,
    AISupplyChainLink,
    AssumptionClaimCreateRequest,
    AssumptionClaimModel,
    AssumptionCreateRequest,
    AssumptionList,
    AssumptionModel,
    ContradictionClaim,
    ContradictionLedger,
    ContradictionLedgerItem,
    ContradictionResolveRequest,
    EntitySummary,
    EstateLineageEdgeModel,
    EstateLineageList,
    GateReason,
    PageInfo,
)


_AI_TYPES = {
    "Agent", "AgentHarness", "AIModel", "Prompt", "InstructionSet", "ContextSource", "Tool", "Dataset",
}
_AI_PREDICATES = {"ORCHESTRATES", "INVOKES", "GROUNDED_BY", "ACCESSES", "FEEDS", "TRIGGERS", "PRODUCES"}


def _entity(row: dict[str, Any], prefix: str = "") -> EntitySummary:
    return EntitySummary(
        id=row[f"{prefix}id"], kind=row[f"{prefix}entity_type"], name=row[f"{prefix}name"],
        canonical_key=row.get(f"{prefix}canonical_key"), summary=row.get(f"{prefix}summary"),
    )


class EstateGovernanceMixin:
    database: Any

    async def create_assumption(
        self, request: AssumptionCreateRequest, *, tenant_id: UUID | None, actor_key: str,
    ) -> AssumptionModel:
        if tenant_id is None:
            raise APIError(400, "TENANT_REQUIRED", "A tenant is required to create an assumption.")
        assumption_id = uuid4()
        dependent_ids = list(dict.fromkeys(request.dependent_entity_ids))
        all_fact_ids = list(dict.fromkeys(
            fact_id for claim in request.claims
            for fact_id in claim.supporting_fact_ids + claim.opposing_fact_ids
        ))
        async with self.database.session(tenant_id) as connection:
            entity_ids = [request.subject_entity_id, *dependent_ids]
            cursor = await connection.execute(
                "SELECT count(*) count FROM entity WHERE id=ANY(%s)", (entity_ids,),
            )
            row = await cursor.fetchone()
            if row is None or row["count"] != len(set(entity_ids)):
                raise APIError(
                    422, "ENTITY_OUTSIDE_TENANT",
                    "The assumption subject and dependents must resolve inside the active tenant.",
                )
            if all_fact_ids:
                cursor = await connection.execute(
                    "SELECT count(*) count FROM fact_assertion WHERE id=ANY(%s)", (all_fact_ids,),
                )
                row = await cursor.fetchone()
                if row is None or row["count"] != len(all_fact_ids):
                    raise APIError(
                        422, "EVIDENCE_OUTSIDE_TENANT",
                        "Every assumption evidence reference must resolve inside the active tenant.",
                    )
            await connection.execute(
                """
                INSERT INTO estate_assumption(
                  id,tenant_id,subject_entity_id,dimension,statement,status,authority,confidence,
                  last_verified_at,created_by
                ) VALUES (%s,%s,%s,%s,%s,'OPEN',%s,%s,%s,%s)
                """,
                (
                    assumption_id, tenant_id, request.subject_entity_id, request.dimension,
                    request.statement, request.authority, request.confidence,
                    request.last_verified_at, actor_key,
                ),
            )
            for entity_id in dependent_ids:
                await connection.execute(
                    "INSERT INTO estate_assumption_dependent(tenant_id,assumption_id,entity_id) VALUES (%s,%s,%s)",
                    (tenant_id, assumption_id, entity_id),
                )
            claim_ids: list[UUID] = []
            for claim in request.claims:
                claim_id = uuid4()
                claim_ids.append(claim_id)
                await connection.execute(
                    """
                    INSERT INTO estate_assumption_claim(
                      id,tenant_id,assumption_id,claim_key,display_value,source_key,
                      assertion_class,confidence,observed_at
                    ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    """,
                    (
                        claim_id, tenant_id, assumption_id, claim.claim_key, claim.display_value,
                        claim.source_key, claim.assertion_class, claim.confidence, claim.observed_at,
                    ),
                )
                for polarity, fact_ids in (
                    ("SUPPORTING", claim.supporting_fact_ids), ("OPPOSING", claim.opposing_fact_ids),
                ):
                    for fact_id in fact_ids:
                        await connection.execute(
                            """
                            INSERT INTO estate_assumption_claim_evidence(
                              tenant_id,claim_id,fact_assertion_id,polarity
                            ) VALUES (%s,%s,%s,%s)
                            """,
                            (tenant_id, claim_id, fact_id, polarity),
                        )
            if len({claim.display_value for claim in request.claims}) >= 2:
                contradiction_id = uuid4()
                await connection.execute(
                    """
                    INSERT INTO estate_contradiction(
                      id,tenant_id,assumption_id,subject_entity_id,dimension,status,severity,created_by
                    ) VALUES (%s,%s,%s,%s,%s,'OPEN','HIGH',%s)
                    """,
                    (
                        contradiction_id, tenant_id, assumption_id, request.subject_entity_id,
                        request.dimension, actor_key,
                    ),
                )
                for claim_id in claim_ids:
                    await connection.execute(
                        "INSERT INTO estate_contradiction_claim(tenant_id,contradiction_id,claim_id) VALUES (%s,%s,%s)",
                        (tenant_id, contradiction_id, claim_id),
                    )
        return await self.assumption(assumption_id, tenant_id=tenant_id)

    async def assumption(self, assumption_id: UUID, *, tenant_id: UUID | None) -> AssumptionModel:
        if tenant_id is None:
            raise APIError(400, "TENANT_REQUIRED", "A tenant is required.")
        row = await self.database.fetch_one(
            """
            SELECT assumption.*,subject.entity_type,subject.name,subject.canonical_key,
                   subject.properties->>'curated_description' summary
            FROM estate_assumption assumption
            JOIN entity subject ON subject.id=assumption.subject_entity_id
            WHERE assumption.id=%s
            """,
            (assumption_id,), tenant_id=tenant_id,
        )
        if row is None:
            raise APIError(404, "ASSUMPTION_NOT_FOUND", "The assumption was not found.")
        claims = await self.database.fetch_all(
            """
            SELECT claim.*,
              coalesce(array_agg(evidence.fact_assertion_id) FILTER (WHERE evidence.polarity='SUPPORTING'),'{}') supporting_fact_ids,
              coalesce(array_agg(evidence.fact_assertion_id) FILTER (WHERE evidence.polarity='OPPOSING'),'{}') opposing_fact_ids
            FROM estate_assumption_claim claim
            LEFT JOIN estate_assumption_claim_evidence evidence ON evidence.claim_id=claim.id
            WHERE claim.assumption_id=%s GROUP BY claim.id ORDER BY claim.created_at,claim.id
            """,
            (assumption_id,), tenant_id=tenant_id,
        )
        dependents = await self.database.fetch_all(
            "SELECT entity_id FROM estate_assumption_dependent WHERE assumption_id=%s ORDER BY entity_id",
            (assumption_id,), tenant_id=tenant_id,
        )
        contradictions = await self.database.fetch_all(
            "SELECT id FROM estate_contradiction WHERE assumption_id=%s ORDER BY id",
            (assumption_id,), tenant_id=tenant_id,
        )
        return AssumptionModel(
            id=row["id"], subject=EntitySummary(
                id=row["subject_entity_id"], kind=row["entity_type"], name=row["name"],
                canonical_key=row["canonical_key"], summary=row["summary"],
            ),
            dimension=row["dimension"], statement=row["statement"], status=row["status"],
            authority=row["authority"], confidence=float(row["confidence"]),
            last_verified_at=row["last_verified_at"], version=row["version"],
            claims=[AssumptionClaimModel(
                id=claim["id"], claim_key=claim["claim_key"], display_value=claim["display_value"],
                source_key=claim["source_key"], assertion_class=claim["assertion_class"],
                confidence=float(claim["confidence"]), observed_at=claim["observed_at"],
                supporting_fact_ids=claim["supporting_fact_ids"],
                opposing_fact_ids=claim["opposing_fact_ids"],
            ) for claim in claims],
            dependent_entity_ids=[item["entity_id"] for item in dependents],
            contradiction_ids=[item["id"] for item in contradictions],
            created_at=row["created_at"], updated_at=row["updated_at"],
        )

    async def assumptions(
        self, *, tenant_id: UUID | None, subject_id: UUID | None, status: str | None, limit: int,
    ) -> AssumptionList:
        if tenant_id is None:
            raise APIError(400, "TENANT_REQUIRED", "A tenant is required.")
        rows = await self.database.fetch_all(
            """
            SELECT id FROM estate_assumption
            WHERE (%s::uuid IS NULL OR subject_entity_id=%s)
              AND (%s::text IS NULL OR status=%s)
            ORDER BY updated_at DESC,id DESC LIMIT %s
            """,
            (subject_id, subject_id, status, status, limit + 1), tenant_id=tenant_id,
        )
        items = [await self.assumption(row["id"], tenant_id=tenant_id) for row in rows[:limit]]
        return AssumptionList(
            assumptions=items,
            page_info=PageInfo(has_next_page=len(rows) > limit, next_cursor=None),
        )

    async def resolve_contradiction(
        self, contradiction_id: UUID, request: ContradictionResolveRequest, *,
        tenant_id: UUID | None, actor_key: str,
    ) -> None:
        if tenant_id is None:
            raise APIError(400, "TENANT_REQUIRED", "A tenant is required.")
        now = datetime.now(UTC)
        async with self.database.session(tenant_id) as connection:
            cursor = await connection.execute(
                "SELECT status,version FROM estate_contradiction WHERE id=%s FOR UPDATE",
                (contradiction_id,),
            )
            row = await cursor.fetchone()
            if row is None:
                raise APIError(404, "CONTRADICTION_NOT_FOUND", "The contradiction was not found.")
            if row["status"] != "OPEN":
                raise APIError(409, "CONTRADICTION_TERMINAL", "The contradiction is already resolved.")
            if row["version"] != request.expected_version:
                raise APIError(409, "VERSION_CONFLICT", "The contradiction changed; reload before resolving.")
            await connection.execute(
                """
                UPDATE estate_contradiction SET status=%s,resolution=%s,resolved_by=%s,
                  resolved_at=%s,version=version+1,updated_at=%s WHERE id=%s
                """,
                (request.status, request.rationale, actor_key, now, now, contradiction_id),
            )
            await connection.execute(
                """
                INSERT INTO estate_contradiction_resolution(
                  tenant_id,contradiction_id,from_status,to_status,rationale,actor_key
                ) VALUES (%s,%s,'OPEN',%s,%s,%s)
                """,
                (tenant_id, contradiction_id, request.status, request.rationale, actor_key),
            )

    async def contradiction_ledger(
        self, *, tenant_id: UUID | None, subject_id: UUID | None, limit: int,
    ) -> ContradictionLedger:
        if tenant_id is None:
            raise APIError(400, "TENANT_REQUIRED", "A tenant is required.")
        rows = await self.database.fetch_all(
            """
            SELECT contradiction.id,contradiction.dimension,contradiction.status,
                   contradiction.version,
                   contradiction.subject_entity_id,contradiction.updated_at,
                   subject.entity_type,subject.name,subject.canonical_key,
                   subject.properties->>'curated_description' summary,
                   coalesce(array_agg(dependent.entity_id) FILTER (WHERE dependent.entity_id IS NOT NULL),'{}') dependent_ids
            FROM estate_contradiction contradiction
            JOIN entity subject ON subject.id=contradiction.subject_entity_id
            LEFT JOIN estate_assumption_dependent dependent ON dependent.assumption_id=contradiction.assumption_id
            WHERE contradiction.status='OPEN' AND (%s::uuid IS NULL OR contradiction.subject_entity_id=%s)
            GROUP BY contradiction.id,subject.id
            ORDER BY contradiction.updated_at DESC,contradiction.id DESC LIMIT %s
            """,
            (subject_id, subject_id, limit + 1), tenant_id=tenant_id,
        )
        if not rows:
            return await super().contradiction_ledger(  # type: ignore[misc]
                tenant_id=tenant_id, subject_id=subject_id, limit=limit,
            )
        items: list[ContradictionLedgerItem] = []
        for row in rows[:limit]:
            claims = await self.database.fetch_all(
                """
                SELECT claim.*,
                  coalesce(array_agg(evidence.fact_assertion_id) FILTER (WHERE evidence.fact_assertion_id IS NOT NULL),'{}') evidence_ids
                FROM estate_contradiction_claim link
                JOIN estate_assumption_claim claim ON claim.id=link.claim_id
                LEFT JOIN estate_assumption_claim_evidence evidence ON evidence.claim_id=claim.id
                WHERE link.contradiction_id=%s GROUP BY claim.id ORDER BY claim.created_at,claim.id
                """,
                (row["id"],), tenant_id=tenant_id,
            )
            items.append(ContradictionLedgerItem(
                id=str(row["id"]), subject=EntitySummary(
                    id=row["subject_entity_id"], kind=row["entity_type"], name=row["name"],
                    canonical_key=row["canonical_key"], summary=row["summary"],
                ), predicate=row["dimension"], claims=[ContradictionClaim(
                    claim_key=claim["claim_key"], display_value=claim["display_value"],
                    source_key=claim["source_key"], assertion_class=claim["assertion_class"],
                    confidence=float(claim["confidence"]), observed_at=claim["observed_at"],
                    evidence_fact_ids=claim["evidence_ids"],
                ) for claim in claims], affected_entity_count=len(row["dependent_ids"]),
                last_verified_at=row["updated_at"], version=row["version"],
            ))
        return ContradictionLedger(
            as_of=datetime.now(UTC), method_version="assumption-registry/1.0.0",
            contradictions=items,
            page_info=PageInfo(has_next_page=len(rows) > limit, next_cursor=None),
        )

    async def estate_lineage(
        self, *, tenant_id: UUID | None, entity_id: UUID | None, limit: int,
    ) -> EstateLineageList:
        if tenant_id is None:
            raise APIError(400, "TENANT_REQUIRED", "A tenant is required.")
        rows = await self.database.fetch_all(
            """
            SELECT lineage.*,upstream.entity_type upstream_entity_type,upstream.name upstream_name,
                   upstream.canonical_key upstream_canonical_key,
                   upstream.properties->>'curated_description' upstream_summary,
                   downstream.entity_type downstream_entity_type,downstream.name downstream_name,
                   downstream.canonical_key downstream_canonical_key,
                   downstream.properties->>'curated_description' downstream_summary
            FROM estate_lineage_edge lineage
            JOIN entity upstream ON upstream.id=lineage.upstream_entity_id
            JOIN entity downstream ON downstream.id=lineage.downstream_entity_id
            WHERE lineage.valid_to IS NULL AND (%s::uuid IS NULL OR %s=ANY(ARRAY[lineage.upstream_entity_id,lineage.downstream_entity_id]))
            ORDER BY lineage.observed_at DESC,lineage.id DESC LIMIT %s
            """,
            (entity_id, entity_id, limit + 1), tenant_id=tenant_id,
        )
        edges = [EstateLineageEdgeModel(
            id=row["id"], upstream=EntitySummary(
                id=row["upstream_entity_id"], kind=row["upstream_entity_type"],
                name=row["upstream_name"], canonical_key=row["upstream_canonical_key"],
                summary=row["upstream_summary"],
            ), downstream=EntitySummary(
                id=row["downstream_entity_id"], kind=row["downstream_entity_type"],
                name=row["downstream_name"], canonical_key=row["downstream_canonical_key"],
                summary=row["downstream_summary"],
            ), lineage_kind=row["lineage_kind"], confidence=float(row["confidence"]),
            evidence_fact_id=row["fact_assertion_id"], observed_at=row["observed_at"],
        ) for row in rows[:limit]]
        limitations = [] if edges else [GateReason(
            code="LINEAGE_NOT_COLLECTED",
            message="No normalized data-lineage evidence has been collected for this scope.",
        )]
        return EstateLineageList(
            edges=edges, page_info=PageInfo(has_next_page=len(rows) > limit, next_cursor=None),
            limitations=limitations,
        )

    async def ai_supply_chain(self, *, tenant_id: UUID | None) -> AISupplyChain:
        if tenant_id is None:
            raise APIError(400, "TENANT_REQUIRED", "A tenant is required.")
        rows = await self.database.fetch_all(
            """
            SELECT fact.predicate,fact.confidence,subject.id subject_entity_id,
                   object.id object_entity_id,
                   subject.entity_type subject_entity_type,subject.name subject_name,
                   subject.canonical_key subject_canonical_key,
                   object.entity_type object_entity_type,object.name object_name,
                   object.canonical_key object_canonical_key,
                   array_agg(DISTINCT fact.id) evidence_fact_ids
            FROM fact_assertion fact
            JOIN entity subject ON subject.id=fact.subject_entity_id
            JOIN entity object ON object.id=fact.object_entity_id
            WHERE fact.system_to IS NULL AND fact.predicate=ANY(%s)
              AND (subject.entity_type=ANY(%s) OR object.entity_type=ANY(%s)
                   OR subject.entity_type='Application' OR object.entity_type='BusinessCapability')
            GROUP BY fact.predicate,fact.confidence,subject.id,object.id
            ORDER BY subject.name,fact.predicate,object.name
            """,
            (list(_AI_PREDICATES), list(_AI_TYPES), list(_AI_TYPES)), tenant_id=tenant_id,
        )
        links = [AISupplyChainLink(
            predicate=row["predicate"], subject=EntitySummary(
                id=row["subject_entity_id"], kind=row["subject_entity_type"],
                name=row["subject_name"], canonical_key=row["subject_canonical_key"],
            ), object=EntitySummary(
                id=row["object_entity_id"], kind=row["object_entity_type"],
                name=row["object_name"], canonical_key=row["object_canonical_key"],
            ), confidence=float(row["confidence"]), evidence_fact_ids=row["evidence_fact_ids"],
        ) for row in rows]
        entities = {item.subject.id: item.subject for item in links}
        entities.update({item.object.id: item.object for item in links})
        observed_types = {item.kind for item in entities.values()}
        expected_types = {"Application", *_AI_TYPES, "BusinessCapability"}
        coverage = len(observed_types & expected_types) / len(expected_types)
        status = "AVAILABLE" if coverage == 1 else "PARTIAL" if links else "NOT_COLLECTED"
        if status == "AVAILABLE":
            limitations = []
        elif links:
            limitations = [GateReason(
                code="AI_SUPPLY_CHAIN_INCOMPLETE",
                message="AI supply-chain coverage is incomplete; missing nodes are not inferred.",
            )]
        else:
            # An empty result here means nothing has been collected, not that the estate runs no
            # AI. The vocabulary is registered in the ontology; no connector emits it yet, and
            # saying which of those two is true is the whole difference for a reader.
            limitations = [GateReason(
                code="AI_SUPPLY_CHAIN_NOT_COLLECTED",
                message=(
                    "No connector currently emits agent, model, prompt, tool, or dataset "
                    "evidence. The AI supply chain is uncollected rather than empty."
                ),
            )]
        return AISupplyChain(
            as_of=datetime.now(UTC), status=status, entities=list(entities.values()), links=links,
            coverage_ratio=coverage, limitations=limitations,
        )
