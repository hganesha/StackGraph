"""Deterministic estate-posture and outcome reports.

These four reports answer questions about how much of the estate StackGraph can
actually reason over, what entered it recently, which governed business
capabilities have no application behind them, and which accepted decisions never
turned into an implementation.  Every answer is produced from recorded state:
none of them invokes an AI provider, and none of them invents a citation for a
record that is not backed by a fact assertion.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Mapping, Protocol
from uuid import UUID

from app.models import AskResponse, Citation


METHOD_VERSION = "enterprise-posture-insights/v1"

# Report thresholds are constants rather than tenant policy so that two runs over
# the same estate always produce the same report.
TECHNOLOGY_INTRODUCTION_WINDOW_DAYS = 90
DECISION_LAG_THRESHOLD_DAYS = 30
DARK_CAPABILITY_MINIMUM_CRITICALITY = 4
# Repositories without a connector-maintained freshness row fall back to how
# recently the estate last saw them.
FRESHNESS_FALLBACK_DAYS = 30

ROW_LIMIT = 50

ASSURANCE_COVERAGE = "assurance_coverage"
TECHNOLOGY_INTRODUCTION = "technology_introduction"
BUSINESS_DARK_CAPABILITY = "business_dark_capability"
DECISION_LAG = "decision_lag"

# Registered alongside the existing executive reports; the categories stay inside
# the frozen EnterpriseInsightCategory contract.
POSTURE_INSIGHT_REPORTS: tuple[dict[str, str], ...] = (
    {
        "key": ASSURANCE_COVERAGE, "title": "Analytical assurance coverage",
        "category": "ENTERPRISE_RISK", "metric_label": "of the estate analytically covered",
        "question": "What share of our estate is analytically covered?",
        "populated_status": "WATCH", "metric_field": "coverage_percent",
        "empty_requires_data": "true",
    },
    {
        "key": TECHNOLOGY_INTRODUCTION, "title": "Technologies introduced",
        "category": "TECHNOLOGY_RATIONALIZATION", "metric_label": "technologies introduced (90 days)",
        "question": "Which technologies were introduced into the estate in the last 90 days?",
        "populated_status": "WATCH", "metric_field": "total_count",
        "empty_requires_data": "true",
    },
    {
        "key": BUSINESS_DARK_CAPABILITY, "title": "Dark business capabilities",
        "category": "PORTFOLIO_DECISIONS", "metric_label": "critical capabilities without applications",
        "question": "Which critical business capabilities have no application behind them?",
        "populated_status": "ACTION_REQUIRED", "metric_field": "total_count",
        "empty_requires_data": "true",
    },
    {
        "key": DECISION_LAG, "title": "Decision implementation lag",
        "category": "PORTFOLIO_DECISIONS", "metric_label": "longest wait in days",
        "question": "Which accepted decisions have not been implemented?",
        "populated_status": "ACTION_REQUIRED", "metric_field": "days_since_acceptance",
        "empty_requires_data": "true",
    },
)


class SupportsFetch(Protocol):
    async def fetch_one(
        self, query: str, params: Any = None, *, tenant_id: UUID | None = None,
    ) -> dict[str, Any] | None: ...

    async def fetch_all(
        self, query: str, params: Any = None, *, tenant_id: UUID | None = None,
    ) -> list[dict[str, Any]]: ...


def match_posture_question(normalized: str) -> str | None:
    """Route a normalized question to a posture report key, or None."""
    if "analytically covered" in normalized or "analytical assurance" in normalized:
        return ASSURANCE_COVERAGE
    if "technolog" in normalized and any(
        word in normalized for word in ("introduced", "introduction", "newly adopted")
    ):
        return TECHNOLOGY_INTRODUCTION
    if "capabilit" in normalized and any(
        phrase in normalized
        for phrase in ("no application", "without application", "dark business", "dark capabilit")
    ):
        return BUSINESS_DARK_CAPABILITY
    if "decision lag" in normalized or (
        "accepted" in normalized
        and any(word in normalized for word in ("decision", "recommendation"))
        and "implement" in normalized
    ):
        return DECISION_LAG
    return None


async def answer_posture_report(
    database: SupportsFetch, key: str, *, tenant_id: UUID | None,
) -> AskResponse:
    if key == ASSURANCE_COVERAGE:
        return await assurance_coverage(database, tenant_id=tenant_id)
    if key == TECHNOLOGY_INTRODUCTION:
        return await technology_introduction(database, tenant_id=tenant_id)
    if key == BUSINESS_DARK_CAPABILITY:
        return await business_dark_capability(database, tenant_id=tenant_id)
    if key == DECISION_LAG:
        return await decision_lag(database, tenant_id=tenant_id)
    raise KeyError(key)


# --- H1: analytical assurance coverage ------------------------------------

_ASSURANCE_COVERAGE_SQL = """
WITH analyzable_ecosystem AS (
  SELECT 'NPM'::text ecosystem
  UNION
  SELECT admission.ecosystem
  FROM ecosystem_admission admission
  WHERE admission.tenant_id=%(tenant_id)s AND admission.status='ADMITTED'
), repository AS (
  SELECT entity.id repository_id,entity.canonical_key,entity.last_seen_at
  FROM entity
  WHERE entity.tenant_id=%(tenant_id)s
    AND entity.namespace='ENTERPRISE' AND entity.entity_type='Repository'
), repository_target AS (
  -- One row per repository: a repository key can be tracked by more than one
  -- source system, and duplicates would inflate every coverage denominator.
  SELECT DISTINCT ON (repository.repository_id)
         repository.repository_id,repository.last_seen_at,
         target.id target_id,target.last_success_at,
         coalesce(target.enabled,true) enabled,
         coalesce((target.refresh_policy->>'archived')::boolean,false) archived,
         freshness.status freshness_status,freshness.expected_by,
         snapshot.id source_snapshot_id
  FROM repository
  LEFT JOIN ingest_target target
    ON target.target_key=repository.canonical_key
   AND target.tenant_id=%(tenant_id)s AND target.target_kind='REPOSITORY'
  LEFT JOIN freshness_state freshness ON freshness.ingest_target_id=target.id
  LEFT JOIN LATERAL (
    SELECT published.id
    FROM source_snapshot published
    WHERE published.ingest_target_id=target.id AND published.status='PUBLISHED'
    ORDER BY published.published_at DESC NULLS LAST,published.observed_at DESC,published.id
    LIMIT 1
  ) snapshot ON true
  ORDER BY repository.repository_id,target.last_success_at DESC NULLS LAST,target.id
), repository_state AS (
  SELECT repository_target.*,coalesce(failure.failed,false) run_failed
  FROM repository_target
  LEFT JOIN LATERAL (
    SELECT true failed
    FROM ingest_run run
    WHERE run.ingest_target_id=repository_target.target_id AND run.status='FAILED'
      AND (repository_target.last_success_at IS NULL
           OR run.completed_at IS NULL
           OR run.completed_at>repository_target.last_success_at)
    LIMIT 1
  ) failure ON true
), dependency_ecosystem AS (
  SELECT DISTINCT dependency.subject_entity_id repository_id,
         upper(coalesce(registry.ecosystem,
           nullif(substring(technology.canonical_key from '^pkg:([^/]+)'),''),
           'UNKNOWN')) ecosystem
  FROM fact_assertion dependency
  JOIN entity technology ON technology.id=dependency.object_entity_id
  LEFT JOIN package_registry_identity identity ON identity.entity_id=technology.id
  LEFT JOIN package_registry registry ON registry.id=identity.package_registry_id
  WHERE dependency.tenant_id=%(tenant_id)s AND dependency.predicate='DEPENDS_ON'
    AND dependency.system_to IS NULL
    AND (technology.canonical_key LIKE 'pkg:%%' OR registry.ecosystem IS NOT NULL)
), classified_ecosystem AS (
  SELECT dependency_ecosystem.repository_id,dependency_ecosystem.ecosystem,
         dependency_ecosystem.ecosystem IN (SELECT ecosystem FROM analyzable_ecosystem) analyzable
  FROM dependency_ecosystem
), repository_ecosystem AS (
  SELECT repository_id,count(*) FILTER (WHERE NOT analyzable)::integer unsupported_ecosystems
  FROM classified_ecosystem GROUP BY repository_id
), fact_evidence AS (
  SELECT fact.id fact_id,fact.subject_entity_id repository_id,
         EXISTS(SELECT 1 FROM evidence WHERE evidence.fact_assertion_id=fact.id) evidenced
  FROM fact_assertion fact
  WHERE fact.tenant_id=%(tenant_id)s AND fact.system_to IS NULL
), repository_evidence AS (
  SELECT repository_id,count(*) FILTER (WHERE evidenced)::integer evidenced_facts
  FROM fact_evidence GROUP BY repository_id
), coverage AS (
  SELECT repository_state.repository_id,
         repository_state.last_seen_at IS NOT NULL scanned,
         CASE
           WHEN repository_state.freshness_status IS NOT NULL
             THEN repository_state.freshness_status='FRESH'
              AND (repository_state.expected_by IS NULL
                   OR repository_state.expected_by>now())
           ELSE repository_state.last_seen_at IS NOT NULL
            AND repository_state.last_seen_at
                >=now()-make_interval(days=>%(freshness_fallback_days)s)
         END fresh,
         coalesce(repository_ecosystem.unsupported_ecosystems,0)=0 ecosystem_supported,
         coalesce(repository_evidence.evidenced_facts,0)>0 evidenced,
         repository_state.source_snapshot_id IS NOT NULL source_snapshotted,
         NOT (
           (repository_state.target_id IS NOT NULL
             AND (NOT repository_state.enabled OR repository_state.archived))
           OR repository_state.run_failed
           OR coalesce(repository_state.freshness_status,'')='ERROR'
         ) available
  FROM repository_state
  LEFT JOIN repository_ecosystem
    ON repository_ecosystem.repository_id=repository_state.repository_id
  LEFT JOIN repository_evidence
    ON repository_evidence.repository_id=repository_state.repository_id
)
SELECT
  (SELECT count(*)::integer FROM coverage) repositories,
  (SELECT count(*) FILTER (WHERE fresh)::integer FROM coverage) fresh_repositories,
  (SELECT count(*) FILTER (WHERE ecosystem_supported)::integer FROM coverage)
    ecosystem_supported_repositories,
  (SELECT count(*) FILTER (WHERE available)::integer FROM coverage) available_repositories,
  (SELECT count(*) FILTER (WHERE source_snapshotted)::integer FROM coverage)
    source_snapshotted_repositories,
  (SELECT count(*) FILTER (
     WHERE scanned AND fresh AND ecosystem_supported AND evidenced AND available
       AND source_snapshotted
   )::integer FROM coverage) covered_repositories,
  (SELECT count(*)::integer FROM fact_evidence) facts,
  (SELECT count(*) FILTER (WHERE evidenced)::integer FROM fact_evidence) evidenced_facts,
  (SELECT count(*)::integer FROM connector WHERE connector.tenant_id=%(tenant_id)s) connectors,
  (SELECT count(*)::integer FROM connector
    WHERE connector.tenant_id=%(tenant_id)s
      AND connector.status='CONNECTED' AND connector.last_error IS NULL) healthy_connectors,
  (SELECT count(*)::integer FROM dead_letter
    WHERE dead_letter.tenant_id=%(tenant_id)s AND dead_letter.replayed_at IS NULL)
    open_dead_letters,
  (SELECT count(*)::integer FROM connector_quota
    WHERE connector_quota.tenant_id=%(tenant_id)s) quota_providers,
  (SELECT count(*)::integer FROM connector_quota
    WHERE connector_quota.tenant_id=%(tenant_id)s AND connector_quota.status='OK'
      AND (connector_quota.backoff_until IS NULL OR connector_quota.backoff_until<=now()))
    healthy_quota_providers,
  (SELECT coalesce(string_agg(ecosystem,', ' ORDER BY ecosystem),'') FROM (
     SELECT DISTINCT ecosystem FROM classified_ecosystem WHERE NOT analyzable
   ) unsupported) unsupported_ecosystems,
  (SELECT coalesce(string_agg(ecosystem,', ' ORDER BY ecosystem),'')
     FROM analyzable_ecosystem) analyzable_ecosystems
