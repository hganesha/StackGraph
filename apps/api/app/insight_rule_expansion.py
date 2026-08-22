from __future__ import annotations

from typing import Any, Mapping
from uuid import UUID


DEFAULT_STRONG_COPYLEFT_LICENSES = (
    "AGPL-3.0-only",
    "AGPL-3.0-or-later",
    "GPL-2.0-only",
    "GPL-2.0-or-later",
    "GPL-3.0-only",
    "GPL-3.0-or-later",
    "SSPL-1.0",
)


EXPANDED_RULE_CATALOG: tuple[Mapping[str, Any], ...] = (
    {
        "key": "supplychain.dependency-confusion",
        "name": "Dependency confusion exposure",
        "phase": 1,
        "description": (
            "npm dependencies whose private registry identity or scope routing can be answered "
            "by the public npm registry."
        ),
        "severity": "CRITICAL",
        "readiness": "ACTIVE",
        "missing": (
            "Python and other package ecosystems are not evaluated by this rule.",
            "Registry-name collision coverage is limited to registry identities already ingested.",
        ),
        "configuration": {"ecosystem": "NPM"},
    },
    {
        "key": "oss.license-obligation",
        "name": "License obligation exposure",
        "phase": 1,
        "description": (
            "Resolved dependencies outside the active license allow-list, or carrying a "
            "conservative strong-copyleft classification when no allow-list exists."
        ),
        "severity": "HIGH",
        "readiness": "ACTIVE",
        "missing": (
            "License compatibility and distribution obligations require legal review.",
        ),
        "configuration": {
            "strong_copyleft_licenses": list(DEFAULT_STRONG_COPYLEFT_LICENSES),
        },
    },
    {
        "key": "code.cross-repository-clone",
        "name": "Cross-repository structural clone",
        "phase": 1,
        "description": (
            "Structurally identical non-vendored code units repeated across distinct repositories."
        ),
        "severity": "HIGH",
        "readiness": "ACTIVE",
        "minimum_repositories": 2,
        "missing": (
            "Structural identity does not by itself establish behavioral or business equivalence.",
        ),
        "configuration": {"minimum_lines": 6},
    },
    {
        "key": "code.vendored-third-party",
        "name": "Vendored source outside dependency management",
        "phase": 1,
        "description": (
            "Scanner-classified vendored source stored in-tree and outside manifest-level "
            "dependency governance."
        ),
        "severity": "HIGH",
        "readiness": "ACTIVE",
        "missing": (
            "Vendored path classification does not establish third-party origin or upstream version.",
        ),
        "configuration": {"minimum_vendored_units": 1},
    },
)


_DEPENDENCY_CONTEXT_CTE = """
WITH dependency_context AS (
  SELECT fact.id fact_id,fact.tenant_id,fact.subject_entity_id repository_id,
         repository.name repository_name,fact.object_entity_id dependency_id,
         dependency.name dependency_name,dependency.entity_type dependency_kind,
         dependency.canonical_key dependency_key,
         resolution.resolution_source,resolution.resolved_version,resolution.npm_scope,
         resolution.visibility resolution_visibility,resolution.custom_registry,
         resolution.package_registry_id,
         coalesce(usage.referenced,false) referenced,
         coalesce(usage.static_reachability,'UNKNOWN') static_reachability,
         coalesce(usage.runtime_observed,'UNKNOWN') runtime_observed,
         application.subject_entity_id application_id,
         deployment.object_entity_id deployment_id,
         fact.observed_at
  FROM dependency_resolution resolution
  JOIN fact_assertion fact ON fact.id=resolution.fact_assertion_id
    AND fact.system_to IS NULL AND fact.predicate='DEPENDS_ON'
  JOIN entity repository ON repository.id=fact.subject_entity_id
    AND repository.namespace='ENTERPRISE' AND repository.entity_type='Repository'
  JOIN entity dependency ON dependency.id=fact.object_entity_id
    AND dependency.entity_type IN ('Package','PackageVersion')
  JOIN package_registry registry ON registry.id=resolution.package_registry_id
    AND registry.ecosystem='NPM'
  LEFT JOIN dependency_usage_summary usage
    ON usage.dependency_fact_assertion_id=fact.id
  LEFT JOIN fact_assertion application
    ON application.object_entity_id=repository.id
   AND application.predicate='IMPLEMENTED_BY' AND application.system_to IS NULL
   AND application.tenant_id=fact.tenant_id
   AND EXISTS (
     SELECT 1 FROM entity application_entity
     WHERE application_entity.id=application.subject_entity_id
       AND application_entity.namespace='ENTERPRISE'
       AND application_entity.entity_type='Application'
   )
  LEFT JOIN fact_assertion deployment
    ON deployment.subject_entity_id=repository.id
   AND deployment.predicate='DEPLOYED_AS' AND deployment.system_to IS NULL
   AND deployment.tenant_id=fact.tenant_id
  WHERE resolution.tenant_id=%s
)
"""


