from __future__ import annotations

import hashlib
import json
import time
from datetime import UTC, datetime
from typing import Any, Mapping
from uuid import NAMESPACE_URL, UUID, uuid5

from app.database import Database
from app.insight_rule_expansion import (
    EXPANDED_RULE_CATALOG,
    expanded_rule_queries,
)
from app.models import (
    DeterministicInsight,
    DeterministicInsightList,
    DeterministicInsightRecommendation,
    DeterministicInsightSummary,
    EntitySummary,
    InsightImpactStages,
    PageInfo,
)


METHOD_VERSION = "deterministic-insights/v1"

_CORE_RULE_CATALOG: tuple[Mapping[str, Any], ...] = (
    {"key": "dependency.vulnerable-direct", "name": "Direct vulnerability", "phase": 1,
     "description": "Resolved direct package versions with a current OSV affected-by relationship.",
     "severity": "CRITICAL", "readiness": "ACTIVE", "missing": ()},
    {"key": "dependency.vulnerable-transitive", "name": "Transitive vulnerability", "phase": 1,
     "description": "Vulnerable versions reached through the resolved transitive dependency graph.",
     "severity": "HIGH", "readiness": "ACTIVE", "missing": ()},
    {"key": "dependency.deprecated", "name": "Deprecated dependency", "phase": 1,
     "description": "Resolved versions explicitly marked deprecated by registry metadata.",
     "severity": "HIGH", "readiness": "ACTIVE", "missing": ()},
    {"key": "dependency.unused-direct", "name": "Unused direct dependency", "phase": 1,
     "description": "Direct dependencies without an observed static reference or runtime event.",
     "severity": "MEDIUM", "readiness": "ACTIVE", "missing": ()},
    {"key": "dependency.version-fragmentation", "name": "Version fragmentation", "phase": 1,
     "description": "Multiple resolved versions of the same package across the estate.",
     "severity": "MEDIUM", "readiness": "ACTIVE", "missing": ()},
    {"key": "capability.technology-diversity", "name": "Capability diversity", "phase": 1,
     "description": "Multiple curated technologies serving the same code capability.",
     "severity": "MEDIUM", "readiness": "ACTIVE", "missing": ()},
    {"key": "deployment.external-exposure", "name": "External exposure", "phase": 2,
     "description": "Repository and infrastructure-as-code declarations for production and public entry points.",
     "severity": "HIGH", "readiness": "ACTIVE", "missing": ()},
    {"key": "business.critical-impact", "name": "Business-critical impact", "phase": 2,
     "description": "Findings affecting applications mapped to high-criticality capabilities in the Business Map.",
     "severity": "CRITICAL", "readiness": "ACTIVE", "missing": ()},
    {"key": "architecture.drift", "name": "Architecture drift", "phase": 2,
     "description": "Technology patterns that diverge from governed golden stacks for capability-map peers.",
     "severity": "MEDIUM", "readiness": "NEEDS_DATA",
     "missing": ("Approved golden-stack baselines",)},
)
RULE_CATALOG: tuple[Mapping[str, Any], ...] = _CORE_RULE_CATALOG + EXPANDED_RULE_CATALOG

_SEVERITY_BASE = {"CRITICAL": 62.0, "HIGH": 48.0, "MEDIUM": 34.0, "LOW": 20.0, "INFO": 8.0}
_CACHE_TTL_SECONDS = 30.0
_INSIGHT_CACHE: dict[
    tuple[UUID | None, str], tuple[float, datetime, tuple[DeterministicInsight, ...]]
] = {}


def invalidate_deterministic_insight_cache(tenant_id: UUID | None) -> None:
    """Make governed map changes visible to Phase 2 findings immediately."""
    for key in [key for key in _INSIGHT_CACHE if key[0] == tenant_id]:
        _INSIGHT_CACHE.pop(key, None)