"""


async def assurance_coverage(
    database: SupportsFetch, *, tenant_id: UUID | None,
) -> AskResponse:
    """Report analytical coverage of the estate, one scan dimension per row."""
    row = await database.fetch_one(
        _ASSURANCE_COVERAGE_SQL,
        {"tenant_id": tenant_id, "freshness_fallback_days": FRESHNESS_FALLBACK_DAYS},
        tenant_id=tenant_id,
    ) or {}
    repositories = _int(row.get("repositories"))
    if repositories == 0:
        # No repository has reached the estate yet, so there is nothing to score.
        # An empty table keeps this apart from a healthy, fully covered estate.
        return AskResponse(
            text=(
                "No repositories have reached the estate yet, so analytical coverage "
                "cannot be scored. Connect a source and complete one scan first."
            ),
            citations=[], result_kind="TABLE", rows=[],
        )

    covered = _int(row.get("covered_repositories"))
    facts = _int(row.get("facts"))
    connectors = _int(row.get("connectors"))
    unsupported_ecosystems = str(row.get("unsupported_ecosystems") or "")
    analyzable_ecosystems = str(row.get("analyzable_ecosystems") or "")

    rows: list[dict[str, Any]] = [_coverage_row(
        "Analytically covered estate", "Repositories", covered, repositories,
        detail=(
            "Repositories that are scanned, fresh, free of unanalyzable ecosystems, "
            "backed by evidence, and reachable."
        ),
    )]
    rows.append(_coverage_row(
        "Scan freshness", "Repositories", _int(row.get("fresh_repositories")), repositories,
        detail=(
            "Connector freshness state is FRESH and not past its expected refresh; "
            f"repositories without a freshness record fall back to activity in the last "
            f"{FRESHNESS_FALLBACK_DAYS} days."
        ),
    ))
    ecosystem_covered = _int(row.get("ecosystem_supported_repositories"))
    rows.append(_coverage_row(
        "Analyzable ecosystems", "Repositories", ecosystem_covered, repositories,
        status=("UNSUPPORTED" if ecosystem_covered < repositories and unsupported_ecosystems
                else None),
        detail=(
            f"Analyzable: {analyzable_ecosystems or 'none admitted'}. "
            + (f"Not yet analyzable: {unsupported_ecosystems}."
               if unsupported_ecosystems else "No dependency sits outside an analyzable ecosystem.")
        ),
    ))
    rows.append(_coverage_row(
        "Evidence completeness", "Current facts", _int(row.get("evidenced_facts")), facts,
        detail="Current facts that carry at least one evidence locator.",
    ))
    rows.append(_coverage_row(
        "Connector health", "Connectors", _int(row.get("healthy_connectors")), connectors,
        detail=(
            "Connectors reporting CONNECTED without a recorded error."
            if connectors else "No connector is registered for this workspace."
        ),
    ))
    rows.append(_coverage_row(
        "Repository availability", "Repositories", _int(row.get("available_repositories")),
        repositories,
        detail=(
            "Repositories whose ingest target is enabled and unarchived, with no failed "
            "run since the last success and no errored freshness state."
        ),
    ))
    rows.append(_coverage_row(
        "Published source snapshots", "Repositories",
        _int(row.get("source_snapshotted_repositories")), repositories,
        detail="Repositories backed by a published immutable source snapshot.",
    ))
    open_dead_letters = _int(row.get("open_dead_letters"))
    rows.append(_coverage_row(
        "Dead-letter backlog", "Ingestion queue", int(open_dead_letters == 0), 1,
        detail=(
            "No unreplayed ingestion failures remain in the dead-letter queue."
            if open_dead_letters == 0 else
            f"{open_dead_letters} ingestion failures remain unreplayed in the dead-letter queue."
        ),
    ))
    quota_providers = _int(row.get("quota_providers"))
    rows.append(_coverage_row(
        "Connector quota", "Providers", _int(row.get("healthy_quota_providers")),
        quota_providers,
        detail=(
            "Observed providers are neither throttled, exhausted, nor under backoff."
            if quota_providers else "No provider quota state has been observed yet."
        ),
    ))

    percent = rows[0]["coverage_percent"]
    return AskResponse(
        text=(
            f"{percent}% of the {repositories} repositories in this estate are analytically "
            "covered. Scan freshness, analyzable ecosystems, evidence completeness, connector "
            "health, repository availability, published snapshots, dead-letter backlog, and "
            "provider quota are scored separately so a gap can be "
            "attributed to the dimension that caused it."
        ),
        citations=[], result_kind="TABLE", rows=rows,
    )


def _coverage_row(
    dimension: str, scope: str, covered: int, in_scope: int, *,
    detail: str, status: str | None = None,
) -> dict[str, Any]:
    percent = round(covered * 100 / in_scope, 1) if in_scope else 0.0
    resolved = status or (
        "NOT_EVALUATED" if in_scope == 0
        else "COVERED" if covered >= in_scope
        else "GAP" if covered == 0
        else "PARTIAL"
    )
    return {
        "dimension": dimension, "scope": scope, "covered": covered, "in_scope": in_scope,
        "coverage_percent": int(percent) if percent.is_integer() else percent,
        "status": resolved, "detail": detail,
    }


def assurance_report_presentation(rows: list[Mapping[str, Any]]) -> tuple[str, str] | None:
    """Derive H1's headline metric and card status from its own scan rows."""
    if not rows:
        return None
    headline = rows[0]
    statuses = [str(row.get("status")) for row in rows[1:]]
    actionable = {
        str(row.get("dimension")) for row in rows[1:]
        if str(row.get("status")) in {"GAP", "PARTIAL"}
        and str(row.get("dimension")) in {
            "Connector health", "Repository availability", "Published source snapshots",
            "Dead-letter backlog", "Connector quota",
        }
    }
    if actionable:
        status = "ACTION_REQUIRED"
    elif any(value in {"GAP", "PARTIAL", "UNSUPPORTED"} for value in statuses):
        status = "WATCH"
    else:
        status = "HEALTHY"
    return f"{headline.get('coverage_percent')}%", status


