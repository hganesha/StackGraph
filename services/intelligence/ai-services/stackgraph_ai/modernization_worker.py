from __future__ import annotations

import argparse
import asyncio
import json
import os
import socket
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Mapping
from uuid import UUID

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from stackgraph_ai.capability_worker import analyze_repository
from stackgraph_ai.modernization import (
    ANALYZER_KEY,
    ANALYZER_VERSION,
    AlternativeCatalog,
    DependencyUsage,
    DuplicateInput,
    ModernizationAnalysis,
    analyze_duplicate,
)


@dataclass(frozen=True, slots=True)
class ModernizationResult:
    repository_id: str
    source_revision: str
    candidates: int
    recommendations: int
    replayed_candidates: int
    replayed_recommendations: int


@dataclass(frozen=True, slots=True)
class WorkResult:
    claimed: int
    succeeded: int
    retried: int
    failed: int


def analyze_modernization(
    database_url: str,
    *,
    tenant_id: UUID,
    repository_id: UUID,
    source_revision: str,
    alternatives_path: Path,
) -> ModernizationResult:
    catalog = AlternativeCatalog.load(alternatives_path)
    with psycopg.connect(database_url, row_factory=dict_row) as connection:
        duplicates = _load_duplicates(
            connection,
            tenant_id=tenant_id,
            repository_id=repository_id,
            source_revision=source_revision,
        )
        analyses = tuple(analyze_duplicate(item, catalog) for item in duplicates)
        candidate_count = 0
        recommendation_count = 0
        replayed_candidates = 0
        replayed_recommendations = 0
        for analysis in analyses:
            candidate_id, candidate_created = _persist_candidate(connection, tenant_id, analysis)
            option_ids = _persist_options(connection, tenant_id, candidate_id, analysis)
            recommendation_created = _persist_recommendation(
                connection,
                tenant_id,
                candidate_id,
                option_ids,
                analysis,
            )
            candidate_count += int(candidate_created)
            recommendation_count += int(recommendation_created)
            replayed_candidates += int(not candidate_created)
            replayed_recommendations += int(not recommendation_created)
        connection.execute(
            """
            UPDATE modernization_candidate
            SET stale_at=coalesce(stale_at,now()),updated_at=now()
            WHERE tenant_id=%s AND repository_entity_id=%s
              AND source_revision<>%s AND stale_at IS NULL
            """,
            (tenant_id, repository_id, source_revision),
        )
        connection.execute(
            """
            UPDATE modernization_recommendation
            SET stale_at=coalesce(stale_at,now()),updated_at=now()
            WHERE tenant_id=%s AND repository_entity_id=%s
              AND source_revision<>%s AND stale_at IS NULL
            """,
            (tenant_id, repository_id, source_revision),
        )
    return ModernizationResult(
        repository_id=str(repository_id),
        source_revision=source_revision,
        candidates=candidate_count,
        recommendations=recommendation_count,
        replayed_candidates=replayed_candidates,
        replayed_recommendations=replayed_recommendations,
    )


async def run_repository_intelligence(
    database_url: str,
    *,
    tenant_id: UUID,
    repository_id: UUID,
    capability_catalog_dir: Path,
    alternatives_path: Path,
    use_ai_for_unmapped: bool = False,
    ai_route: str = "default",
) -> tuple[Mapping[str, Any], ModernizationResult | None]:
    capabilities = await analyze_repository(
        database_url,
        tenant_id=tenant_id,
        repository_id=repository_id,
        catalog_dir=capability_catalog_dir,
        use_ai_for_unmapped=use_ai_for_unmapped,
        ai_route=ai_route,
    )
    modernization = None
    if capabilities.source_revision and capabilities.completeness == "COMPLETE":
        modernization = analyze_modernization(
            database_url,
            tenant_id=tenant_id,
            repository_id=repository_id,
            source_revision=capabilities.source_revision,
            alternatives_path=alternatives_path,
        )
    return asdict(capabilities), modernization


