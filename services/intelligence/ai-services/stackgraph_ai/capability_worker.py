from __future__ import annotations

import argparse
import asyncio
import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import unquote
from uuid import UUID

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from stackgraph_ai.bootstrap import AISettings, build_ai_service
from stackgraph_ai.capabilities import (
    ANALYZER_KEY,
    ANALYZER_VERSION,
    CapabilityTaxonomy,
    InferenceProposal,
    LocalCapabilityCatalog,
    PackageUsage,
    PersistedInference,
    curated_inferences,
    duplicate_capability_candidates,
    infer_with_ai,
)
from stackgraph_ai.database import PostgresDatabase
from stackgraph_ai.sync_capabilities import sync_capabilities


@dataclass(frozen=True, slots=True)
class AnalysisResult:
    taxonomy: str
    repository_id: str
    source_revision: str | None
    completeness: str | None
    usages_considered: int
    curated_inferences: int
    ai_inferences: int
    duplicate_candidates: int
    replayed_inferences: int


async def analyze_repository(
    database_url: str,
    *,
    tenant_id: UUID,
    repository_id: UUID,
    catalog_dir: Path,
    taxonomy_key: str = "stackgraph.technical-capabilities",
    use_ai_for_unmapped: bool = False,
    ai_route: str = "default",
) -> AnalysisResult:
    sync_capabilities(
        database_url,
        catalog_dir,
        tenant_id=None,
        actor_key="capability-worker",
    )
    taxonomies = LocalCapabilityCatalog(catalog_dir).definitions()
    taxonomy = next(
        (
            item for item in taxonomies
            if item.key == taxonomy_key and item.status == "ACTIVE"
        ),
        None,
    )
    if taxonomy is None:
        raise ValueError(f"no active local taxonomy: {taxonomy_key}")
    with psycopg.connect(database_url, row_factory=dict_row) as connection:
        taxonomy_id, capability_ids = _taxonomy_ids(
            connection, tenant_id, taxonomy,
        )
        source_revision, completeness = _latest_revision(
            connection, tenant_id, repository_id,
        )
        usages = _load_usages(
            connection, tenant_id, repository_id, source_revision,
        )

    proposals: list[InferenceProposal] = []
    unmapped: list[PackageUsage] = []
    for usage in usages:
        curated = curated_inferences(taxonomy, usage)
        proposals.extend(curated)
        if usage.active and not curated:
            unmapped.append(usage)

    curated_count = len(proposals)
    ai_count = 0
    if use_ai_for_unmapped and unmapped:
        database = PostgresDatabase(database_url)
        ai = build_ai_service(AISettings.from_env(), database=database)
        for usage in unmapped:
            proposals.append(await infer_with_ai(
                ai,
                taxonomy,
                usage,
                tenant_id=tenant_id,
                route=ai_route,
            ))
            ai_count += 1

    with psycopg.connect(database_url, row_factory=dict_row) as connection:
        persisted, replayed = _persist_inferences(
            connection,
            tenant_id=tenant_id,
            taxonomy_id=taxonomy_id,
            capability_ids=capability_ids,
            proposals=tuple(proposals),
        )
        duplicates = (
            duplicate_capability_candidates(tuple(persisted))
            if completeness == "COMPLETE" else ()
        )
        duplicate_count = _persist_duplicates(
            connection,
            tenant_id=tenant_id,
            capability_ids=capability_ids,
            proposals=duplicates,
        )
        if source_revision and completeness == "COMPLETE":
            connection.execute(
                """
                UPDATE capability_inference SET stale_at=coalesce(stale_at,now()),updated_at=now()
                WHERE tenant_id=%s AND repository_entity_id=%s
                  AND source_revision<>%s AND stale_at IS NULL
                """,
                (tenant_id, repository_id, source_revision),
            )
            connection.execute(
                """
                UPDATE duplicate_capability_candidate
                SET stale_at=coalesce(stale_at,now()),updated_at=now()
                WHERE tenant_id=%s AND repository_entity_id=%s
                  AND source_revision<>%s AND stale_at IS NULL
                """,
                (tenant_id, repository_id, source_revision),
            )
    return AnalysisResult(
        taxonomy=f"{taxonomy.key}@{taxonomy.version}",
        repository_id=str(repository_id),
        source_revision=source_revision,
        completeness=completeness,
        usages_considered=len(usages),
        curated_inferences=curated_count,
        ai_inferences=ai_count,
        duplicate_candidates=duplicate_count,
        replayed_inferences=replayed,
    )


