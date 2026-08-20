from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import socket
import time
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
    AlternativeDefinition,
    CodeUnitEvidence,
    DependencyUsage,
    DuplicateInput,
    InternalComponentInput,
    ModernizationAnalysis,
    ModernizationPolicyInput,
    analyze_duplicate,
    analyze_native_replacement,
    analyze_structural_duplication,
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


def enqueue_reanalysis(
    database_url: str,
    *,
    tenant_id: UUID,
    repository_id: UUID,
    capability_catalog_dir: Path,
    alternatives_path: Path,
) -> tuple[UUID, bool, str]:
    catalog = AlternativeCatalog.load(alternatives_path)
    capability_hash = hashlib.sha256()
    for path in sorted(capability_catalog_dir.glob("*.json")):
        capability_hash.update(path.name.encode())
        capability_hash.update(path.read_bytes())
    with psycopg.connect(database_url, row_factory=dict_row) as connection:
        policy = _load_policy(connection, tenant_id)
        internal_components = _load_internal_components(connection, tenant_id)
        configuration_fingerprint = "sha256:" + hashlib.sha256(json.dumps({
            "analyzer": f"{ANALYZER_KEY}/{ANALYZER_VERSION}",
            "capabilities": capability_hash.hexdigest(),
            "alternatives": catalog.content_hash,
            "policy": {
                "id": str(policy.id) if policy.id else None,
                "key": policy.key,
                "version": policy.version,
                "runtime_versions": dict(sorted(policy.runtime_versions.items())),
                "allowed_licenses": sorted(policy.allowed_licenses),
                "denied_option_keys": sorted(policy.denied_option_keys),
                "allowed_security_statuses": sorted(policy.allowed_security_statuses),
                "required_policy_tags": sorted(policy.required_policy_tags),
            },
            "internal_components": [{
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
                "supporting_fact_ids": sorted(
                    str(value) for value in component.supporting_fact_ids
                ),
            } for component in internal_components],
        }, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        snapshot = connection.execute(
            """
            SELECT snapshot.*
            FROM source_snapshot snapshot
            JOIN ingest_target target ON target.id=snapshot.ingest_target_id
            JOIN entity repository
              ON repository.tenant_id=snapshot.tenant_id
             AND repository.namespace='ENTERPRISE'
             AND repository.entity_type='Repository'
             AND repository.canonical_key=target.target_key
            WHERE snapshot.tenant_id=%s AND repository.id=%s
              AND snapshot.status='PUBLISHED' AND snapshot.completeness='COMPLETE'
              AND snapshot.extractor_key='repository-dependency-usage'
            ORDER BY snapshot.published_at DESC,snapshot.id DESC LIMIT 1
            """,
            (tenant_id, repository_id),
        ).fetchone()
        if snapshot is None:
            raise ValueError("repository has no complete published usage snapshot")
        row = connection.execute(
            """
            INSERT INTO intelligence_job(
              tenant_id,repository_entity_id,source_snapshot_id,source_revision,
              job_kind,configuration_fingerprint
            ) VALUES (%s,%s,%s,%s,'REPOSITORY_MODERNIZATION',%s)
            ON CONFLICT(
              tenant_id,repository_entity_id,source_revision,job_kind,configuration_fingerprint
            ) DO NOTHING RETURNING id
            """,
            (
                tenant_id, repository_id, snapshot["id"], snapshot["source_revision"],
                configuration_fingerprint,
            ),
        ).fetchone()
        if row:
            return row["id"], True, configuration_fingerprint
        existing = connection.execute(
            """
            SELECT id FROM intelligence_job
            WHERE tenant_id=%s AND repository_entity_id=%s AND source_revision=%s
              AND job_kind='REPOSITORY_MODERNIZATION' AND configuration_fingerprint=%s
            """,
            (tenant_id, repository_id, snapshot["source_revision"], configuration_fingerprint),
        ).fetchone()
        assert existing is not None
        return existing["id"], False, configuration_fingerprint


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
        policy = _load_policy(connection, tenant_id)
        internal_components = _load_internal_components(connection, tenant_id)
        code_units = _load_code_units(
            connection, tenant_id=tenant_id, repository_id=repository_id,
            source_revision=source_revision,
        )
        duplicates = _load_duplicates(
            connection,
            tenant_id=tenant_id,
            repository_id=repository_id,
            source_revision=source_revision,
        )
        analyses: list[ModernizationAnalysis] = []
        for item in duplicates:
            dependency_paths = {
                str(location.get("path"))
                for dependency in item.dependencies for location in dependency.source_locations
                if location.get("path")
            }
            analyses.append(analyze_duplicate(
                item, catalog, policy=policy, internal_components=internal_components,
                code_units=tuple(unit for unit in code_units if unit.path in dependency_paths),
                additional_alternatives=_upgrade_alternatives(
                    connection, item.dependencies, capability_key=item.capability_key,
                ),
            ))
        for group in _structural_groups(code_units, repository_id):
            capability = _capability_for_units(connection, tenant_id, group)
            analyses.append(analyze_structural_duplication(
                repository_id=repository_id, source_revision=source_revision, units=group,
                policy=policy,
                capability_definition_id=capability["id"] if capability else None,
                capability_name=capability["name"] if capability else None,
            ))
        duplicate_inference_ids = {
            dependency.inference_id for duplicate in duplicates for dependency in duplicate.dependencies
        }
        for capability, dependency in _load_capability_dependencies(
            connection, tenant_id=tenant_id, repository_id=repository_id,
            source_revision=source_revision,
        ):
            if dependency.inference_id in duplicate_inference_ids:
                continue
            dependency_paths = {
                str(location.get("path")) for location in dependency.source_locations if location.get("path")
            }
            native = analyze_native_replacement(
                repository_id=repository_id, source_revision=source_revision,
                capability_definition_id=capability["id"],
                capability_key=capability["key"], capability_name=capability["name"],
                dependency=dependency, catalog=catalog, policy=policy,
                internal_components=internal_components,
                code_units=tuple(unit for unit in code_units if unit.path in dependency_paths),
                additional_alternatives=_upgrade_alternatives(
                    connection, (dependency,), capability_key=capability["key"],
                ),
            )
            if native is not None:
                analyses.append(native)
        candidate_count = 0
        recommendation_count = 0
        replayed_candidates = 0
        replayed_recommendations = 0
        active_candidate_fingerprints: list[str] = []
        active_recommendation_fingerprints: list[str] = []
        for analysis in analyses:
            candidate_id, candidate_created = _persist_candidate(connection, tenant_id, analysis)
            option_ids = _persist_options(connection, tenant_id, candidate_id, analysis)
            _persist_impact(connection, tenant_id, candidate_id, analysis)
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
            active_candidate_fingerprints.append(analysis.analysis_fingerprint)
            active_recommendation_fingerprints.append(analysis.recommendation.analysis_fingerprint)
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
        connection.execute(
            """
            UPDATE modernization_candidate
            SET stale_at=coalesce(stale_at,now()),updated_at=now()
            WHERE tenant_id=%s AND repository_entity_id=%s AND source_revision=%s
              AND stale_at IS NULL AND NOT(analysis_fingerprint=ANY(%s::text[]))
            """,
            (tenant_id, repository_id, source_revision, active_candidate_fingerprints),
        )
        connection.execute(
            """
            UPDATE modernization_recommendation
            SET stale_at=coalesce(stale_at,now()),updated_at=now()
            WHERE tenant_id=%s AND repository_entity_id=%s AND source_revision=%s
              AND stale_at IS NULL AND NOT(analysis_fingerprint=ANY(%s::text[]))
            """,
            (tenant_id, repository_id, source_revision, active_recommendation_fingerprints),
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


def _load_policy(
    connection: psycopg.Connection,
    tenant_id: UUID,
) -> ModernizationPolicyInput:
    row = connection.execute(
        """
        SELECT * FROM modernization_policy
        WHERE tenant_id=%s AND status='ACTIVE'
        ORDER BY updated_at DESC,id LIMIT 1
        """,
        (tenant_id,),
    ).fetchone()
    if row is None:
        return ModernizationPolicyInput()
    return ModernizationPolicyInput(
        id=row["id"], key=row["policy_key"], version=row["version"],
        runtime_versions=dict(row["runtime_versions"]),
        allowed_licenses=tuple(row["allowed_licenses"]),
        denied_option_keys=tuple(row["denied_option_keys"]),
        allowed_security_statuses=tuple(row["allowed_security_statuses"]),
        required_policy_tags=tuple(row["required_policy_tags"]),
    )


def _load_internal_components(
    connection: psycopg.Connection,
    tenant_id: UUID,
) -> tuple[InternalComponentInput, ...]:
    rows = connection.execute(
        """
        SELECT component.*,entity.name
        FROM modernization_internal_component component
        JOIN entity ON entity.id=component.component_entity_id
        WHERE component.tenant_id=%s
        ORDER BY component.component_key,component.version
        """,
        (tenant_id,),
    ).fetchall()
    return tuple(InternalComponentInput(
        id=row["id"], entity_id=row["component_entity_id"],
        capability_definition_id=row["capability_definition_id"],
        key=row["component_key"], name=row["name"], version=row["version"],
        status=row["status"], api_symbols=tuple(row["api_symbols"]),
        runtime_constraints=dict(row["runtime_constraints"]),
        behavior_verified=any(
            isinstance(item, Mapping) and item.get("verified") is True
            for item in row["behavior_claims"]
        ),
        license=row["license"], security_status=row["security_status"],
        policy_tags=tuple(row["policy_tags"]),
        supporting_fact_ids=tuple(row["supporting_fact_ids"]),
    ) for row in rows)


def _load_code_units(
    connection: psycopg.Connection,
    *,
    tenant_id: UUID,
    repository_id: UUID,
    source_revision: str,
) -> tuple[CodeUnitEvidence, ...]:
    rows = connection.execute(
        """
        WITH current_fingerprints AS (
          SELECT DISTINCT structural_fingerprint
          FROM code_implementation_summary
          WHERE tenant_id=%s AND repository_entity_id=%s AND source_revision=%s
        )
        SELECT unit.*
        FROM code_implementation_summary unit
        JOIN fact_assertion fact ON fact.id=unit.fact_assertion_id AND fact.system_to IS NULL
        WHERE unit.tenant_id=%s AND unit.structural_fingerprint IN (
          SELECT structural_fingerprint FROM current_fingerprints
        )
        ORDER BY unit.structural_fingerprint,unit.repository_entity_id,unit.path,unit.line_start
        """,
        (tenant_id, repository_id, source_revision, tenant_id),
    ).fetchall()
    return tuple(CodeUnitEvidence(
        id=row["id"], repository_id=row["repository_entity_id"],
        fact_id=row["fact_assertion_id"], source_revision=row["source_revision"],
        language=row["language"], qualified_name=row["qualified_name"], path=row["path"],
        line_start=row["line_start"], line_end=row["line_end"],
        structural_fingerprint=row["structural_fingerprint"],
        semantic_tokens=tuple(row["semantic_tokens"]),
        dependency_keys=tuple(row["dependency_keys"]),
        covering_tests=tuple(row["covering_tests"]),
        dynamic_signals=tuple(row["dynamic_signals"]),
        touchpoints=tuple(dict(item) for item in row["touchpoints"]),
        vendored=row["vendored"], limitations=tuple(row["limitations"]),
    ) for row in rows)


def _structural_groups(
    units: tuple[CodeUnitEvidence, ...],
    repository_id: UUID,
) -> tuple[tuple[CodeUnitEvidence, ...], ...]:
    grouped: dict[str, list[CodeUnitEvidence]] = {}
    for unit in units:
        grouped.setdefault(unit.structural_fingerprint, []).append(unit)
    values: list[tuple[CodeUnitEvidence, ...]] = []
    for fingerprint in sorted(grouped):
        group = tuple(grouped[fingerprint])
        if len(group) < 2 or not any(unit.repository_id == repository_id for unit in group):
            continue
        common_tokens = set(group[0].semantic_tokens)
        for unit in group[1:]:
            common_tokens.intersection_update(unit.semantic_tokens)
        if len(common_tokens) < 2 and not any(unit.vendored for unit in group):
            continue
        values.append(group)
    return tuple(values)


def _capability_for_units(
    connection: psycopg.Connection,
    tenant_id: UUID,
    units: tuple[CodeUnitEvidence, ...],
) -> Mapping[str, Any] | None:
    unit_tokens = {token for unit in units for token in unit.semantic_tokens}
    rows = connection.execute(
        """
        SELECT capability.id,capability.capability_key,capability.name,capability.aliases
        FROM capability_definition capability
        JOIN capability_taxonomy_version taxonomy ON taxonomy.id=capability.taxonomy_version_id
        WHERE taxonomy.status='ACTIVE' AND (taxonomy.tenant_id IS NULL OR taxonomy.tenant_id=%s)
        ORDER BY taxonomy.tenant_id NULLS LAST,capability.capability_key
        """,
        (tenant_id,),
    ).fetchall()
    best = None
    best_score = 0
    for row in rows:
        terms = {
            token
            for value in (row["capability_key"], row["name"], *row["aliases"])
            for token in _semantic_parts(str(value))
        }
        score = len(unit_tokens & terms)
        if score > best_score:
            best = {"id": row["id"], "key": row["capability_key"], "name": row["name"]}
            best_score = score
    return best if best_score >= 1 else None


def _semantic_parts(value: str) -> set[str]:
    import re
    return {part for part in re.split(r"[^a-z0-9]+", value.lower()) if len(part) > 1}


def _load_capability_dependencies(
    connection: psycopg.Connection,
    *,
    tenant_id: UUID,
    repository_id: UUID,
    source_revision: str,
) -> tuple[tuple[Mapping[str, Any], DependencyUsage], ...]:
    rows = connection.execute(
        """
        SELECT inference.*,entity.canonical_key,entity.name,
               capability.capability_key,capability.name capability_name
        FROM capability_inference inference
        JOIN entity ON entity.id=inference.subject_entity_id
        JOIN capability_definition capability ON capability.id=inference.capability_definition_id
        WHERE inference.tenant_id=%s AND inference.repository_entity_id=%s
          AND inference.source_revision=%s AND inference.stale_at IS NULL
          AND inference.review_state<>'REJECTED'
        ORDER BY capability.capability_key,entity.canonical_key,inference.id
        """,
        (tenant_id, repository_id, source_revision),
    ).fetchall()
    return tuple((
        {"id": row["capability_definition_id"], "key": row["capability_key"], "name": row["capability_name"]},
        _dependency_from_inference(connection, row),
    ) for row in rows)


def _dependency_from_inference(
    connection: psycopg.Connection,
    inference: Mapping[str, Any],
) -> DependencyUsage:
    fact_ids = list(inference["supporting_fact_ids"])
    usage_rows = connection.execute(
        """
        SELECT usage.*,fact.id fact_id
        FROM dependency_usage_summary usage
        JOIN fact_assertion fact ON fact.id=usage.dependency_fact_assertion_id
        WHERE fact.id=ANY(%s::uuid[]) ORDER BY fact.id
        """,
        (fact_ids,),
    ).fetchall()
    evidence_rows = connection.execute(
        """
        SELECT locator FROM evidence
        WHERE fact_assertion_id=ANY(%s::uuid[]) ORDER BY fact_assertion_id,id
        """,
        (fact_ids,),
    ).fetchall()
    return DependencyUsage(
        entity_id=inference["subject_entity_id"], canonical_key=inference["canonical_key"],
        name=inference["name"], inference_id=inference["id"],
        supporting_fact_ids=tuple(fact_ids), confidence=float(inference["confidence"]),
        reference_count=sum(int(item["reference_count"]) for item in usage_rows),
        referenced_symbols=tuple(sorted({
            str(symbol) for item in usage_rows for symbol in (item["referenced_symbols"] or [])
        })),
        source_locations=tuple(dict(item["locator"]) for item in evidence_rows),
        runtime_observed=(
            "OBSERVED" if any(item["runtime_observed"] == "OBSERVED" for item in usage_rows)
            else "NOT_OBSERVED" if usage_rows and all(
                item["runtime_observed"] == "NOT_OBSERVED" for item in usage_rows
            ) else "UNKNOWN"
        ),
        limitations=tuple(sorted({
            str(value) for item in usage_rows for value in (item["limitations"] or [])
        })),
    )


def _upgrade_alternatives(
    connection: psycopg.Connection,
    dependencies: tuple[DependencyUsage, ...],
    *,
    capability_key: str,
) -> tuple[AlternativeDefinition, ...]:
    values: list[AlternativeDefinition] = []
    for dependency in dependencies:
        row = connection.execute(
            """
            SELECT
              coalesce(fact.object_value#>>'{dist_tags,latest}',entity.properties#>>'{dist_tags,latest}') latest,
              coalesce(fact.object_value->>'license',entity.properties->>'license') license,
              coalesce(fact.object_value->'engines',entity.properties->'engines','{}'::jsonb) engines
            FROM entity
            LEFT JOIN fact_assertion fact
              ON fact.subject_entity_id=entity.id AND fact.predicate='HAS_PROPERTY'
             AND fact.system_to IS NULL
             AND fact.object_value->>'record_kind'='npm_registry_version_metadata'
            WHERE entity.id=%s ORDER BY fact.observed_at DESC NULLS LAST LIMIT 1
            """,
            (dependency.entity_id,),
        ).fetchone()
        if not row or not row["latest"]:
            continue
        package_key, separator, current_version = dependency.canonical_key.rpartition("@")
        if not separator or str(row["latest"]) == current_version:
            continue
        values.append(AlternativeDefinition(
            capability_key=capability_key, kind="UPGRADE",
            key=f"{package_key}@{row['latest']}",
            name=f"{dependency.name} {row['latest']}",
            rationale=f"Registry metadata identifies {row['latest']} as the latest release.",
            validation_gaps=("Confirm changelog, API, behavior, and transitive dependency compatibility.",),
            runtime_constraints={str(key): str(value) for key, value in dict(row["engines"]).items()},
            license=str(row["license"]) if row["license"] else None,
            security_status="UNKNOWN", behavior_verified=False,
        ))
    return tuple(values)


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
          input_fingerprint,analysis_fingerprint,source_code_unit_ids
        ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        ON CONFLICT(tenant_id,analysis_fingerprint) DO NOTHING RETURNING id
        """,
        (
            tenant_id, analysis.repository_id, analysis.source_revision,
            analysis.duplicate_candidate_id, analysis.capability_definition_id,
            analysis.candidate_kind, list(analysis.subject_entity_ids), analysis.confidence,
            analysis.summary, list(analysis.supporting_fact_ids),
            Jsonb(list(analysis.source_locations)), Jsonb(list(analysis.validation_gaps)),
            ANALYZER_KEY, ANALYZER_VERSION, analysis.input_fingerprint,
            analysis.analysis_fingerprint, list(analysis.source_code_unit_ids),
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
            DO UPDATE SET target_entity_id=EXCLUDED.target_entity_id,
              compatibility=EXCLUDED.compatibility,rank=EXCLUDED.rank,score=EXCLUDED.score,
              score_components=EXCLUDED.score_components,rationale=EXCLUDED.rationale,
              tradeoffs=EXCLUDED.tradeoffs,disqualifiers=EXCLUDED.disqualifiers,
              validation_gaps=EXCLUDED.validation_gaps,
              supporting_fact_ids=EXCLUDED.supporting_fact_ids
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
        eligibility = option.eligibility
        connection.execute(
            """
            INSERT INTO modernization_option_evaluation(
              tenant_id,modernization_option_id,policy_id,capability_fit,api_fit,
              behavior_fit,runtime_fit,license_fit,security_fit,policy_fit,eligible,
              evidence,disqualifiers,unknowns
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT(modernization_option_id) DO UPDATE SET
              policy_id=EXCLUDED.policy_id,capability_fit=EXCLUDED.capability_fit,
              api_fit=EXCLUDED.api_fit,behavior_fit=EXCLUDED.behavior_fit,
              runtime_fit=EXCLUDED.runtime_fit,license_fit=EXCLUDED.license_fit,
              security_fit=EXCLUDED.security_fit,policy_fit=EXCLUDED.policy_fit,
              eligible=EXCLUDED.eligible,evidence=EXCLUDED.evidence,
              disqualifiers=EXCLUDED.disqualifiers,unknowns=EXCLUDED.unknowns,
              evaluated_at=now()
            """,
            (
                tenant_id, row["id"], eligibility.policy_id,
                eligibility.capability_fit, eligibility.api_fit, eligibility.behavior_fit,
                eligibility.runtime_fit, eligibility.license_fit, eligibility.security_fit,
                eligibility.policy_fit, eligibility.eligible, Jsonb(dict(eligibility.evidence)),
                Jsonb(list(eligibility.disqualifiers)), Jsonb(list(eligibility.unknowns)),
            ),
        )
    return values


def _persist_impact(
    connection: psycopg.Connection,
    tenant_id: UUID,
    candidate_id: UUID,
    analysis: ModernizationAnalysis,
) -> None:
    impact = analysis.impact
    connection.execute(
        """
        INSERT INTO modernization_impact(
          tenant_id,modernization_candidate_id,affected_call_sites,affected_files,
          covered_call_sites,uncovered_call_sites,affected_test_files,dynamic_signals,
          configuration_touchpoints,build_touchpoints,deployment_touchpoints,
          evidence_locations,confidence,effort_points,effort_model_version,limitations
        ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        ON CONFLICT(modernization_candidate_id) DO UPDATE SET
          affected_call_sites=EXCLUDED.affected_call_sites,
          affected_files=EXCLUDED.affected_files,
          covered_call_sites=EXCLUDED.covered_call_sites,
          uncovered_call_sites=EXCLUDED.uncovered_call_sites,
          affected_test_files=EXCLUDED.affected_test_files,
          dynamic_signals=EXCLUDED.dynamic_signals,
          configuration_touchpoints=EXCLUDED.configuration_touchpoints,
          build_touchpoints=EXCLUDED.build_touchpoints,
          deployment_touchpoints=EXCLUDED.deployment_touchpoints,
          evidence_locations=EXCLUDED.evidence_locations,
          confidence=EXCLUDED.confidence,effort_points=EXCLUDED.effort_points,
          effort_model_version=EXCLUDED.effort_model_version,
          limitations=EXCLUDED.limitations,updated_at=now()
        """,
        (
            tenant_id, candidate_id, impact.affected_call_sites, impact.affected_files,
            impact.covered_call_sites, impact.uncovered_call_sites,
            list(impact.affected_test_files), list(impact.dynamic_signals),
            Jsonb(list(impact.configuration_touchpoints)), Jsonb(list(impact.build_touchpoints)),
            Jsonb(list(impact.deployment_touchpoints)), Jsonb(list(impact.evidence_locations)),
            impact.confidence, impact.effort_points, impact.effort_model_version,
            Jsonb(list(impact.limitations)),
        ),
    )


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
    parser.add_argument("command", choices=("run", "work", "serve", "requeue"))
    parser.add_argument("--tenant-id", type=UUID)
    parser.add_argument("--repository-id", type=UUID)
    parser.add_argument("--capability-catalog-dir", type=Path, default=Path("/code/capabilities"))
    parser.add_argument("--alternatives", type=Path, default=Path("/code/alternatives/default.json"))
    parser.add_argument("--max-jobs", type=int, default=1)
    parser.add_argument("--poll-seconds", type=float, default=2.0)
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
    if args.command == "requeue":
        if not args.tenant_id or not args.repository_id:
            raise SystemExit("--tenant-id and --repository-id are required for requeue")
        job_id, created, fingerprint = enqueue_reanalysis(
            database_url, tenant_id=args.tenant_id, repository_id=args.repository_id,
            capability_catalog_dir=args.capability_catalog_dir,
            alternatives_path=args.alternatives,
        )
        print(json.dumps({
            "job_id": str(job_id), "created": created,
            "configuration_fingerprint": fingerprint,
        }, sort_keys=True))
        return 0
    if args.poll_seconds < 0:
        raise SystemExit("--poll-seconds must not be negative")
    while True:
        result = work_jobs(
            database_url,
            capability_catalog_dir=args.capability_catalog_dir,
            alternatives_path=args.alternatives,
            worker_id=args.worker_id,
            max_jobs=max(1, args.max_jobs),
            use_ai_for_unmapped=args.ai_unmapped,
            ai_route=args.ai_route,
        )
        print(json.dumps(asdict(result), sort_keys=True), flush=True)
        if args.command == "work":
            return 0
        time.sleep(max(0.1, args.poll_seconds))


if __name__ == "__main__":
    raise SystemExit(main())