# --- C1: technologies introduced -------------------------------------------

_TECHNOLOGY_INTRODUCTION_SQL = """
WITH repository_fact AS (
  SELECT fact.id fact_id,fact.object_entity_id technology_id,
         fact.subject_entity_id repository_id,fact.observed_at
  FROM fact_assertion fact
  JOIN entity repository ON repository.id=fact.subject_entity_id
   AND repository.namespace='ENTERPRISE' AND repository.entity_type='Repository'
  WHERE fact.tenant_id=%(tenant_id)s
    AND fact.predicate IN ('DEPENDS_ON','USES','RUNS_ON')
    AND fact.object_entity_id IS NOT NULL
    AND fact.system_to IS NULL
), introduction AS (
  SELECT DISTINCT ON (technology.id)
         technology.id technology_id,technology.first_seen_at,
         repository_fact.fact_id,repository_fact.repository_id
  FROM entity technology
  JOIN repository_fact ON repository_fact.technology_id=technology.id
  WHERE (technology.tenant_id IS NULL OR technology.tenant_id=%(tenant_id)s)
    AND technology.namespace IN ('TECHNOLOGY','OSS')
    AND technology.first_seen_at>=now()-make_interval(days=>%(window_days)s)
  ORDER BY technology.id,repository_fact.observed_at,
           repository_fact.repository_id,repository_fact.fact_id
)
SELECT technology.name technology,technology.entity_type technology_kind,
       repository.name repository,introduction.first_seen_at,
       introduction.fact_id,
       coalesce(
         (SELECT min(evidence.observed_at) FROM evidence
           WHERE evidence.fact_assertion_id=introduction.fact_id),
         introduction.first_seen_at
       ) evidence_observed_at,
       (SELECT count(DISTINCT spread.repository_id)::integer
          FROM repository_fact spread
         WHERE spread.technology_id=introduction.technology_id) repositories,
       count(*) OVER()::integer total_count
FROM introduction
JOIN entity technology ON technology.id=introduction.technology_id
JOIN entity repository ON repository.id=introduction.repository_id
ORDER BY introduction.first_seen_at DESC,technology.name
LIMIT %(row_limit)s
"""