_DEPENDENCY_CTE = """
WITH dependency AS (
  SELECT fact.id fact_id,fact.tenant_id,fact.subject_entity_id repository_id,
         repository.name repository_name,fact.object_entity_id dependency_id,
         dependency.name dependency_name,dependency.canonical_key dependency_key,
         coalesce((fact.properties->>'direct')::boolean,false) direct,
         coalesce(usage.referenced,false) referenced,
         coalesce(usage.static_reachability,'UNKNOWN') static_reachability,
         coalesce(usage.runtime_observed,'UNKNOWN') runtime_observed,
         fact.observed_at
  FROM fact_assertion fact
  JOIN entity repository ON repository.id=fact.subject_entity_id
    AND repository.namespace='ENTERPRISE' AND repository.entity_type='Repository'
  JOIN entity dependency ON dependency.id=fact.object_entity_id
    AND dependency.entity_type IN ('Package','PackageVersion')
  LEFT JOIN dependency_usage_summary usage
    ON usage.dependency_fact_assertion_id=fact.id
  WHERE fact.tenant_id=%s AND fact.predicate='DEPENDS_ON' AND fact.system_to IS NULL
), context AS (
  SELECT dependency.*,
         application.subject_entity_id application_id,
         deployment.object_entity_id deployment_id
  FROM dependency
  LEFT JOIN fact_assertion application
    ON application.object_entity_id=dependency.repository_id
   AND application.predicate='IMPLEMENTED_BY' AND application.system_to IS NULL
   AND application.tenant_id=dependency.tenant_id
  LEFT JOIN fact_assertion deployment
    ON deployment.subject_entity_id=dependency.repository_id
   AND deployment.predicate='DEPLOYED_AS' AND deployment.system_to IS NULL
   AND deployment.tenant_id=dependency.tenant_id
)
"""


async def list_deterministic_insights(
    database: Database,
    *,
    tenant_id: UUID | None,
    scope_entity_id: UUID | None = None,
    rule_key: str | None = None,
    limit: int = 100,
) -> DeterministicInsightList:
    policies = await _policies(database, tenant_id)
    policy_fingerprint = hashlib.sha256(json.dumps(policies, sort_keys=True, default=str).encode()).hexdigest()
    cache_key = (tenant_id, policy_fingerprint)
    now = time.monotonic()
    for key, cached in list(_INSIGHT_CACHE.items()):
        if cached[0] <= now:
            _INSIGHT_CACHE.pop(key, None)
    cached = _INSIGHT_CACHE.get(cache_key)
    if cached is not None:
        _, as_of, cached_insights = cached
        insights = list(cached_insights)
    else:
        rows: list[Mapping[str, Any]] = []
        queries = (
            ("dependency.vulnerable-direct", _DIRECT_VULNERABILITY_SQL, (tenant_id,)),
            ("dependency.vulnerable-transitive", _TRANSITIVE_VULNERABILITY_SQL, (tenant_id,)),
            ("dependency.deprecated", _DEPRECATED_SQL, (tenant_id,)),
            ("dependency.unused-direct", _UNUSED_SQL, (tenant_id,)),
            ("dependency.version-fragmentation", _FRAGMENTATION_SQL, (tenant_id,)),
            ("capability.technology-diversity", _CAPABILITY_DIVERSITY_SQL, (tenant_id,)),
        ) + expanded_rule_queries(tenant_id, policies)
        for key, sql, params in queries:
            policy = policies[key]
            if not policy["enabled"] or (rule_key is not None and rule_key != key):
                continue
            result = await database.fetch_all(sql, params, tenant_id=tenant_id)
            rows.extend({**row, "rule_key": key, "policy": policy} for row in result)
        phase_two_context = await _phase_two_context(database, tenant_id)
        criticality_threshold = int(
            policies["business.critical-impact"]["configuration"].get("criticality_threshold", 4)
        )
        insights = [
            item for row in rows
            if (item := _to_insight(
                row,
                phase_two_context=phase_two_context,
                criticality_threshold=criticality_threshold,
            )).affected_repository_count
               >= int(row["policy"]["minimum_repositories"])
        ]
        as_of = datetime.now(UTC)
        if rule_key is None:
            _INSIGHT_CACHE[cache_key] = (now + _CACHE_TTL_SECONDS, as_of, tuple(insights))
    if rule_key is not None:
        insights = [item for item in insights if item.rule_key == rule_key]
    if scope_entity_id is not None:
        insights = [
            item for item in insights
            if item.subject.id == scope_entity_id
            or any(repository.id == scope_entity_id for repository in item.affected_repositories)
            or scope_entity_id in item.scope_entity_ids
        ]
    insights.sort(key=lambda item: (-item.priority_score, item.title, str(item.id)))
    total = len(insights)
    page = insights[:limit]
    affected_repositories = {repository.id for item in insights for repository in item.affected_repositories}
    return DeterministicInsightList(
        as_of=as_of,
        summary=DeterministicInsightSummary(
            total=total,
            critical=sum(item.severity == "CRITICAL" for item in insights),
            high=sum(item.severity == "HIGH" for item in insights),
            affected_repositories=len(affected_repositories),
            runtime_observed=sum(item.stages.runtime_observed for item in insights),
            deployed=sum(item.stages.deployed for item in insights),
        ),
        insights=page,
        page_info=PageInfo(has_next_page=total > limit),
    )