_DEPENDENCY_CONFUSION_SQL = _DEPENDENCY_CONTEXT_CTE + """
, candidate AS (
  SELECT context.*,
         coalesce(identity.package_name,context.dependency_name) package_name
  FROM dependency_context context
  LEFT JOIN package_registry_identity identity
    ON identity.entity_id=context.dependency_id
   AND (identity.tenant_id IS NULL OR identity.tenant_id=context.tenant_id)
   AND (context.resolved_version IS NULL OR identity.package_version=context.resolved_version)
  WHERE (
    context.resolution_visibility='PRIVATE'
    AND EXISTS (
      SELECT 1
      FROM package_registry_identity public_identity
      JOIN package_registry public_registry
        ON public_registry.id=public_identity.package_registry_id
       AND public_registry.ecosystem='NPM' AND public_registry.visibility='PUBLIC'
      WHERE lower(public_identity.package_name)=lower(
        coalesce(identity.package_name,context.dependency_name)
      )
        AND public_identity.visibility='PUBLIC'
        AND (public_identity.tenant_id IS NULL OR public_identity.tenant_id=context.tenant_id)
    )
  ) OR (
    context.npm_scope IS NOT NULL
    AND context.resolution_source='NPM_DEFAULT'
    AND EXISTS (
      SELECT 1
      FROM package_registry_scope scope
      JOIN package_registry scoped_registry ON scoped_registry.id=scope.package_registry_id
      WHERE scope.tenant_id=context.tenant_id
        AND scope.package_scope=context.npm_scope
        AND scoped_registry.visibility='PRIVATE'
    )
  )
)
SELECT candidate.dependency_id subject_id,candidate.dependency_kind subject_kind,
       candidate.package_name subject_name,candidate.dependency_key subject_key,
       'DEPENDENCY_CONFUSION' kind,
       candidate.package_name||' has ambiguous npm registry routing' title,
       count(DISTINCT candidate.repository_id)||
         ' repositories resolve a private package name or scope that the public registry can answer.' summary,
       count(DISTINCT candidate.repository_id)::integer present,
       count(DISTINCT candidate.repository_id) FILTER (WHERE candidate.referenced)::integer referenced,
       count(DISTINCT candidate.repository_id)
         FILTER (WHERE candidate.static_reachability='OBSERVED')::integer reachable,
       count(DISTINCT candidate.repository_id)
         FILTER (WHERE candidate.runtime_observed='OBSERVED')::integer runtime,
       count(DISTINCT candidate.deployment_id)::integer deployed,
       count(DISTINCT candidate.application_id)::integer applications,
       array_remove(array_agg(DISTINCT candidate.application_id),NULL)||
         array_remove(array_agg(DISTINCT candidate.deployment_id),NULL)||
         array_remove(array_agg(DISTINCT candidate.dependency_id),NULL) scope_ids,
       jsonb_agg(DISTINCT jsonb_build_object(
         'id',candidate.repository_id,'kind','Repository','name',candidate.repository_name
       )) repositories,
       array_agg(DISTINCT candidate.fact_id) fact_ids,max(candidate.observed_at) detected_at,
       'INVESTIGATE' action,'Pin private npm scopes to an approved registry' recommendation_title,
       'Verify the public-name collision, then enforce scoped registry routing and a defensive publication policy.' recommendation_rationale,
       'LOW' effort,
       ARRAY[
         'Only npm dependency resolution is evaluated by this rule.',
         'Public-name collision coverage is limited to registry identities already ingested.'
       ]::text[] missing_inputs,
       1::integer coverage_penalty
FROM candidate
GROUP BY candidate.dependency_id,candidate.dependency_kind,candidate.package_name,
         candidate.dependency_key
"""