async def technology_introduction(
    database: SupportsFetch, *, tenant_id: UUID | None,
) -> AskResponse:
    """List technologies whose first repository observation falls inside the window."""
    rows = await database.fetch_all(
        _TECHNOLOGY_INTRODUCTION_SQL,
        {
            "tenant_id": tenant_id,
            "window_days": TECHNOLOGY_INTRODUCTION_WINDOW_DAYS,
            "row_limit": ROW_LIMIT,
        },
        tenant_id=tenant_id,
    )
    citations = [Citation(
        fact_id=row["fact_id"],
        label=f"First seen · {row['technology']}",
        href=f"/api/v1/facts/{row['fact_id']}/evidence",
    ) for row in rows if row.get("fact_id")]
    result_rows = [{
        "technology": row["technology"],
        "kind": row["technology_kind"],
        "first_repository": row["repository"],
        "first_seen_at": _timestamp(row["first_seen_at"]),
        "evidence_observed_at": _timestamp(row["evidence_observed_at"]),
        "repositories": _int(row.get("repositories")),
        "total_count": _int(row.get("total_count")),
    } for row in rows]
    total_count = _int(rows[0].get("total_count")) if rows else 0
    return AskResponse(
        text=(
            f"{total_count} technolog{'y was' if total_count == 1 else 'ies were'} "
            f"first seen in the estate within the last {TECHNOLOGY_INTRODUCTION_WINDOW_DAYS} "
            f"days. {'The top 50 are shown. ' if total_count > len(result_rows) else ''}"
            "Each introduction is attributed to its earliest current repository fact and evidence."
            if result_rows else
            f"No technology was first seen in the estate in the last "
            f"{TECHNOLOGY_INTRODUCTION_WINDOW_DAYS} days. Everything currently in the graph "
            "was already present before that window."
        ),
        citations=citations, result_kind="TABLE", rows=result_rows,
    )