async def _policies(database: Database, tenant_id: UUID | None) -> dict[str, Mapping[str, Any]]:
    stored = await database.fetch_all(
        "SELECT * FROM deterministic_insight_rule_policy ORDER BY rule_key",
        tenant_id=tenant_id,
    )
    by_key = {row["rule_key"]: row for row in stored}
    return {
        item["key"]: {
            "enabled": bool(by_key.get(item["key"], {}).get("enabled", item["readiness"] == "ACTIVE")),
            "severity": str(by_key.get(item["key"], {}).get("severity", item["severity"])),
            "minimum_repositories": int(by_key.get(item["key"], {}).get(
                "minimum_repositories", item.get("minimum_repositories", 1),
            )),
            "configuration": {
                **dict(item.get("configuration") or {}),
                **dict(by_key.get(item["key"], {}).get("configuration") or {}),
            },
            "version": int(by_key.get(item["key"], {}).get("version", 0)),
        }
        for item in RULE_CATALOG
    }


async def _phase_two_context(
    database: Database, tenant_id: UUID | None,
) -> dict[UUID, Mapping[str, Any]]:
    rows = await database.fetch_all(
        _PHASE_TWO_CONTEXT_SQL,
        (tenant_id, tenant_id, tenant_id, tenant_id),
        tenant_id=tenant_id,
    )
    return {UUID(str(row["repository_id"])): row for row in rows}