_LICENSE_OBLIGATION_SQL = _DEPENDENCY_CONTEXT_CTE + """
, active_policy AS (
  SELECT policy.id,policy.allowed_licenses
  FROM modernization_policy policy
  WHERE policy.tenant_id=%s AND policy.status='ACTIVE'
  ORDER BY policy.activated_at DESC NULLS LAST,policy.updated_at DESC
  LIMIT 1
), licensed AS (
  SELECT context.*,metadata.id metadata_fact_id,license.value license,
         policy.id IS NOT NULL AND cardinality(policy.allowed_licenses)>0 policy_defined,
         policy.id IS NOT NULL AND cardinality(policy.allowed_licenses)>0
           AND NOT EXISTS (
             SELECT 1 FROM unnest(policy.allowed_licenses) allowed(value)
             WHERE lower(allowed.value)=lower(license.value)
           ) policy_violation,
         lower(license.value)=ANY(%s::text[]) strong_obligation
  FROM dependency_context context
  JOIN fact_assertion metadata
    ON metadata.subject_entity_id=context.dependency_id
   AND metadata.predicate='HAS_PROPERTY' AND metadata.system_to IS NULL
   AND (metadata.tenant_id IS NULL OR metadata.tenant_id=context.tenant_id)
   AND metadata.object_value->>'record_kind'='deps_dev_version_metadata'
  CROSS JOIN LATERAL jsonb_array_elements_text(
    CASE WHEN jsonb_typeof(metadata.object_value->'licenses')='array'
      THEN metadata.object_value->'licenses' ELSE '[]'::jsonb END
  ) license(value)
  LEFT JOIN active_policy policy ON true
  WHERE nullif(trim(license.value),'') IS NOT NULL
)
SELECT licensed.dependency_id subject_id,licensed.dependency_kind subject_kind,
       licensed.dependency_name subject_name,licensed.dependency_key subject_key,
       'LICENSE_OBLIGATION' kind,
       licensed.dependency_name||' requires license review' title,
       count(DISTINCT licensed.repository_id)||' repositories use this dependency under '||
         string_agg(DISTINCT licensed.license,', ' ORDER BY licensed.license)||'.' summary,
       count(DISTINCT licensed.repository_id)::integer present,
       count(DISTINCT licensed.repository_id) FILTER (WHERE licensed.referenced)::integer referenced,
       count(DISTINCT licensed.repository_id)
         FILTER (WHERE licensed.static_reachability='OBSERVED')::integer reachable,
       count(DISTINCT licensed.repository_id)
         FILTER (WHERE licensed.runtime_observed='OBSERVED')::integer runtime,
       count(DISTINCT licensed.deployment_id)::integer deployed,
       count(DISTINCT licensed.application_id)::integer applications,
       array_remove(array_agg(DISTINCT licensed.application_id),NULL)||
         array_remove(array_agg(DISTINCT licensed.deployment_id),NULL)||
         array_remove(array_agg(DISTINCT licensed.dependency_id),NULL) scope_ids,
       jsonb_agg(DISTINCT jsonb_build_object(
         'id',licensed.repository_id,'kind','Repository','name',licensed.repository_name
       )) repositories,
       array_agg(DISTINCT licensed.fact_id)||
         array_agg(DISTINCT licensed.metadata_fact_id) fact_ids,
       max(licensed.observed_at) detected_at,
       'INVESTIGATE' action,'Review the dependency license obligation' recommendation_title,
       'Confirm distribution obligations, record an exception, or replace the dependency with an approved option.' recommendation_rationale,
       'MEDIUM' effort,
       CASE WHEN bool_or(licensed.policy_defined)
         THEN ARRAY['License compatibility and distribution obligations require legal review.']::text[]
         ELSE ARRAY[
           'No active license allow-list is configured; conservative strong-copyleft defaults were used.',
           'License compatibility and distribution obligations require legal review.'
         ]::text[]
       END missing_inputs,
       CASE WHEN bool_or(licensed.policy_defined) THEN 0 ELSE 1 END::integer coverage_penalty
FROM licensed
WHERE licensed.policy_violation OR licensed.strong_obligation
GROUP BY licensed.dependency_id,licensed.dependency_kind,licensed.dependency_name,
         licensed.dependency_key
"""