def _taxonomy_ids(
    connection: psycopg.Connection,
    tenant_id: UUID,
    taxonomy: CapabilityTaxonomy,
) -> tuple[UUID, dict[str, UUID]]:
    row = connection.execute(
        """
        SELECT id FROM capability_taxonomy_version
        WHERE taxonomy_key=%s AND version=%s AND status='ACTIVE'
          AND (tenant_id=%s OR tenant_id IS NULL)
        ORDER BY (tenant_id IS NOT NULL) DESC LIMIT 1
        """,
        (taxonomy.key, taxonomy.version, tenant_id),
    ).fetchone()
    if row is None:
        raise ValueError("active capability taxonomy was not synchronized")
    definitions = connection.execute(
        """
        SELECT id,capability_key FROM capability_definition
        WHERE taxonomy_version_id=%s
        """,
        (row["id"],),
    ).fetchall()
    return row["id"], {item["capability_key"]: item["id"] for item in definitions}


def _load_usages(
    connection: psycopg.Connection,
    tenant_id: UUID,
    repository_id: UUID,
    source_revision: str | None,
) -> tuple[PackageUsage, ...]:
    if source_revision is None:
        return ()
    rows = connection.execute(
        """
        SELECT f.id fact_id,f.source_revision,f.properties,f.object_entity_id,
               dependency.canonical_key subject_key,repository.canonical_key repository_key,
               usage.referenced,usage.runtime_observed,usage.referenced_symbols
        FROM current_fact f
        JOIN entity repository ON repository.id=f.subject_entity_id
        JOIN entity dependency ON dependency.id=f.object_entity_id
        JOIN dependency_usage_summary usage ON usage.dependency_fact_assertion_id=f.id
        WHERE f.tenant_id=%s AND f.subject_entity_id=%s AND f.predicate='DEPENDS_ON'
          AND f.source_revision=%s
        ORDER BY f.source_revision,dependency.canonical_key,f.id
        """,
        (tenant_id, repository_id, source_revision),
    ).fetchall()
    grouped: dict[tuple[UUID, str], dict[str, Any]] = {}
    for row in rows:
        properties = row["properties"] or {}
        ecosystem = str(properties.get("ecosystem") or "")
        package_name = _package_name(row["subject_key"], ecosystem)
        key = (row["object_entity_id"], row["source_revision"])
        item = grouped.setdefault(key, {
            "repository_key": row["repository_key"],
            "subject_key": row["subject_key"],
            "ecosystem": ecosystem,
            "package_name": package_name,
            "symbols": set(),
            "facts": set(),
            "referenced": False,
            "runtime": "UNKNOWN",
        })
        item["symbols"].update(row["referenced_symbols"] or [])
        item["facts"].add(row["fact_id"])
        item["referenced"] = item["referenced"] or bool(row["referenced"])
        if row["runtime_observed"] == "OBSERVED":
            item["runtime"] = "OBSERVED"
        elif item["runtime"] == "UNKNOWN" and row["runtime_observed"] == "NOT_OBSERVED":
            item["runtime"] = "NOT_OBSERVED"
    return tuple(
        PackageUsage(
            repository_id=repository_id,
            repository_key=item["repository_key"],
            subject_entity_id=subject_id,
            subject_key=item["subject_key"],
            source_revision=revision,
            ecosystem=item["ecosystem"],
            package_name=item["package_name"],
            referenced_symbols=tuple(sorted(item["symbols"])),
            supporting_fact_ids=tuple(sorted(item["facts"], key=str)),
            referenced=item["referenced"],
            runtime_observed=item["runtime"],
        )
        for (subject_id, revision), item in sorted(
            grouped.items(), key=lambda pair: (str(pair[0][0]), pair[0][1]),
        )
    )


def _latest_revision(
    connection: psycopg.Connection,
    tenant_id: UUID,
    repository_id: UUID,
) -> tuple[str | None, str | None]:
    row = connection.execute(
        """
        SELECT snapshot.source_revision,snapshot.completeness
        FROM entity repository
        JOIN ingest_target target
          ON target.tenant_id=repository.tenant_id
         AND target.target_kind='REPOSITORY'
         AND target.target_key=repository.canonical_key
        JOIN source_snapshot snapshot ON snapshot.ingest_target_id=target.id
        WHERE repository.id=%s AND repository.tenant_id=%s
          AND snapshot.status='PUBLISHED'
        ORDER BY snapshot.observed_at DESC,snapshot.published_at DESC,snapshot.id DESC
        LIMIT 1
        """,
        (repository_id, tenant_id),
    ).fetchone()
    return (
        (row["source_revision"], row["completeness"])
        if row else (None, None)
    )


