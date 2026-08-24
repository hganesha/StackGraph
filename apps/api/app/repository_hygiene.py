from __future__ import annotations

from typing import Any, Mapping
from uuid import UUID


REPOSITORY_HYGIENE_RULE_CATALOG: tuple[Mapping[str, Any], ...] = (
    {
        "key": "repository.missing-readme",
        "name": "Missing README",
        "phase": 1,
        "description": "Repositories whose complete default-branch scan has no root README.",
        "severity": "MEDIUM",
        "readiness": "ACTIVE",
        "missing": ("README quality and freshness are not evaluated.",),
    },
    {
        "key": "repository.missing-license",
        "name": "Missing license",
        "phase": 1,
        "description": "Repositories whose complete default-branch scan has no root license file.",
        "severity": "LOW",
        "readiness": "ACTIVE",
        "missing": ("Repository visibility and organization-wide licensing are not evaluated.",),
    },
    {
        "key": "repository.missing-codeowners",
        "name": "Missing CODEOWNERS",
        "phase": 1,
        "description": "Repositories with no CODEOWNERS file in a supported GitHub location.",
        "severity": "LOW",
        "readiness": "ACTIVE",
        "missing": ("Ownership configured outside the repository is not observed.",),
    },
    {
        "key": "repository.missing-ci",
        "name": "Missing CI configuration",
        "phase": 1,
        "description": "Repositories with no recognized in-repository CI configuration.",
        "severity": "MEDIUM",
        "readiness": "ACTIVE",
        "missing": ("CI configured entirely outside the repository is not observed.",),
    },
    {
        "key": "dependency.missing-lockfile",
        "name": "Missing dependency lockfile",
        "phase": 1,
        "description": (
            "Repository components that declare dependencies without a recognized ecosystem lockfile."
        ),
        "severity": "MEDIUM",
        "readiness": "ACTIVE",
        "missing": ("Library projects may intentionally avoid committing a lockfile.",),
    },
    {
        "key": "testing.missing-tests",
        "name": "Missing tests",
        "phase": 1,
        "description": "Repositories with source files but no recognized tests or test configuration.",
        "severity": "MEDIUM",
        "readiness": "ACTIVE",
        "missing": ("Tests stored or executed outside the repository are not observed.",),
    },
)


_RULES: tuple[Mapping[str, str], ...] = (
    {
        "key": "repository.missing-readme",
        "profile_key": "readme",
        "kind": "MISSING_README",
        "title_suffix": "has no root README",
        "summary": "The complete repository scan did not find a root README file.",
        "recommendation_title": "Add a repository README",
        "recommendation_rationale": (
            "Document the repository purpose, ownership, local setup, and primary operational workflow."
        ),
        "effort": "LOW",
        "applicability": "",
    },
    {
        "key": "repository.missing-license",
        "profile_key": "license",
        "kind": "MISSING_LICENSE",
        "title_suffix": "has no root license file",
        "summary": "The complete repository scan did not find LICENSE or COPYING at the root.",
        "recommendation_title": "Declare the repository license",
        "recommendation_rationale": (
            "Add the approved license text or record why licensing is governed elsewhere."
        ),
        "effort": "LOW",
        "applicability": "",
    },
    {
        "key": "repository.missing-codeowners",
        "profile_key": "codeowners",
        "kind": "MISSING_CODEOWNERS",
        "title_suffix": "has no CODEOWNERS file",
        "summary": "The complete repository scan did not find CODEOWNERS in a supported location.",
        "recommendation_title": "Declare repository ownership",
        "recommendation_rationale": (
            "Add CODEOWNERS at the root, in .github, or in docs so review ownership is explicit."
        ),
        "effort": "LOW",
        "applicability": "",
    },
    {
        "key": "repository.missing-ci",
        "profile_key": "ci",
        "kind": "MISSING_CI_CONFIGURATION",
        "title_suffix": "has no recognized CI configuration",
        "summary": "The complete repository scan did not find a recognized CI configuration.",
        "recommendation_title": "Add or document continuous integration",
        "recommendation_rationale": (
            "Add a supported CI workflow or document the external pipeline that validates changes."
        ),
        "effort": "MEDIUM",
        "applicability": "",
    },
    {
        "key": "dependency.missing-lockfile",
        "profile_key": "dependency_lockfile",
        "kind": "MISSING_DEPENDENCY_LOCKFILE",
        "title_suffix": "has an unlocked dependency component",
        "summary": "At least one dependency-bearing component has no recognized lockfile.",
        "recommendation_title": "Commit the ecosystem lockfile",
        "recommendation_rationale": (
            "Generate and commit the appropriate lockfile, or document why this component "
            "must remain unlocked."
        ),
        "effort": "LOW",
        "applicability": (
            "AND (profile.value->'hygiene'->'dependency_lockfile'->>'applicable')::boolean "
            "IS TRUE"
        ),
    },
    {
        "key": "testing.missing-tests",
        "profile_key": "tests",
        "kind": "MISSING_TESTS",
        "title_suffix": "has source code but no recognized tests",
        "summary": "The complete repository scan found source code but no tests or test configuration.",
        "recommendation_title": "Add an executable test baseline",
        "recommendation_rationale": (
            "Add a focused test suite and its runner configuration for the primary behavior."
        ),
        "effort": "MEDIUM",
        "applicability": "AND (profile.value->'hygiene'->'tests'->>'applicable')::boolean IS TRUE",
    },
)