_CROSS_REPOSITORY_CLONE_SQL = """
WITH clone_unit AS (
  SELECT unit.*,repository.name repository_name
  FROM code_implementation_summary unit
  JOIN entity repository ON repository.id=unit.repository_entity_id
    AND repository.namespace='ENTERPRISE' AND repository.entity_type='Repository'
  WHERE unit.tenant_id=%s AND NOT unit.vendored
    AND unit.line_end-unit.line_start+1>=%s
), repeated AS (
  SELECT structural_fingerprint
  FROM clone_unit
  GROUP BY structural_fingerprint
  HAVING count(DISTINCT repository_entity_id)>=2
), impacted AS (
  SELECT unit.*,application.subject_entity_id application_id,
         deployment.object_entity_id deployment_id
  FROM clone_unit unit
  JOIN repeated USING(structural_fingerprint)
  LEFT JOIN fact_assertion application
    ON application.object_entity_id=unit.repository_entity_id
   AND application.predicate='IMPLEMENTED_BY' AND application.system_to IS NULL
   AND application.tenant_id=unit.tenant_id
   AND EXISTS (
     SELECT 1 FROM entity application_entity
     WHERE application_entity.id=application.subject_entity_id
       AND application_entity.namespace='ENTERPRISE'
       AND application_entity.entity_type='Application'
   )
  LEFT JOIN fact_assertion deployment
    ON deployment.subject_entity_id=unit.repository_entity_id
   AND deployment.predicate='DEPLOYED_AS' AND deployment.system_to IS NULL
   AND deployment.tenant_id=unit.tenant_id
)
SELECT md5(impacted.structural_fingerprint)::uuid subject_id,'CodeClone' subject_kind,
       min(impacted.qualified_name)||' structural clone' subject_name,
       'code-clone:'||impacted.structural_fingerprint subject_key,
       'CROSS_REPOSITORY_CLONE' kind,
       'The same code structure appears in '||
         count(DISTINCT impacted.repository_entity_id)||' repositories' title,
       count(DISTINCT impacted.repository_entity_id)||' repositories contain '||
         count(DISTINCT impacted.id)||' code units with the same structural fingerprint.' summary,
       count(DISTINCT impacted.repository_entity_id)::integer present,
       count(DISTINCT impacted.repository_entity_id)::integer referenced,
       0::integer reachable,0::integer runtime,
       count(DISTINCT impacted.deployment_id)::integer deployed,
       count(DISTINCT impacted.application_id)::integer applications,
       array_remove(array_agg(DISTINCT impacted.repository_entity_id),NULL)||
         array_remove(array_agg(DISTINCT impacted.application_id),NULL)||
         array_remove(array_agg(DISTINCT impacted.deployment_id),NULL) scope_ids,
       jsonb_agg(DISTINCT jsonb_build_object(
         'id',impacted.repository_entity_id,'kind','Repository','name',impacted.repository_name
       )) repositories,
       array_agg(DISTINCT impacted.fact_assertion_id) fact_ids,
       max(impacted.created_at) detected_at,
       'CONSOLIDATE' action,'Evaluate a shared internal component' recommendation_title,
       'Confirm behavioral equivalence and ownership, then extract a governed reusable component where appropriate.' recommendation_rationale,
       'HIGH' effort,
       ARRAY[
         'Structural identity does not establish behavioral or business equivalence.',
         'Code-unit runtime execution is not observed.'
       ]::text[] missing_inputs,
       1::integer coverage_penalty
FROM impacted
GROUP BY impacted.structural_fingerprint
"""