# --- G1: dark business capabilities ----------------------------------------

_BUSINESS_DARK_CAPABILITY_SQL = """
SELECT map.map_key business_map_key,map.title business_map,lane.label lane,
       business_function.name business_function,process.name business_process,
       capability.capability_key,capability.name capability,
       capability.criticality::integer criticality,capability.owner,
       placement.maturity::integer maturity,count(*) OVER()::integer total_count
FROM business_map_capability capability
JOIN business_map map ON map.id=capability.business_map_id
JOIN business_map_process process ON process.id=capability.business_map_process_id
JOIN business_map_function business_function
  ON business_function.id=process.business_map_function_id
LEFT JOIN LATERAL (
  SELECT candidate.maturity,candidate.lane_id
  FROM business_map_placement candidate
  WHERE candidate.business_map_capability_id=capability.id
  ORDER BY candidate.updated_at DESC,candidate.id
  LIMIT 1
) placement ON true
LEFT JOIN business_map_lane lane ON lane.id=placement.lane_id
WHERE capability.tenant_id=%(tenant_id)s
  AND map.status='ACTIVE'
  AND capability.criticality>=%(minimum_criticality)s
  AND NOT EXISTS (
    SELECT 1 FROM business_map_application_assignment assignment
    WHERE assignment.business_map_capability_id=capability.id
  )
ORDER BY capability.criticality DESC,map.title,business_function.name,capability.name
LIMIT %(row_limit)s
"""