def work_jobs(
    database_url: str,
    *,
    capability_catalog_dir: Path,
    alternatives_path: Path,
    worker_id: str,
    max_jobs: int = 1,
    use_ai_for_unmapped: bool = False,
    ai_route: str = "default",
) -> WorkResult:
    claimed = succeeded = retried = failed = 0
    for _ in range(max_jobs):
        job = _claim_job(database_url, worker_id)
        if job is None:
            break
        claimed += 1
        try:
            asyncio.run(run_repository_intelligence(
                database_url,
                tenant_id=job["tenant_id"],
                repository_id=job["repository_entity_id"],
                capability_catalog_dir=capability_catalog_dir,
                alternatives_path=alternatives_path,
                use_ai_for_unmapped=use_ai_for_unmapped,
                ai_route=ai_route,
            ))
        except Exception as error:
            terminal = _fail_job(database_url, job, error)
            failed += int(terminal)
            retried += int(not terminal)
        else:
            _complete_job(database_url, job["id"])
            succeeded += 1
    return WorkResult(claimed=claimed, succeeded=succeeded, retried=retried, failed=failed)


def _load_duplicates(
    connection: psycopg.Connection,
    *,
    tenant_id: UUID,
    repository_id: UUID,
    source_revision: str,
) -> tuple[DuplicateInput, ...]:
    rows = connection.execute(
        """
        SELECT candidate.*,capability.capability_key,capability.name capability_name
        FROM duplicate_capability_candidate candidate
        JOIN capability_definition capability ON capability.id=candidate.capability_definition_id
        WHERE candidate.tenant_id=%s AND candidate.repository_entity_id=%s
          AND candidate.source_revision=%s AND candidate.stale_at IS NULL
          AND candidate.review_state<>'REJECTED'
        ORDER BY capability.capability_key,candidate.id
        """,
        (tenant_id, repository_id, source_revision),
    ).fetchall()
    values: list[DuplicateInput] = []
    for row in rows:
        inferences = connection.execute(
            """
            SELECT inference.*,entity.canonical_key,entity.name
            FROM capability_inference inference
            JOIN entity ON entity.id=inference.subject_entity_id
            WHERE inference.id=ANY(%s::uuid[]) AND inference.stale_at IS NULL
              AND inference.review_state<>'REJECTED'
            ORDER BY entity.canonical_key,inference.id
            """,
            (list(row["capability_inference_ids"]),),
        ).fetchall()
        usages: list[DependencyUsage] = []
        for inference in inferences:
            fact_ids = list(inference["supporting_fact_ids"])
            usage_rows = connection.execute(
                """
                SELECT usage.*,fact.id fact_id
                FROM dependency_usage_summary usage
                JOIN fact_assertion fact ON fact.id=usage.dependency_fact_assertion_id
                WHERE fact.id=ANY(%s::uuid[])
                ORDER BY fact.id
                """,
                (fact_ids,),
            ).fetchall()
            evidence_rows = connection.execute(
                """
                SELECT locator FROM evidence
                WHERE fact_assertion_id=ANY(%s::uuid[])
                ORDER BY fact_assertion_id,id
                """,
                (fact_ids,),
            ).fetchall()
            usages.append(DependencyUsage(
                entity_id=inference["subject_entity_id"],
                canonical_key=inference["canonical_key"],
                name=inference["name"],
                inference_id=inference["id"],
                supporting_fact_ids=tuple(fact_ids),
                confidence=float(inference["confidence"]),
                reference_count=sum(int(item["reference_count"]) for item in usage_rows),
                referenced_symbols=tuple(sorted({
                    str(symbol)
                    for item in usage_rows
                    for symbol in (item["referenced_symbols"] or [])
                })),
                source_locations=tuple(dict(item["locator"]) for item in evidence_rows),
                runtime_observed=(
                    "OBSERVED" if any(item["runtime_observed"] == "OBSERVED" for item in usage_rows)
                    else "NOT_OBSERVED" if usage_rows and all(item["runtime_observed"] == "NOT_OBSERVED" for item in usage_rows)
                    else "UNKNOWN"
                ),
                limitations=tuple(sorted({
                    str(value)
                    for item in usage_rows
                    for value in (item["limitations"] or [])
                })),
            ))
        if len({item.entity_id for item in usages}) >= 2:
            values.append(DuplicateInput(
                id=row["id"],
                repository_id=row["repository_entity_id"],
                source_revision=row["source_revision"],
                capability_definition_id=row["capability_definition_id"],
                capability_key=row["capability_key"],
                capability_name=row["capability_name"],
                confidence=float(row["confidence"]),
                dependencies=tuple(usages),
            ))
    return tuple(values)