def _to_insight(
    row: Mapping[str, Any], *,
    phase_two_context: Mapping[UUID, Mapping[str, Any]] | None = None,
    criticality_threshold: int = 4,
) -> DeterministicInsight:
    policy = row["policy"]
    repositories = tuple(_entity_from_json(value) for value in row.get("repositories") or ())
    fact_ids = tuple(sorted({UUID(str(value)) for value in row.get("fact_ids") or ()}, key=str))
    present = int(row.get("present") or len(repositories))
    referenced = int(row.get("referenced") or 0)
    reachable = int(row.get("reachable") or 0)
    runtime = int(row.get("runtime") or 0)
    deployed = int(row.get("deployed") or 0)
    applications = int(row.get("applications") or 0)
    context_by_repository = phase_two_context or {}
    repository_context = [
        context_by_repository.get(repository.id, {}) for repository in repositories
    ]
    production = sum(bool(context.get("code_production")) for context in repository_context)
    exposed = sum(bool(context.get("code_external_exposure")) for context in repository_context)
    governed_criticalities = [
        int(context["business_criticality"])
        for context in repository_context
        if context.get("business_criticality") is not None
    ]
    business_critical = (
        sum(value >= criticality_threshold for value in governed_criticalities)
        if governed_criticalities else None
    )
    missing = list(row.get("missing_inputs") or ())
    missing.append("Live deployment and runtime ingress status are not observed; only code declarations are evaluated.")
    if business_critical is None:
        missing.append("No governed capability criticality is mapped to the affected applications.")
    coverage_penalty = max(0, min(6, int(row.get("coverage_penalty") or 0)))
    risk_bonus = max(0.0, min(10.0, float(row.get("risk_bonus") or 0)))
    known_dimensions = max(1, 7 - coverage_penalty + int(business_critical is not None))
    coverage = min(1.0, known_dimensions / 9)
    severity = str(policy["severity"])
    breadth = min(12.0, present * 1.5)
    priority = min(100.0, _SEVERITY_BASE[severity] + breadth + min(6.0, referenced * 0.8)
                   + min(8.0, reachable * 1.2) + min(8.0, runtime * 2.0)
                   + min(4.0, deployed) + min(4.0, production * 2.0)
                   + min(6.0, exposed * 3.0) + min(6.0, (business_critical or 0) * 2.0)
                   + risk_bonus)
    fingerprint_payload = {
        "rule": row["rule_key"], "rule_version": METHOD_VERSION,
        "subject": str(row["subject_id"]), "facts": [str(value) for value in fact_ids],
        "policy_version": policy["version"],
        "counts": [present, referenced, reachable, runtime, deployed, production, exposed,
                   business_critical, risk_bonus],
    }
    canonical = json.dumps(fingerprint_payload, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(canonical.encode()).hexdigest()
    input_fingerprint = f"sha256:{digest}"
    insight_id = uuid5(NAMESPACE_URL, f"stackgraph:deterministic-insight:{digest}")
    recommendation = DeterministicInsightRecommendation(
        action=row["action"], title=row["recommendation_title"],
        rationale=row["recommendation_rationale"], estimated_effort=row["effort"],
    ) if row.get("action") else None
    summary = str(row["summary"])
    if present == 1:
        summary = summary.replace("1 repositories", "1 repository")
    return DeterministicInsight(
        id=insight_id, rule_key=row["rule_key"], rule_version=METHOD_VERSION,
        kind=row["kind"], severity=severity, title=row["title"], summary=summary,
        priority_score=round(priority, 2), evidence_coverage=round(coverage, 4),
        subject=EntitySummary(id=row["subject_id"], kind=row["subject_kind"],
                              name=row["subject_name"], canonical_key=row.get("subject_key")),
        affected_repository_count=present, affected_application_count=applications,
        affected_deployment_count=deployed, affected_repositories=list(repositories[:20]),
        scope_entity_ids=list(sorted(
            {UUID(str(value)) for value in row.get("scope_ids") or ()}, key=str,
        )),
        stages=InsightImpactStages(present=present, referenced=referenced,
                                   statically_reachable=reachable, runtime_observed=runtime,
                                   deployed=deployed, production=production,
                                   externally_exposed=exposed,
                                   business_critical=business_critical),
        supporting_fact_ids=list(fact_ids), missing_inputs=list(dict.fromkeys(missing)),
        recommendation=recommendation, input_fingerprint=input_fingerprint,
        detected_at=row.get("detected_at") or datetime.now(UTC),
    )


def _entity_from_json(value: Mapping[str, Any]) -> EntitySummary:
    return EntitySummary(id=value["id"], kind=value.get("kind") or "Repository", name=value["name"],
                         canonical_key=value.get("canonical_key"))


_PHASE_TWO_CONTEXT_SQL = """
WITH repository AS (
  SELECT id FROM entity
  WHERE tenant_id=%s AND namespace='ENTERPRISE' AND entity_type='Repository'
), application_link AS (
  SELECT fact.object_entity_id repository_id,fact.subject_entity_id application_id
  FROM fact_assertion fact
  WHERE fact.tenant_id=%s AND fact.predicate='IMPLEMENTED_BY' AND fact.system_to IS NULL
), criticality AS (
  SELECT link.repository_id,max(mapping.criticality)::integer business_criticality
  FROM application_link link
  JOIN current_capability_application_relationship mapping
    ON mapping.application_entity_id=link.application_id
  GROUP BY link.repository_id
), production AS (
  SELECT deployment.subject_entity_id repository_id,
         bool_or(lower(environment.name) ~ '(^|[-_ ])prod(uction)?($|[-_ ])') code_production
  FROM fact_assertion deployment
  JOIN fact_assertion location ON location.subject_entity_id=deployment.object_entity_id
    AND location.predicate='LOCATED_IN' AND location.system_to IS NULL
    AND location.tenant_id=deployment.tenant_id
  JOIN entity environment ON environment.id=location.object_entity_id
    AND environment.entity_type='Environment'
  WHERE deployment.tenant_id=%s AND deployment.predicate='DEPLOYED_AS'
    AND deployment.system_to IS NULL
    AND coalesce(deployment.properties->>'source_kind','') IN ('KUBERNETES','COMPOSE','DOCKERFILE')
  GROUP BY deployment.subject_entity_id
), exposure AS (
  SELECT fact.subject_entity_id repository_id,
         bool_or(fact.properties->>'external_exposure'='PUBLIC') code_external_exposure
  FROM fact_assertion fact
  WHERE fact.tenant_id=%s AND fact.system_to IS NULL
    AND fact.properties->>'external_exposure'='PUBLIC'
  GROUP BY fact.subject_entity_id
)
SELECT repository.id repository_id,criticality.business_criticality,
       coalesce(production.code_production,false) code_production,
       coalesce(exposure.code_external_exposure,false) code_external_exposure
FROM repository
LEFT JOIN criticality ON criticality.repository_id=repository.id
LEFT JOIN production ON production.repository_id=repository.id
LEFT JOIN exposure ON exposure.repository_id=repository.id
"""


_DIRECT_VULNERABILITY_SQL = _DEPENDENCY_CTE + """
SELECT vulnerability.id subject_id,vulnerability.entity_type subject_kind,
       vulnerability.name subject_name,vulnerability.canonical_key subject_key,
       'VULNERABLE_DIRECT_DEPENDENCY' kind,
       'Vulnerability '||vulnerability.name||' affects a directly used package' title,
       count(DISTINCT context.repository_id)||' repositories resolve an affected direct dependency version.' summary,
       count(DISTINCT context.repository_id)::integer present,
       count(DISTINCT context.repository_id) FILTER (WHERE context.referenced)::integer referenced,
       count(DISTINCT context.repository_id) FILTER (WHERE context.static_reachability='OBSERVED')::integer reachable,
       count(DISTINCT context.repository_id) FILTER (WHERE context.runtime_observed='OBSERVED')::integer runtime,
       count(DISTINCT context.deployment_id)::integer deployed,
       count(DISTINCT context.application_id)::integer applications,
       array_remove(array_agg(DISTINCT context.application_id),NULL)||array_remove(array_agg(DISTINCT context.deployment_id),NULL)||array_remove(array_agg(DISTINCT context.dependency_id),NULL) scope_ids,
       jsonb_agg(DISTINCT jsonb_build_object('id',context.repository_id,'kind','Repository','name',context.repository_name)) repositories,
       array_agg(DISTINCT context.fact_id)||array_agg(DISTINCT affected.id) fact_ids,
       max(context.observed_at) detected_at,
       'UPGRADE' action,'Upgrade the affected dependency' recommendation_title,
       'Select a non-affected version that passes runtime, API, license, and policy eligibility.' recommendation_rationale,
       'MEDIUM' effort,ARRAY[]::text[] missing_inputs
FROM context
JOIN fact_assertion affected ON affected.subject_entity_id=context.dependency_id
 AND affected.predicate='AFFECTED_BY' AND affected.system_to IS NULL
 AND (affected.tenant_id IS NULL OR affected.tenant_id=context.tenant_id)
JOIN entity vulnerability ON vulnerability.id=affected.object_entity_id
WHERE context.direct
GROUP BY vulnerability.id,vulnerability.entity_type,vulnerability.name,vulnerability.canonical_key
"""

_DEPRECATED_SQL = _DEPENDENCY_CTE + """
SELECT dependency.id subject_id,dependency.entity_type subject_kind,
       dependency.name subject_name,dependency.canonical_key subject_key,
       'DEPRECATED_DEPENDENCY' kind,
       dependency.name||' is deprecated' title,
       count(DISTINCT context.repository_id)||' repositories resolve a version explicitly marked deprecated.' summary,
       count(DISTINCT context.repository_id)::integer present,
       count(DISTINCT context.repository_id) FILTER (WHERE context.referenced)::integer referenced,
       count(DISTINCT context.repository_id) FILTER (WHERE context.static_reachability='OBSERVED')::integer reachable,
       count(DISTINCT context.repository_id) FILTER (WHERE context.runtime_observed='OBSERVED')::integer runtime,
       count(DISTINCT context.deployment_id)::integer deployed,
       count(DISTINCT context.application_id)::integer applications,
       array_remove(array_agg(DISTINCT context.application_id),NULL)||array_remove(array_agg(DISTINCT context.deployment_id),NULL)||array_remove(array_agg(DISTINCT context.dependency_id),NULL) scope_ids,
       jsonb_agg(DISTINCT jsonb_build_object('id',context.repository_id,'kind','Repository','name',context.repository_name)) repositories,
       array_agg(DISTINCT context.fact_id)||array_agg(DISTINCT metadata.id) fact_ids,
       max(context.observed_at) detected_at,
       'UPGRADE' action,'Move off the deprecated version' recommendation_title,
       'Use registry metadata and governed eligibility checks to select the replacement.' recommendation_rationale,
       'MEDIUM' effort,ARRAY[]::text[] missing_inputs
FROM context
JOIN entity dependency ON dependency.id=context.dependency_id
JOIN fact_assertion metadata ON metadata.subject_entity_id=context.dependency_id
 AND metadata.predicate='HAS_PROPERTY' AND metadata.system_to IS NULL
 AND (coalesce((metadata.object_value->>'is_deprecated')::boolean,false)
      OR nullif(metadata.object_value->>'deprecated','') IS NOT NULL)
GROUP BY dependency.id,dependency.entity_type,dependency.name,dependency.canonical_key
"""

_UNUSED_SQL = _DEPENDENCY_CTE + """
SELECT dependency.id subject_id,dependency.entity_type subject_kind,
       dependency.name subject_name,dependency.canonical_key subject_key,
       'UNUSED_DIRECT_DEPENDENCY' kind,
       dependency.name||' has no observed use' title,
       count(DISTINCT context.repository_id)||' repositories declare this direct dependency without a static reference or runtime event.' summary,
       count(DISTINCT context.repository_id)::integer present,0::integer referenced,0::integer reachable,
       0::integer runtime,count(DISTINCT context.deployment_id)::integer deployed,
       count(DISTINCT context.application_id)::integer applications,
       array_remove(array_agg(DISTINCT context.application_id),NULL)||array_remove(array_agg(DISTINCT context.deployment_id),NULL)||array_remove(array_agg(DISTINCT context.dependency_id),NULL) scope_ids,
       jsonb_agg(DISTINCT jsonb_build_object('id',context.repository_id,'kind','Repository','name',context.repository_name)) repositories,
       array_agg(DISTINCT context.fact_id) fact_ids,max(context.observed_at) detected_at,
       'REMOVE' action,'Validate and remove the unused dependency' recommendation_title,
       'Confirm dynamic and runtime use before removing the manifest and lockfile entries.' recommendation_rationale,
       'LOW' effort,ARRAY['Runtime absence is UNKNOWN when no attested trace is available.']::text[] missing_inputs
FROM context
JOIN entity dependency ON dependency.id=context.dependency_id
WHERE context.direct AND NOT context.referenced AND context.runtime_observed<>'OBSERVED'
GROUP BY dependency.id,dependency.entity_type,dependency.name,dependency.canonical_key
"""

_FRAGMENTATION_SQL = _DEPENDENCY_CTE + """
SELECT coalesce(package.entity_id,(array_agg(DISTINCT context.dependency_id ORDER BY context.dependency_id))[1]) subject_id,'Package' subject_kind,
       identity.package_name subject_name,'pkg:'||lower(registry.ecosystem)||'/'||identity.package_name subject_key,
       'VERSION_FRAGMENTATION' kind,
       identity.package_name||' is fragmented across '||count(DISTINCT identity.package_version)||' versions' title,
       count(DISTINCT context.repository_id)||' repositories use '||count(DISTINCT identity.package_version)||' resolved versions.' summary,
       count(DISTINCT context.repository_id)::integer present,
       count(DISTINCT context.repository_id) FILTER (WHERE context.referenced)::integer referenced,
       count(DISTINCT context.repository_id) FILTER (WHERE context.static_reachability='OBSERVED')::integer reachable,
       count(DISTINCT context.repository_id) FILTER (WHERE context.runtime_observed='OBSERVED')::integer runtime,
       count(DISTINCT context.deployment_id)::integer deployed,
       count(DISTINCT context.application_id)::integer applications,
       array_remove(array_agg(DISTINCT context.application_id),NULL)||array_remove(array_agg(DISTINCT context.deployment_id),NULL)||array_remove(array_agg(DISTINCT context.dependency_id),NULL) scope_ids,
       jsonb_agg(DISTINCT jsonb_build_object('id',context.repository_id,'kind','Repository','name',context.repository_name)) repositories,
       array_agg(DISTINCT context.fact_id) fact_ids,max(context.observed_at) detected_at,
       'CONSOLIDATE' action,'Converge on governed versions' recommendation_title,
       'Keep the smallest approved version set that satisfies observed runtime and API constraints.' recommendation_rationale,
       'HIGH' effort,ARRAY['Breaking-change compatibility is not established by version counts.']::text[] missing_inputs
FROM context
JOIN package_registry_identity identity ON identity.entity_id=context.dependency_id
 AND identity.package_version IS NOT NULL
JOIN package_registry registry ON registry.id=identity.package_registry_id
LEFT JOIN package_registry_identity package ON package.package_registry_id=identity.package_registry_id
 AND package.package_name=identity.package_name AND package.package_version IS NULL
GROUP BY package.entity_id,identity.package_registry_id,identity.package_name,registry.ecosystem
HAVING count(DISTINCT identity.package_version)>1
"""

_TRANSITIVE_VULNERABILITY_SQL = """
WITH root AS (
  SELECT fact.id root_fact_id,fact.subject_entity_id repository_id,repository.name repository_name,
         fact.object_entity_id root_dependency_id,dependency.canonical_key root_purl,fact.observed_at
  FROM fact_assertion fact
  JOIN entity repository ON repository.id=fact.subject_entity_id
  JOIN entity dependency ON dependency.id=fact.object_entity_id
  WHERE fact.tenant_id=%s AND fact.predicate='DEPENDS_ON' AND fact.system_to IS NULL
    AND repository.namespace='ENTERPRISE' AND repository.entity_type='Repository'
    AND coalesce((fact.properties->>'direct')::boolean,false)
), graph_edge AS (
  SELECT fact.id edge_fact_id,fact.object_entity_id node_id,
         fact.properties->>'graph_root_purl' root_purl
  FROM fact_assertion fact
  WHERE fact.predicate='DEPENDS_ON' AND fact.system_to IS NULL
    AND fact.properties->>'provider'='deps.dev'
    AND nullif(fact.properties->>'graph_root_purl','') IS NOT NULL
), impacted AS (
  SELECT root.*,graph_edge.node_id,graph_edge.edge_fact_id,
         affected.object_entity_id vulnerability_id,affected.id vulnerability_fact_id
  FROM root
  JOIN graph_edge ON graph_edge.root_purl=root.root_purl
   AND graph_edge.node_id<>root.root_dependency_id
  JOIN fact_assertion affected ON affected.subject_entity_id=graph_edge.node_id
   AND affected.predicate='AFFECTED_BY' AND affected.system_to IS NULL
)
SELECT package.id subject_id,package.entity_type subject_kind,package.name subject_name,
       package.canonical_key subject_key,'VULNERABLE_TRANSITIVE_DEPENDENCY' kind,
       vulnerability.name||' is present through '||package.name title,
       count(DISTINCT impacted.repository_id)||' repositories reach this affected transitive version.' summary,
       count(DISTINCT impacted.repository_id)::integer present,0::integer referenced,0::integer reachable,
       0::integer runtime,count(DISTINCT deployment.object_entity_id)::integer deployed,
       count(DISTINCT application.subject_entity_id)::integer applications,
       array_remove(array_agg(DISTINCT application.subject_entity_id),NULL)||array_remove(array_agg(DISTINCT deployment.object_entity_id),NULL)||array_remove(array_agg(DISTINCT impacted.root_dependency_id),NULL)||array_remove(array_agg(DISTINCT impacted.node_id),NULL) scope_ids,
       jsonb_agg(DISTINCT jsonb_build_object('id',impacted.repository_id,'kind','Repository','name',impacted.repository_name)) repositories,
       array_agg(DISTINCT impacted.root_fact_id)||array_agg(DISTINCT impacted.edge_fact_id)||array_agg(DISTINCT impacted.vulnerability_fact_id) fact_ids,
       max(impacted.observed_at) detected_at,
       'UPGRADE' action,'Upgrade the direct dependency that introduces this path' recommendation_title,
       'Use the stored dependency path to choose the smallest compatible parent upgrade.' recommendation_rationale,
       'HIGH' effort,ARRAY['Transitive call-site reachability is unavailable.']::text[] missing_inputs
FROM impacted JOIN entity package ON package.id=impacted.node_id
JOIN entity vulnerability ON vulnerability.id=impacted.vulnerability_id
LEFT JOIN fact_assertion deployment ON deployment.subject_entity_id=impacted.repository_id
 AND deployment.predicate='DEPLOYED_AS' AND deployment.system_to IS NULL
LEFT JOIN fact_assertion application ON application.object_entity_id=impacted.repository_id
 AND application.predicate='IMPLEMENTED_BY' AND application.system_to IS NULL
GROUP BY package.id,package.entity_type,package.name,package.canonical_key,vulnerability.id,vulnerability.name
"""

_CAPABILITY_DIVERSITY_SQL = """
WITH accepted AS (
  SELECT inference.repository_entity_id,inference.subject_entity_id,inference.capability_definition_id,
         inference.supporting_fact_ids,repository.name repository_name,inference.updated_at
  FROM capability_inference inference
  JOIN entity repository ON repository.id=inference.repository_entity_id
  WHERE inference.tenant_id=%s AND inference.stale_at IS NULL
    AND inference.review_state<>'REJECTED'
    AND (inference.assertion_class='CURATED' OR inference.review_state='CONFIRMED')
), flattened AS (
  SELECT accepted.*,fact_id FROM accepted CROSS JOIN LATERAL unnest(accepted.supporting_fact_ids) fact_id
)
SELECT (array_agg(DISTINCT technology.id ORDER BY technology.id))[1] subject_id,'Capability' subject_kind,capability.name subject_name,
       'capability:'||capability.capability_key subject_key,'CAPABILITY_DIVERSITY' kind,
       capability.name||' uses '||count(DISTINCT flattened.subject_entity_id)||' technologies' title,
       count(DISTINCT flattened.repository_entity_id)||' repositories use multiple curated implementations for this capability.' summary,
       count(DISTINCT flattened.repository_entity_id)::integer present,
       count(DISTINCT flattened.repository_entity_id)::integer referenced,0::integer reachable,0::integer runtime,
       count(DISTINCT deployment.object_entity_id)::integer deployed,
       count(DISTINCT application.subject_entity_id)::integer applications,
       array_remove(array_agg(DISTINCT application.subject_entity_id),NULL)||array_remove(array_agg(DISTINCT deployment.object_entity_id),NULL)||array_remove(array_agg(DISTINCT flattened.subject_entity_id),NULL) scope_ids,
       jsonb_agg(DISTINCT jsonb_build_object('id',flattened.repository_entity_id,'kind','Repository','name',flattened.repository_name)) repositories,
       array_agg(DISTINCT flattened.fact_id) fact_ids,max(flattened.updated_at) detected_at,
       'CONSOLIDATE' action,'Review capability standardization' recommendation_title,
       'Compare governed eligibility and observed usage before selecting preferred implementations.' recommendation_rationale,
       'HIGH' effort,ARRAY['Shared capability does not prove behavioral equivalence.']::text[] missing_inputs
FROM flattened JOIN capability_definition capability ON capability.id=flattened.capability_definition_id
JOIN entity technology ON technology.id=flattened.subject_entity_id
LEFT JOIN fact_assertion deployment ON deployment.subject_entity_id=flattened.repository_entity_id
 AND deployment.predicate='DEPLOYED_AS' AND deployment.system_to IS NULL
LEFT JOIN fact_assertion application ON application.object_entity_id=flattened.repository_entity_id
 AND application.predicate='IMPLEMENTED_BY' AND application.system_to IS NULL
GROUP BY capability.id,capability.name,capability.capability_key
HAVING count(DISTINCT flattened.subject_entity_id)>1
"""