async def business_dark_capability(
    database: SupportsFetch, *, tenant_id: UUID | None,
) -> AskResponse:
    """Find governed, high-criticality capabilities with no application assigned."""
    rows = await database.fetch_all(
        _BUSINESS_DARK_CAPABILITY_SQL,
        {
            "tenant_id": tenant_id,
            "minimum_criticality": DARK_CAPABILITY_MINIMUM_CRITICALITY,
            "row_limit": ROW_LIMIT,
        },
        tenant_id=tenant_id,
    )
    result_rows = [{
        "capability": row["capability"],
        "criticality": _int(row.get("criticality")),
        "maturity": _int(row.get("maturity")),
        "business_map": row["business_map"],
        "lane": row.get("lane") or "—",
        "business_function": row["business_function"],
        "business_process": row["business_process"],
        "owner": row.get("owner") or "unassigned",
        "business_map_key": row["business_map_key"],
        "capability_key": row["capability_key"],
        "total_count": _int(row.get("total_count")),
    } for row in rows]
    total_count = _int(rows[0].get("total_count")) if rows else 0
    return AskResponse(
        text=(
            f"{total_count} governed capabilit"
            f"{'y is' if total_count == 1 else 'ies are'} rated criticality "
            f"{DARK_CAPABILITY_MINIMUM_CRITICALITY} or higher on an active business map with no "
            f"application assigned. {'The top 50 are shown. ' if total_count > len(result_rows) else ''}"
            "These are curated map decisions, so they carry "
            "business-map context instead of fact citations."
            if result_rows else
            f"Every governed capability rated criticality "
            f"{DARK_CAPABILITY_MINIMUM_CRITICALITY} or higher on an active business map has at "
            "least one application assigned to it."
        ),
        # Business Map assignments are curated records, not fact assertions, so
        # there is no evidence to cite and none is manufactured.
        citations=[], result_kind="TABLE", rows=result_rows,
    )