def _persist_candidate(
    connection: psycopg.Connection,
    tenant_id: UUID,
    analysis: ModernizationAnalysis,
) -> tuple[UUID, bool]:
    row = connection.execute(
        """
        INSERT INTO modernization_candidate(
          tenant_id,repository_entity_id,source_revision,duplicate_capability_candidate_id,
          capability_definition_id,candidate_kind,subject_entity_ids,confidence,summary,
          supporting_fact_ids,source_locations,validation_gaps,analyzer_key,analyzer_version,
          input_fingerprint,analysis_fingerprint
        ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        ON CONFLICT(tenant_id,analysis_fingerprint) DO NOTHING RETURNING id
        """,
        (
            tenant_id, analysis.repository_id, analysis.source_revision,
            analysis.duplicate_candidate_id, analysis.capability_definition_id,
            analysis.candidate_kind, list(analysis.subject_entity_ids), analysis.confidence,
            analysis.summary, list(analysis.supporting_fact_ids),
            Jsonb(list(analysis.source_locations)), Jsonb(list(analysis.validation_gaps)),
            ANALYZER_KEY, ANALYZER_VERSION, analysis.input_fingerprint,
            analysis.analysis_fingerprint,
        ),
    ).fetchone()
    if row:
        return row["id"], True
    existing = connection.execute(
        "SELECT id FROM modernization_candidate WHERE tenant_id=%s AND analysis_fingerprint=%s",
        (tenant_id, analysis.analysis_fingerprint),
    ).fetchone()
    assert existing is not None
    return existing["id"], False


def _persist_options(
    connection: psycopg.Connection,
    tenant_id: UUID,
    candidate_id: UUID,
    analysis: ModernizationAnalysis,
) -> dict[str, UUID]:
    values: dict[str, UUID] = {}
    for rank, option in enumerate(analysis.options, 1):
        row = connection.execute(
            """
            INSERT INTO modernization_option(
              tenant_id,modernization_candidate_id,option_kind,canonical_key,name,
              target_entity_id,compatibility,rank,score,score_components,rationale,
              tradeoffs,disqualifiers,validation_gaps,supporting_fact_ids
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT(modernization_candidate_id,canonical_key)
            DO UPDATE SET rank=EXCLUDED.rank,score=EXCLUDED.score,
              score_components=EXCLUDED.score_components,rationale=EXCLUDED.rationale,
              tradeoffs=EXCLUDED.tradeoffs,disqualifiers=EXCLUDED.disqualifiers,
              validation_gaps=EXCLUDED.validation_gaps
            RETURNING id
            """,
            (
                tenant_id, candidate_id, option.kind, option.canonical_key, option.name,
                option.target_entity_id, option.compatibility, rank, option.score,
                Jsonb(dict(option.score_components)), option.rationale,
                Jsonb(list(option.tradeoffs)), Jsonb(list(option.disqualifiers)),
                Jsonb(list(option.validation_gaps)), list(option.supporting_fact_ids),
            ),
        ).fetchone()
        values[option.canonical_key] = row["id"]
    return values


def _persist_recommendation(
    connection: psycopg.Connection,
    tenant_id: UUID,
    candidate_id: UUID,
    option_ids: Mapping[str, UUID],
    analysis: ModernizationAnalysis,
) -> bool:
    recommendation = analysis.recommendation
    row = connection.execute(
        """
        INSERT INTO modernization_recommendation(
          tenant_id,repository_entity_id,modernization_candidate_id,selected_option_id,
          source_revision,action,objective,title,rationale,confidence,estimated_effort,
          affected_call_sites,affected_files,validation_gaps,migration_plan,rollback_plan,
          supporting_fact_ids,counter_signals,policy_version,input_fingerprint,
          analysis_fingerprint
        ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        ON CONFLICT(tenant_id,analysis_fingerprint) DO NOTHING RETURNING id
        """,
        (
            tenant_id, analysis.repository_id, candidate_id,
            option_ids[recommendation.selected_option_key], analysis.source_revision,
            recommendation.action, recommendation.objective, recommendation.title,
            recommendation.rationale, recommendation.confidence,
            recommendation.estimated_effort, recommendation.affected_call_sites,
            recommendation.affected_files, Jsonb(list(recommendation.validation_gaps)),
            Jsonb(list(recommendation.migration_plan)), Jsonb(list(recommendation.rollback_plan)),
            list(recommendation.supporting_fact_ids), Jsonb(list(recommendation.counter_signals)),
            recommendation.policy_version, recommendation.input_fingerprint,
            recommendation.analysis_fingerprint,
        ),
    ).fetchone()
    return row is not None