def repository_hygiene_queries(
    tenant_id: UUID | None,
) -> tuple[tuple[str, str, tuple[Any, ...]], ...]:
    return tuple(
        (str(rule["key"]), _rule_sql(rule), (tenant_id,))
        for rule in _RULES
    )


def _rule_sql(rule: Mapping[str, str]) -> str:
    # All interpolated values come from the closed catalog above, never from tenant input.
    return f"""
WITH profile AS (
  SELECT fact.id fact_id,fact.tenant_id,fact.subject_entity_id repository_id,
         repository.name repository_name,repository.canonical_key repository_key,
         fact.object_value value,fact.observed_at
  FROM fact_assertion fact
  JOIN source_snapshot snapshot ON snapshot.id=fact.source_snapshot_id
    AND snapshot.status='PUBLISHED' AND snapshot.completeness='COMPLETE'
  JOIN entity repository ON repository.id=fact.subject_entity_id
    AND repository.namespace='ENTERPRISE' AND repository.entity_type='Repository'
  WHERE fact.tenant_id=%s AND fact.predicate='HAS_PROPERTY' AND fact.system_to IS NULL
    AND fact.object_value->>'record_kind'='repository_profile'
)
SELECT profile.repository_id subject_id,'Repository' subject_kind,
       profile.repository_name subject_name,profile.repository_key subject_key,
       '{rule["kind"]}' kind,
       profile.repository_name||' {rule["title_suffix"]}' title,
       '{rule["summary"]}' summary,
       1::integer present,0::integer referenced,0::integer reachable,0::integer runtime,
       count(DISTINCT deployment.object_entity_id)::integer deployed,
       count(DISTINCT application.subject_entity_id)::integer applications,
       ARRAY[profile.repository_id]::uuid[]||
         array_remove(array_agg(DISTINCT application.subject_entity_id),NULL)||
         array_remove(array_agg(DISTINCT deployment.object_entity_id),NULL) scope_ids,
       jsonb_build_array(jsonb_build_object(
         'id',profile.repository_id,'kind','Repository','name',profile.repository_name,
         'canonical_key',profile.repository_key
       )) repositories,
       ARRAY[profile.fact_id]::uuid[] fact_ids,profile.observed_at detected_at,
       'INVESTIGATE' action,'{rule["recommendation_title"]}' recommendation_title,
       '{rule["recommendation_rationale"]}' recommendation_rationale,
       '{rule["effort"]}' effort,
       ARRAY['Only files admitted by the repository scanner are evaluated.']::text[] missing_inputs,
       0::integer coverage_penalty
FROM profile
LEFT JOIN fact_assertion application
  ON application.object_entity_id=profile.repository_id
 AND application.predicate='IMPLEMENTED_BY' AND application.system_to IS NULL
 AND application.tenant_id=profile.tenant_id
LEFT JOIN fact_assertion deployment
  ON deployment.subject_entity_id=profile.repository_id
 AND deployment.predicate='DEPLOYED_AS' AND deployment.system_to IS NULL
 AND deployment.tenant_id=profile.tenant_id
WHERE (profile.value->'hygiene'->'{rule["profile_key"]}'->>'present')::boolean IS FALSE
  {rule["applicability"]}
GROUP BY profile.repository_id,profile.repository_name,profile.repository_key,
         profile.fact_id,profile.observed_at
"""