# --- C3: decision implementation lag ---------------------------------------

_DECISION_LAG_SQL = """
SELECT recommendation.title,recommendation.action,
       recommendation.objective,recommendation.estimated_effort,
       current_support.current_supporting_fact_ids supporting_fact_ids,
       repository.name repository,
       accepted.accepted_at,
       floor(extract(epoch FROM now()-accepted.accepted_at)/86400)::integer days_since_acceptance
FROM modernization_recommendation recommendation
JOIN entity repository ON repository.id=recommendation.repository_entity_id
JOIN LATERAL (
  SELECT min(review.reviewed_at) accepted_at
  FROM modernization_recommendation_review review
  WHERE review.modernization_recommendation_id=recommendation.id AND review.decision='ACCEPT'
) accepted ON accepted.accepted_at IS NOT NULL
JOIN LATERAL (
  SELECT array_agg(fact.id ORDER BY fact.id) current_supporting_fact_ids
  FROM fact_assertion fact
  WHERE fact.id=ANY(recommendation.supporting_fact_ids) AND fact.system_to IS NULL
) current_support ON cardinality(current_support.current_supporting_fact_ids)>0
WHERE recommendation.tenant_id=%(tenant_id)s
  AND recommendation.review_state='ACCEPTED'
  AND recommendation.stale_at IS NULL
  AND accepted.accepted_at<=now()-make_interval(days=>%(threshold_days)s)
  AND NOT EXISTS (
    SELECT 1 FROM modernization_validation_outcome outcome
    WHERE outcome.modernization_recommendation_id=recommendation.id
  )
ORDER BY accepted.accepted_at,recommendation.title
LIMIT %(row_limit)s
"""