def _claim_job(database_url: str, worker_id: str) -> Mapping[str, Any] | None:
    with psycopg.connect(database_url, row_factory=dict_row) as connection:
        return connection.execute(
            """
            UPDATE intelligence_job SET status='RUNNING',leased_by=%s,
              leased_until=now()+interval '5 minutes',attempt=attempt+1,
              started_at=coalesce(started_at,now()),updated_at=now()
            WHERE id=(
              SELECT id FROM intelligence_job
              WHERE status='PENDING' AND available_at<=now()
                AND (leased_until IS NULL OR leased_until<now())
              ORDER BY available_at,created_at,id
              FOR UPDATE SKIP LOCKED LIMIT 1
            ) RETURNING *
            """,
            (worker_id,),
        ).fetchone()


def _complete_job(database_url: str, job_id: UUID) -> None:
    with psycopg.connect(database_url) as connection:
        connection.execute(
            """
            UPDATE intelligence_job SET status='SUCCEEDED',completed_at=now(),updated_at=now(),
              leased_by=NULL,leased_until=NULL,last_error=NULL WHERE id=%s
            """,
            (job_id,),
        )


def _fail_job(database_url: str, job: Mapping[str, Any], error: Exception) -> bool:
    terminal = int(job["attempt"]) >= int(job["max_attempts"])
    detail = {
        "type": type(error).__name__,
        "message": str(error)[:2000],
        "failed_at": datetime.now(UTC).isoformat(),
    }
    with psycopg.connect(database_url) as connection:
        connection.execute(
            """
            UPDATE intelligence_job SET status=%s,available_at=%s,updated_at=now(),
              leased_by=NULL,leased_until=NULL,last_error=%s WHERE id=%s
            """,
            (
                "FAILED" if terminal else "PENDING",
                datetime.now(UTC) + timedelta(seconds=min(300, 2 ** int(job["attempt"]))),
                Jsonb(detail), job["id"],
            ),
        )
        if terminal:
            connection.execute(
                """
                INSERT INTO dead_letter(
                  tenant_id,source_kind,source_id,error_class,error_detail,replay_metadata
                ) VALUES (%s,'INTELLIGENCE_JOB',%s,%s,%s,%s)
                """,
                (
                    job["tenant_id"], str(job["id"]), type(error).__name__,
                    Jsonb(detail), Jsonb({"repository_entity_id": str(job["repository_entity_id"])}),
                ),
            )
    return terminal


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run repository modernization intelligence")
    parser.add_argument("command", choices=("run", "work"))
    parser.add_argument("--tenant-id", type=UUID)
    parser.add_argument("--repository-id", type=UUID)
    parser.add_argument("--capability-catalog-dir", type=Path, default=Path("/code/capabilities"))
    parser.add_argument("--alternatives", type=Path, default=Path("/code/alternatives/default.json"))
    parser.add_argument("--max-jobs", type=int, default=1)
    parser.add_argument("--worker-id", default=f"{socket.gethostname()}:{os.getpid()}")
    parser.add_argument("--ai-unmapped", action="store_true")
    parser.add_argument("--ai-route", default="default")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    database_url = os.getenv("STACKGRAPH_DATABASE_URL")
    if not database_url:
        raise SystemExit("STACKGRAPH_DATABASE_URL is required")
    if args.command == "run":
        if not args.tenant_id or not args.repository_id:
            raise SystemExit("--tenant-id and --repository-id are required for run")
        capabilities, modernization = asyncio.run(run_repository_intelligence(
            database_url,
            tenant_id=args.tenant_id,
            repository_id=args.repository_id,
            capability_catalog_dir=args.capability_catalog_dir,
            alternatives_path=args.alternatives,
            use_ai_for_unmapped=args.ai_unmapped,
            ai_route=args.ai_route,
        ))
        print(json.dumps({
            "capabilities": capabilities,
            "modernization": asdict(modernization) if modernization else None,
        }, sort_keys=True))
        return 0
    result = work_jobs(
        database_url,
        capability_catalog_dir=args.capability_catalog_dir,
        alternatives_path=args.alternatives,
        worker_id=args.worker_id,
        max_jobs=max(1, args.max_jobs),
        use_ai_for_unmapped=args.ai_unmapped,
        ai_route=args.ai_route,
    )
    print(json.dumps(asdict(result), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