_VENDORED_SOURCE_SQL = """
WITH impacted AS (
  SELECT unit.*,repository.name repository_name,
         application.subject_entity_id application_id,
         deployment.object_entity_id deployment_id
  FROM code_implementation_summary unit
  JOIN entity repository ON repository.id=unit.repository_entity_id
    AND repository.namespace='ENTERPRISE' AND repository.entity_type='Repository'
  LEFT JOIN fact_assertion application
    ON application.object_entity_id=unit.repository_entity_id
   AND application.predicate='IMPLEMENTED_BY' AND application.system_to IS NULL
   AND application.tenant_id=unit.tenant_id
   AND EXISTS (
     SELECT 1 FROM entity application_entity
     WHERE application_entity.id=application.subject_entity_id
       AND application_entity.namespace='ENTERPRISE'
       AND application_entity.entity_type='Application'
   )
  LEFT JOIN fact_assertion deployment
    ON deployment.subject_entity_id=unit.repository_entity_id
   AND deployment.predicate='DEPLOYED_AS' AND deployment.system_to IS NULL
   AND deployment.tenant_id=unit.tenant_id
  WHERE unit.tenant_id=%s AND unit.vendored
)
SELECT impacted.repository_entity_id subject_id,'Repository' subject_kind,
       impacted.repository_name subject_name,repository.canonical_key subject_key,
       'VENDORED_SOURCE_OUTSIDE_MANAGEMENT' kind,
       impacted.repository_name||' contains vendored source' title,
       count(DISTINCT impacted.id)||
         ' scanner-classified vendored code units are stored in-tree outside manifest-level dependency governance.' summary,
       1::integer present,1::integer referenced,0::integer reachable,0::integer runtime,
       count(DISTINCT impacted.deployment_id)::integer deployed,
       count(DISTINCT impacted.application_id)::integer applications,
       ARRAY[impacted.repository_entity_id]::uuid[]||
         array_remove(array_agg(DISTINCT impacted.application_id),NULL)||
         array_remove(array_agg(DISTINCT impacted.deployment_id),NULL) scope_ids,
       jsonb_build_array(jsonb_build_object(
         'id',impacted.repository_entity_id,'kind','Repository','name',impacted.repository_name
       )) repositories,
       array_agg(DISTINCT impacted.fact_assertion_id) fact_ids,
       max(impacted.created_at) detected_at,
       'INVESTIGATE' action,'Move vendored source under governed dependency management' recommendation_title,
       'Establish the upstream origin and version first, then replace the copied source with a patchable dependency where safe.' recommendation_rationale,
       'HIGH' effort,
       ARRAY[
         'Vendored path classification does not establish third-party origin or upstream version.',
         'Copied source is outside manifest-level vulnerability and release tracking.'
       ]::text[] missing_inputs,
       2::integer coverage_penalty
FROM impacted
JOIN entity repository ON repository.id=impacted.repository_entity_id
GROUP BY impacted.repository_entity_id,impacted.repository_name,repository.canonical_key
HAVING count(DISTINCT impacted.id)>=%s
"""


def expanded_rule_queries(
    tenant_id: UUID | None,
    policies: Mapping[str, Mapping[str, Any]],
) -> tuple[tuple[str, str, tuple[Any, ...]], ...]:
    license_configuration = policies["oss.license-obligation"]["configuration"]
    configured_licenses = license_configuration.get(
        "strong_copyleft_licenses", DEFAULT_STRONG_COPYLEFT_LICENSES,
    )
    strong_licenses = tuple(
        str(value).strip().lower()
        for value in configured_licenses
        if str(value).strip()
    ) or tuple(value.lower() for value in DEFAULT_STRONG_COPYLEFT_LICENSES)
    clone_minimum_lines = _bounded_integer(
        policies["code.cross-repository-clone"]["configuration"].get("minimum_lines"),
        default=6,
        minimum=2,
        maximum=500,
    )
    vendored_minimum_units = _bounded_integer(
        policies["code.vendored-third-party"]["configuration"].get(
            "minimum_vendored_units"
        ),
        default=1,
        minimum=1,
        maximum=1000,
    )
    return (
        (
            "supplychain.dependency-confusion",
            _DEPENDENCY_CONFUSION_SQL,
            (tenant_id,),
        ),
        (
            "oss.license-obligation",
            _LICENSE_OBLIGATION_SQL,
            (tenant_id, tenant_id, list(strong_licenses)),
        ),
        (
            "code.cross-repository-clone",
            _CROSS_REPOSITORY_CLONE_SQL,
            (tenant_id, clone_minimum_lines),
        ),
        (
            "code.vendored-third-party",
            _VENDORED_SOURCE_SQL,
            (tenant_id, vendored_minimum_units),
        ),
    )


def _bounded_integer(
    value: Any,
    *,
    default: int,
    minimum: int,
    maximum: int,
) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, min(maximum, parsed))