async def decision_lag(
    database: SupportsFetch, *, tenant_id: UUID | None,
) -> AskResponse:
    """Accepted, still-current decisions that never reported a validation outcome."""
    rows = await database.fetch_all(
        _DECISION_LAG_SQL,
        {
            "tenant_id": tenant_id,
            "threshold_days": DECISION_LAG_THRESHOLD_DAYS,
            "row_limit": ROW_LIMIT,
        },
        tenant_id=tenant_id,
    )
    citations: list[Citation] = []
    seen: set[UUID] = set()
    for row in rows:
        for fact_id in (row.get("supporting_fact_ids") or [])[:5]:
            if fact_id in seen:
                continue
            seen.add(fact_id)
            citations.append(Citation(
                fact_id=fact_id,
                label=f"Accepted decision · {row['title']}",
                href=f"/api/v1/facts/{fact_id}/evidence",
            ))
    result_rows = [{
        "decision": row["title"],
        "action": row["action"],
        "repository": row["repository"],
        "accepted_at": _timestamp(row["accepted_at"]),
        "days_since_acceptance": _int(row.get("days_since_acceptance")),
        "estimated_effort": row["estimated_effort"],
        "objective": row["objective"],
    } for row in rows]
    return AskResponse(
        text=(
            f"{len(result_rows)} accepted decision"
            f"{'' if len(result_rows) == 1 else 's'} passed "
            f"{DECISION_LAG_THRESHOLD_DAYS} days without a reported validation outcome while "
            "at least one supporting fact remains current."
            if result_rows else
            f"No accepted decision has been waiting longer than "
            f"{DECISION_LAG_THRESHOLD_DAYS} days without a reported validation outcome."
        ),
        citations=citations, result_kind="TABLE", rows=result_rows,
    )


# --- readiness --------------------------------------------------------------

_READINESS_SQL = """
SELECT
  EXISTS(
    SELECT 1 FROM entity
    WHERE entity.tenant_id=%(tenant_id)s
      AND entity.namespace='ENTERPRISE' AND entity.entity_type='Repository'
  ) estate_observed,
  EXISTS(
    SELECT 1 FROM fact_assertion fact
    JOIN entity repository ON repository.id=fact.subject_entity_id
     AND repository.namespace='ENTERPRISE' AND repository.entity_type='Repository'
    WHERE fact.tenant_id=%(tenant_id)s
      AND fact.predicate IN ('DEPENDS_ON','USES','RUNS_ON')
  ) technology_observed,
  EXISTS(
    SELECT 1 FROM business_map_capability capability
    JOIN business_map map ON map.id=capability.business_map_id
    WHERE capability.tenant_id=%(tenant_id)s AND map.status='ACTIVE'
      AND capability.criticality>=%(minimum_criticality)s
  ) critical_capability_governed,
  EXISTS(
    SELECT 1 FROM modernization_recommendation recommendation
    WHERE recommendation.tenant_id=%(tenant_id)s AND recommendation.review_state='ACCEPTED'
  ) decision_accepted
"""


async def posture_report_readiness(
    database: SupportsFetch, *, tenant_id: UUID | None,
) -> dict[str, bool]:
    """Separate a defensible empty report from one that has nothing to look at."""
    row = await database.fetch_one(
        _READINESS_SQL,
        {
            "tenant_id": tenant_id,
            "minimum_criticality": DARK_CAPABILITY_MINIMUM_CRITICALITY,
        },
        tenant_id=tenant_id,
    ) or {}
    return {
        ASSURANCE_COVERAGE: bool(row.get("estate_observed")),
        TECHNOLOGY_INTRODUCTION: bool(row.get("technology_observed")),
        BUSINESS_DARK_CAPABILITY: bool(row.get("critical_capability_governed")),
        DECISION_LAG: bool(row.get("decision_accepted")),
    }


def _int(value: Any) -> int:
    if isinstance(value, bool) or value is None:
        return 0
    if isinstance(value, (int, float, Decimal)):
        return int(value)
    return 0


def _timestamp(value: Any) -> str | None:
    return value.isoformat() if hasattr(value, "isoformat") else value