def _persist_inferences(
    connection: psycopg.Connection,
    *,
    tenant_id: UUID,
    taxonomy_id: UUID,
    capability_ids: Mapping[str, UUID],
    proposals: tuple[InferenceProposal, ...],
) -> tuple[list[PersistedInference], int]:
    persisted: list[PersistedInference] = []
    replayed = 0
    for proposal in proposals:
        row = connection.execute(
            """
            INSERT INTO capability_inference(
              tenant_id,repository_entity_id,subject_entity_id,capability_definition_id,
              source_revision,assertion_class,confidence,confidence_band,
              supporting_fact_ids,counter_evidence_fact_ids,taxonomy_version_id,
              analyzer_key,analyzer_version,model_invocation_id,model_provider,model_name,
              policy_version,input_fingerprint,analysis_fingerprint,rationale
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT(tenant_id,analysis_fingerprint) DO NOTHING RETURNING id
            """,
            (
                tenant_id, proposal.usage.repository_id,
                proposal.usage.subject_entity_id, capability_ids[proposal.capability_key],
                proposal.usage.source_revision, proposal.assertion_class,
                proposal.confidence, proposal.confidence_band,
                list(proposal.supporting_fact_ids), list(proposal.counter_evidence_fact_ids),
                taxonomy_id, ANALYZER_KEY, ANALYZER_VERSION,
                proposal.model_invocation_id, proposal.model_provider, proposal.model_name,
                proposal.policy_version, proposal.input_fingerprint,
                proposal.analysis_fingerprint, proposal.rationale,
            ),
        ).fetchone()
        if row is None:
            row = connection.execute(
                """
                SELECT id FROM capability_inference
                WHERE tenant_id=%s AND analysis_fingerprint=%s
                """,
                (tenant_id, proposal.analysis_fingerprint),
            ).fetchone()
            replayed += 1
        persisted.append(PersistedInference(row["id"], proposal))
    return persisted, replayed


def _persist_duplicates(
    connection: psycopg.Connection,
    *,
    tenant_id: UUID,
    capability_ids: Mapping[str, UUID],
    proposals: tuple,
) -> int:
    inserted = 0
    for proposal in proposals:
        row = connection.execute(
            """
            INSERT INTO duplicate_capability_candidate(
              tenant_id,repository_entity_id,capability_definition_id,source_revision,
              dependency_entity_ids,capability_inference_ids,supporting_fact_ids,
              confidence,analysis_fingerprint,summary,limitations
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT(tenant_id,analysis_fingerprint) DO NOTHING RETURNING id
            """,
            (
                tenant_id, proposal.repository_id,
                capability_ids[proposal.capability_key], proposal.source_revision,
                list(proposal.dependency_entity_ids),
                list(proposal.capability_inference_ids),
                list(proposal.supporting_fact_ids), proposal.confidence,
                proposal.analysis_fingerprint, proposal.summary,
                Jsonb(list(proposal.limitations)),
            ),
        ).fetchone()
        inserted += int(row is not None)
    return inserted


def _package_name(canonical_key: str, ecosystem: str) -> str:
    marker = f"pkg:{ecosystem}/"
    if marker not in canonical_key:
        raise ValueError(f"dependency entity is not a {ecosystem} purl")
    value = canonical_key.split(marker, 1)[1].rsplit("@", 1)[0]
    return unquote(value)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Analyze repository dependency capabilities")
    parser.add_argument("--tenant-id", type=UUID, required=True)
    parser.add_argument("--repository-id", type=UUID, required=True)
    parser.add_argument("--catalog-dir", type=Path, required=True)
    parser.add_argument("--taxonomy-key", default="stackgraph.technical-capabilities")
    parser.add_argument("--ai-unmapped", action="store_true")
    parser.add_argument("--ai-route", default="default")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    database_url = os.getenv("STACKGRAPH_DATABASE_URL")
    if not database_url:
        raise SystemExit("STACKGRAPH_DATABASE_URL is required")
    result = asyncio.run(analyze_repository(
        database_url,
        tenant_id=args.tenant_id,
        repository_id=args.repository_id,
        catalog_dir=args.catalog_dir,
        taxonomy_key=args.taxonomy_key,
        use_ai_for_unmapped=args.ai_unmapped,
        ai_route=args.ai_route,
    ))
    print(json.dumps(asdict(result), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
