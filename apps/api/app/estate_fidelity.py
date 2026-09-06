from __future__ import annotations

import hashlib
import re
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from app.errors import APIError
from app.models import (
    ComponentProfile,
    ContradictionClaim,
    ContradictionLedger,
    ContradictionLedgerItem,
    ContainerCompositionList,
    ContainerImageComposition,
    ContainerImageIdentity,
    ContainerLayer,
    ContainerPackage,
    DeploymentAction,
    DeploymentProfile,
    DeploymentProfileList,
    EntitySummary,
    EstateComponentDetail,
    EstateComponentList,
    EstateComponentSummary,
    EstateStrata,
    EstateStratumLayer,
    Freshness,
    GateReason,
    PageInfo,
)


_DIGEST = re.compile(r"sha256:[a-f0-9]{64}")
_LAYER_LABELS = {
    "BUSINESS": "Business",
    "ENTERPRISE": "Enterprise",
    "TECHNOLOGY": "Technology",
    "OSS": "OSS",
    "DEPLOYMENT": "Deployment",
}


def _properties(row: dict[str, Any]) -> dict[str, Any]:
    value = row.get("properties")
    return value if isinstance(value, dict) else {}


def _entity(row: dict[str, Any], prefix: str = "") -> EntitySummary:
    return EntitySummary(
        id=row[f"{prefix}id"],
        kind=row[f"{prefix}entity_type"],
        name=row[f"{prefix}name"],
        canonical_key=row.get(f"{prefix}canonical_key"),
        summary=row.get(f"{prefix}summary"),
    )


def _freshness(observed_at: datetime | None) -> Freshness:
    timestamp = observed_at or datetime.now(UTC)
    if observed_at is None:
        status = "UNKNOWN"
    elif datetime.now(UTC) - observed_at <= timedelta(days=30):
        status = "FRESH"
    else:
        status = "STALE"
    return Freshness(observed_at=timestamp, status=status)


def _confidence_label(value: float) -> str:
    if value >= 0.85:
        return "HIGH"
    if value >= 0.6:
        return "MEDIUM"
    return "LOW"


def _strings(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [item for item in value if isinstance(item, str) and item]
    return []


def _fact_ids(row: dict[str, Any]) -> list[UUID | str]:
    values: list[UUID | str] = []
    for key in ("fact_assertion_id", "evidence_fact_ids"):
        value = row.get(key)
        if value is not None and not isinstance(value, list):
            value = [value]
        if isinstance(value, list):
            values.extend(item for item in value if item)
    return list(dict.fromkeys(values))


class EstateFidelityMixin:
    """Typed S1-S3 read models over canonical entities and current facts.

    These methods deliberately return PARTIAL/NOT_COLLECTED instead of manufacturing
    scanner output. They can therefore ship before every scanner has learned the new
    profiles without teaching clients that missing data means an empty estate.
    """

    database: Any

    async def _repository(self, repository_id: UUID, tenant_id: UUID | None) -> dict[str, Any]:
        row = await self.database.fetch_one(
            """
            SELECT id,entity_type,name,canonical_key,properties->>'curated_description' summary
            FROM entity WHERE id=%s AND namespace='ENTERPRISE' AND entity_type='Repository'
            """,
            (repository_id,), tenant_id=tenant_id,
        )
        if row is None:
            raise APIError(404, "REPOSITORY_NOT_FOUND", "The repository was not found.")
        return row

    @staticmethod
    def _component_summary(row: dict[str, Any]) -> EstateComponentSummary:
        properties = {**_properties(row), **(row.get("typed_properties") or {})}
        confidence = float(properties.get("confidence") or row.get("relationship_confidence") or 0)
        component_path = properties.get("component_path") or properties.get("path")
        if component_path is None and "#" in str(row.get("canonical_key") or ""):
            component_path = str(row["canonical_key"]).split("#", 1)[1] or None
        classifications = _strings(
            properties.get("classifications", properties.get("classification")),
        )
        repository = None
        if row.get("repository_id") is not None:
            repository = _entity(row, "repository_")
        evidence = _fact_ids(row)
        limitations = []
        if component_path is None:
            limitations.append(GateReason(
                code="COMPONENT_PATH_NOT_COLLECTED",
                message="The component has canonical identity but no current repository path.",
                evidence_fact_ids=evidence,
            ))
        if not evidence:
            limitations.append(GateReason(
                code="COMPONENT_EVIDENCE_NOT_COLLECTED",
                message="The component has canonical identity but no current supporting relationship fact.",
            ))
        status = "AVAILABLE" if component_path and evidence else "PARTIAL"
        return EstateComponentSummary(
            component=_entity(row),
            repository=repository,
            profile=ComponentProfile(
                component_path=str(component_path) if component_path is not None else None,
                classifications=classifications,
                independently_deployable=(
                    properties.get("independently_deployable")
                    if isinstance(properties.get("independently_deployable"), bool)
                    else None
                ),
                runtime=properties.get("runtime") if isinstance(properties.get("runtime"), str) else None,
                status=status, confidence=confidence,
                confidence_label=_confidence_label(confidence),
                freshness=_freshness(row.get("observed_at")),
                evidence_fact_ids=evidence, limitations=limitations,
            ),
        )

    async def estate_components(
        self, *, tenant_id: UUID | None, cursor: UUID | None, limit: int,
    ) -> EstateComponentList:
        rows = await self.database.fetch_all(
            """
            SELECT component.id,component.entity_type,component.name,component.canonical_key,
                   component.properties,component.properties->>'curated_description' summary,
                   coalesce(profile.observed_at,component.last_seen_at) observed_at,
                   profile.typed_properties,profile.evidence_fact_ids,
                   repository.id repository_id,repository.entity_type repository_entity_type,
                   repository.name repository_name,repository.canonical_key repository_canonical_key,
                   repository.properties->>'curated_description' repository_summary,
                   repository_link.fact_assertion_id,
                   repository_link.confidence relationship_confidence
            FROM entity component
            LEFT JOIN LATERAL (
              SELECT profile.observed_at,
                     jsonb_build_object(
                       'component_path',profile.component_path,
                       'classifications',profile.classifications,
                       'independently_deployable',profile.independently_deployable,
                       'runtime',runtime.name,
                       'confidence',profile.confidence,
                       'method_version',profile.method_version,
                       'source_revision',profile.source_revision
                     )||profile.attributes typed_properties,
                     coalesce((SELECT array_agg(evidence.fact_assertion_id ORDER BY evidence.fact_assertion_id)
                       FROM estate_profile_evidence evidence
                       WHERE evidence.profile_kind='COMPONENT' AND evidence.profile_id=profile.id),'{}') evidence_fact_ids
              FROM estate_component_profile profile
              LEFT JOIN entity runtime ON runtime.id=profile.runtime_entity_id
              WHERE profile.component_entity_id=component.id AND profile.valid_to IS NULL
              ORDER BY profile.observed_at DESC,profile.id DESC LIMIT 1
            ) profile ON true
            LEFT JOIN LATERAL (
              SELECT related.*,edge.fact_assertion_id,edge.confidence
              FROM current_relationship edge
              JOIN entity related ON related.id=CASE
                WHEN edge.source_entity_id=component.id THEN edge.target_entity_id
                ELSE edge.source_entity_id END
              WHERE (edge.source_entity_id=component.id OR edge.target_entity_id=component.id)
                AND edge.relationship_type IN ('CONTAINS','IMPLEMENTS','IMPLEMENTED_BY')
                AND related.namespace='ENTERPRISE' AND related.entity_type='Repository'
              ORDER BY edge.confidence DESC,related.name,related.id LIMIT 1
            ) repository_link ON true
            LEFT JOIN entity repository ON repository.id=repository_link.id
            WHERE component.namespace='ENTERPRISE' AND component.entity_type='Component'
              AND (%s::uuid IS NULL OR component.id>%s::uuid)
            ORDER BY component.id LIMIT %s
            """,
            (cursor, cursor, limit + 1), tenant_id=tenant_id,
        )
        visible = rows[:limit]
        components = [self._component_summary(row) for row in visible]
        limitations: list[GateReason] = []
        if any(item.profile.status != "AVAILABLE" for item in components):
            limitations.append(GateReason(
                code="COMPONENT_EVIDENCE_PARTIAL",
                message="Some component profiles are missing a current path or supporting relationship fact.",
            ))
        return EstateComponentList(
            as_of=max(
                (item.profile.freshness.observed_at for item in components),
                default=datetime.now(UTC),
            ),
            components=components,
            page_info=PageInfo(
                has_next_page=len(rows) > limit,
                next_cursor=str(visible[-1]["id"]) if len(rows) > limit and visible else None,
            ),
            limitations=limitations,
        )

    async def component_detail(
        self, component_id: UUID, *, tenant_id: UUID | None,
    ) -> EstateComponentDetail:
        rows = await self.database.fetch_all(
            """
            SELECT component.id,component.entity_type,component.name,component.canonical_key,
                   component.properties,component.properties->>'curated_description' summary,
                   coalesce(profile.observed_at,component.last_seen_at) observed_at,
                   profile.typed_properties,profile.evidence_fact_ids,
                   repository.id repository_id,repository.entity_type repository_entity_type,
                   repository.name repository_name,repository.canonical_key repository_canonical_key,
                   repository.properties->>'curated_description' repository_summary,
                   repository_link.fact_assertion_id,
                   repository_link.confidence relationship_confidence
            FROM entity component
            LEFT JOIN LATERAL (
              SELECT profile.observed_at,
                     jsonb_build_object(
                       'component_path',profile.component_path,
                       'classifications',profile.classifications,
                       'independently_deployable',profile.independently_deployable,
                       'runtime',runtime.name,
                       'confidence',profile.confidence,
                       'method_version',profile.method_version,
                       'source_revision',profile.source_revision
                     )||profile.attributes typed_properties,
                     coalesce((SELECT array_agg(evidence.fact_assertion_id ORDER BY evidence.fact_assertion_id)
                       FROM estate_profile_evidence evidence
                       WHERE evidence.profile_kind='COMPONENT' AND evidence.profile_id=profile.id),'{}') evidence_fact_ids
              FROM estate_component_profile profile
              LEFT JOIN entity runtime ON runtime.id=profile.runtime_entity_id
              WHERE profile.component_entity_id=component.id AND profile.valid_to IS NULL
              ORDER BY profile.observed_at DESC,profile.id DESC LIMIT 1
            ) profile ON true
            LEFT JOIN LATERAL (
              SELECT related.*,edge.fact_assertion_id,edge.confidence
              FROM current_relationship edge
              JOIN entity related ON related.id=CASE
                WHEN edge.source_entity_id=component.id THEN edge.target_entity_id
                ELSE edge.source_entity_id END
              WHERE (edge.source_entity_id=component.id OR edge.target_entity_id=component.id)
                AND edge.relationship_type IN ('CONTAINS','IMPLEMENTS','IMPLEMENTED_BY')
                AND related.namespace='ENTERPRISE' AND related.entity_type='Repository'
              ORDER BY edge.confidence DESC,related.name,related.id LIMIT 1
            ) repository_link ON true
            LEFT JOIN entity repository ON repository.id=repository_link.id
            WHERE component.id=%s AND component.namespace='ENTERPRISE'
              AND component.entity_type='Component'
            """,
            (component_id,), tenant_id=tenant_id,
        )
        if not rows:
            raise APIError(404, "COMPONENT_NOT_FOUND", "The component was not found.")
        related = await self.database.fetch_all(
            """
            SELECT entity.id,entity.entity_type,entity.name,entity.canonical_key,
                   entity.properties->>'curated_description' summary,entity.namespace,
                   edge.fact_assertion_id
            FROM current_relationship edge
            JOIN entity ON entity.id=CASE
              WHEN edge.source_entity_id=%s THEN edge.target_entity_id
              ELSE edge.source_entity_id END
            WHERE edge.source_entity_id=%s OR edge.target_entity_id=%s
            ORDER BY entity.namespace,entity.entity_type,entity.name,entity.id
            """,
            (component_id, component_id, component_id), tenant_id=tenant_id,
        )
        summary = self._component_summary(rows[0])
        technologies = [
            _entity(row) for row in related if row["namespace"] in ("TECHNOLOGY", "OSS")
        ]
        deployments = [
            _entity(row) for row in related if row["entity_type"] == "Deployment"
        ]
        containers = [
            _entity(row) for row in related if row["entity_type"] == "ContainerImage"
        ]
        limitations = []
        if not related:
            limitations.append(GateReason(
                code="COMPONENT_RELATIONSHIPS_NOT_COLLECTED",
                message="No current technology, deployment, or container relationships were collected for this component.",
            ))
        return EstateComponentDetail(
            as_of=summary.profile.freshness.observed_at,
            component=summary,
            technologies=technologies,
            deployments=deployments,
            container_images=containers,
            limitations=limitations,
        )

    async def _repository_related_entities(
        self, repository_id: UUID, entity_type: str, tenant_id: UUID | None,
    ) -> list[dict[str, Any]]:
        return await self.database.fetch_all(
            """
            WITH first_hop AS (
              SELECT CASE WHEN edge.source_entity_id=%s THEN edge.target_entity_id
                          ELSE edge.source_entity_id END entity_id,
                     edge.fact_assertion_id,edge.confidence
              FROM current_relationship edge
              WHERE edge.source_entity_id=%s OR edge.target_entity_id=%s
            ), candidates AS (
              SELECT entity_id,fact_assertion_id,confidence FROM first_hop
              UNION ALL
              SELECT CASE WHEN edge.source_entity_id=first_hop.entity_id THEN edge.target_entity_id
                          ELSE edge.source_entity_id END,
                     edge.fact_assertion_id,least(first_hop.confidence,edge.confidence)
              FROM first_hop JOIN entity intermediate ON intermediate.id=first_hop.entity_id
              JOIN current_relationship edge ON
                (edge.source_entity_id=first_hop.entity_id OR edge.target_entity_id=first_hop.entity_id)
              WHERE intermediate.entity_type IN ('Component','Deployment')
            )
            SELECT DISTINCT ON (entity.id)
                   entity.id,entity.entity_type,entity.name,entity.canonical_key,
                   entity.properties,entity.properties->>'curated_description' summary,
                   entity.last_seen_at observed_at,candidates.fact_assertion_id,
                   candidates.confidence relationship_confidence
            FROM candidates JOIN entity ON entity.id=candidates.entity_id
            WHERE entity.entity_type=%s
            ORDER BY entity.id,candidates.confidence DESC,candidates.fact_assertion_id
            """,
            (repository_id, repository_id, repository_id, entity_type), tenant_id=tenant_id,
        )

    @staticmethod
    def _container(row: dict[str, Any]) -> ContainerImageComposition:
        properties = {**_properties(row), **(row.get("typed_properties") or {})}
        key = str(row.get("canonical_key") or "")
        digest_match = _DIGEST.search(str(properties.get("digest") or key))
        digest = digest_match.group(0) if digest_match else None
        tags = _strings(properties.get("observed_tags", properties.get("tags")))
        if not tags and ":" in key and "@sha256:" not in key:
            tags = [key.rsplit(":", 1)[-1]]
        if digest:
            resolution = "RESOLVED"
            canonical_reference = key if digest in key else digest
        elif tags and all(tag.casefold() != "latest" for tag in tags):
            resolution = "INFERRED"
            canonical_reference = key or None
        else:
            resolution = "UNRESOLVED"
            canonical_reference = None

        layers = []
        for index, value in enumerate(properties.get("layers") or []):
            if isinstance(value, str):
                match = _DIGEST.search(value)
                layers.append(ContainerLayer(index=index, digest=match.group(0) if match else None))
            elif isinstance(value, dict):
                raw_digest = value.get("digest")
                digest_match = _DIGEST.search(raw_digest) if isinstance(raw_digest, str) else None
                raw_index = value.get("index", index)
                raw_size = value.get("size_bytes")
                layers.append(ContainerLayer(
                    index=raw_index if isinstance(raw_index, int) and raw_index >= 0 else index,
                    digest=digest_match.group(0) if digest_match else None,
                    command=value.get("command") if isinstance(value.get("command"), str) else None,
                    size_bytes=raw_size if isinstance(raw_size, int) and raw_size >= 0 else None,
                ))
        packages = []
        for value in properties.get("packages") or []:
            if isinstance(value, str) and value:
                packages.append(ContainerPackage(name=value))
            elif isinstance(value, dict) and value.get("name"):
                packages.append(ContainerPackage(
                    name=value["name"], version=value.get("version"),
                    ecosystem=value.get("ecosystem"),
                ))
        limitations = []
        if resolution != "RESOLVED":
            limitations.append(GateReason(
                code="CONTAINER_IDENTITY_UNRESOLVED" if resolution == "UNRESOLVED" else "CONTAINER_TAG_NOT_PINNED",
                message=(
                    "The image reference does not resolve to an immutable digest."
                    if resolution == "UNRESOLVED"
                    else "The observed tag is not an immutable container identity."
                ),
                evidence_fact_ids=_fact_ids(row),
            ))
        if not layers and not packages:
            limitations.append(GateReason(
                code="CONTAINER_COMPOSITION_NOT_COLLECTED",
                message="No layer or package composition was collected for this image.",
                evidence_fact_ids=_fact_ids(row),
            ))
        status = "AVAILABLE" if resolution == "RESOLVED" and (layers or packages) else "PARTIAL"
        return ContainerImageComposition(
            image=_entity(row),
            identity=ContainerImageIdentity(
                state=resolution, canonical_reference=canonical_reference, digest=digest,
                observed_tags=tags,
                registry=properties.get("registry") if isinstance(properties.get("registry"), str) else None,
            ),
            architecture=properties.get("architecture") if isinstance(properties.get("architecture"), str) else None,
            operating_system=properties.get("operating_system") if isinstance(properties.get("operating_system"), str) else None,
            layers=layers, packages=packages, scan_status=status,
            freshness=_freshness(row.get("observed_at")),
            evidence_fact_ids=_fact_ids(row), limitations=limitations,
        )

    async def repository_container_compositions(
        self, repository_id: UUID, *, tenant_id: UUID | None,
    ) -> ContainerCompositionList:
        repository = await self._repository(repository_id, tenant_id)
        rows = await self.database.fetch_all(
            """
            SELECT image.id,image.entity_type,image.name,image.canonical_key,image.properties,
                   image.properties->>'curated_description' summary,profile.observed_at,
                   profile.typed_properties,profile.evidence_fact_ids,1.0 relationship_confidence
            FROM estate_container_profile current
            JOIN entity image ON image.id=current.image_entity_id
            JOIN LATERAL (
              SELECT selected.observed_at,
                     jsonb_build_object(
                       'digest',selected.digest,'observed_tags',selected.tags,
                       'registry',selected.registry,'architecture',selected.architecture,
                       'operating_system',selected.operating_system,'runtime',selected.runtime,
                       'layers',coalesce((SELECT jsonb_agg(jsonb_build_object(
                         'index',layer.ordinal,'digest',layer.digest,'command',layer.command,
                         'size_bytes',layer.size_bytes) ORDER BY layer.ordinal)
                         FROM estate_container_layer layer WHERE layer.container_profile_id=selected.id),'[]'),
                       'packages',coalesce((SELECT jsonb_agg(jsonb_build_object(
                         'name',package.name,'version',package.version,'ecosystem',package.ecosystem)
                         ORDER BY package.name,package.version)
                         FROM estate_container_package package WHERE package.container_profile_id=selected.id),'[]'),
                       'coverage',selected.coverage,'build',selected.build_metadata,
                       'deployment',selected.deployment_metadata
                     ) typed_properties,
                     coalesce((SELECT array_agg(evidence.fact_assertion_id ORDER BY evidence.fact_assertion_id)
                       FROM estate_profile_evidence evidence
                       WHERE evidence.profile_kind='CONTAINER' AND evidence.profile_id=selected.id),'{}') evidence_fact_ids
              FROM estate_container_profile selected WHERE selected.id=current.id
            ) profile ON true
            WHERE current.repository_entity_id=%s AND current.valid_to IS NULL
            ORDER BY image.name,image.id,current.observed_at DESC
            """,
            (repository_id,), tenant_id=tenant_id,
        )
        if not rows:
            rows = await self._repository_related_entities(repository_id, "ContainerImage", tenant_id)
        images = [self._container(row) for row in rows]
        limitations = []
        if not images:
            limitations.append(GateReason(
                code="CONTAINER_IMAGES_NOT_COLLECTED",
                message="No container image relationship was collected for this repository.",
            ))
        status = (
            "NOT_COLLECTED" if not images
            else "PARTIAL" if any(image.scan_status != "AVAILABLE" for image in images)
            else "AVAILABLE"
        )
        return ContainerCompositionList(
            repository=_entity(repository), status=status, images=images,
            as_of=max((image.freshness.observed_at for image in images), default=datetime.now(UTC)),
            limitations=limitations,
        )

    @staticmethod
    def _deployment(row: dict[str, Any]) -> DeploymentProfile:
        properties = {**_properties(row), **(row.get("typed_properties") or {})}
        actions = []
        for value in properties.get("actions") or []:
            if isinstance(value, dict) and value.get("verb") and value.get("target"):
                actions.append(DeploymentAction(
                    verb=value["verb"], target=value["target"],
                    target_kind=value.get("target_kind"),
                ))
        provider = properties.get("provider") if isinstance(properties.get("provider"), str) else None
        workload = properties.get("workload_kind") if isinstance(properties.get("workload_kind"), str) else None
        target = properties.get("target") if isinstance(properties.get("target"), str) else None
        if not actions and target:
            actions.append(DeploymentAction(verb="RUNS_ON", target=target, target_kind=workload))
        if not actions and provider:
            actions.append(DeploymentAction(verb="DEPLOYS_TO", target=provider, target_kind="PROVIDER"))
        evidence = _fact_ids(row)
        limitations = []
        if not actions:
            limitations.append(GateReason(
                code="DEPLOYMENT_RELATIONSHIPS_NOT_COLLECTED",
                message="The deployment is known, but no verb-and-target relationship was collected.",
                evidence_fact_ids=evidence,
            ))
        if provider is None:
            limitations.append(GateReason(
                code="DEPLOYMENT_PROVIDER_UNKNOWN",
                message="The deployment provider has not been resolved.",
                evidence_fact_ids=evidence,
            ))
        confidence = float(properties.get("confidence") or row.get("relationship_confidence") or 0)
        status = "AVAILABLE" if actions and provider else "PARTIAL"
        return DeploymentProfile(
            deployment=_entity(row), provider=provider, workload_kind=workload,
            environment=properties.get("environment") if isinstance(properties.get("environment"), str) else None,
            region=properties.get("region") if isinstance(properties.get("region"), str) else None,
            actions=actions, status=status, confidence=confidence,
            confidence_label=_confidence_label(confidence),
            freshness=_freshness(row.get("observed_at")),
            evidence_fact_ids=evidence, limitations=limitations,
        )

    async def repository_deployment_profiles(
        self, repository_id: UUID, *, tenant_id: UUID | None,
    ) -> DeploymentProfileList:
        repository = await self._repository(repository_id, tenant_id)
        rows = await self.database.fetch_all(
            """
            SELECT deployment.id,deployment.entity_type,deployment.name,deployment.canonical_key,
                   deployment.properties,deployment.properties->>'curated_description' summary,
                   profile.observed_at,
                   jsonb_build_object(
                     'provider',profile.provider,'workload_kind',profile.workload_kind,
                     'environment',profile.environment,'region',profile.region,
                     'actions',profile.actions,'resources',profile.resources,
                     'confidence',profile.confidence,'method_version',profile.method_version,
                     'source_revision',profile.source_revision
                   ) typed_properties,
                   coalesce((SELECT array_agg(evidence.fact_assertion_id ORDER BY evidence.fact_assertion_id)
                     FROM estate_profile_evidence evidence
                     WHERE evidence.profile_kind='DEPLOYMENT' AND evidence.profile_id=profile.id),'{}') evidence_fact_ids,
                   profile.confidence relationship_confidence
            FROM estate_deployment_profile profile
            JOIN entity deployment ON deployment.id=profile.deployment_entity_id
            WHERE profile.repository_entity_id=%s AND profile.valid_to IS NULL
            ORDER BY deployment.name,deployment.id,profile.observed_at DESC
            """,
            (repository_id,), tenant_id=tenant_id,
        )
        if not rows:
            rows = await self._repository_related_entities(repository_id, "Deployment", tenant_id)
        profiles = [self._deployment(row) for row in rows]
        limitations = []
        if not profiles:
            limitations.append(GateReason(
                code="DEPLOYMENTS_NOT_COLLECTED",
                message="No deployment relationship was collected for this repository.",
            ))
        return DeploymentProfileList(
            repository=_entity(repository), profiles=profiles,
            as_of=max((profile.freshness.observed_at for profile in profiles), default=datetime.now(UTC)),
            limitations=limitations,
        )

    async def estate_strata(self, *, tenant_id: UUID | None) -> EstateStrata:
        rows = await self.database.fetch_all(
            """
            WITH population AS (
              SELECT namespace,count(*)::integer population_count
              FROM entity WHERE namespace IN ('BUSINESS','ENTERPRISE','TECHNOLOGY','OSS','DEPLOYMENT')
              GROUP BY namespace
            ), observed AS (
              SELECT entity.namespace,count(DISTINCT entity.id)::integer observed_count,
                     max(fact.observed_at) as_of
              FROM entity JOIN current_fact fact ON fact.subject_entity_id=entity.id
              WHERE entity.namespace IN ('BUSINESS','ENTERPRISE','TECHNOLOGY','OSS','DEPLOYMENT')
              GROUP BY entity.namespace
            ), edge_evidence AS (
              SELECT entity.namespace,relationship.fact_assertion_id,
                     count(DISTINCT evidence.source_artifact_id) source_count
              FROM current_relationship relationship
              JOIN entity ON entity.id=relationship.source_entity_id
              LEFT JOIN evidence ON evidence.fact_assertion_id=relationship.fact_assertion_id
              WHERE entity.namespace IN ('BUSINESS','ENTERPRISE','TECHNOLOGY','OSS','DEPLOYMENT')
              GROUP BY entity.namespace,relationship.fact_assertion_id
            ), corroboration AS (
              SELECT namespace,
                     count(*) FILTER (WHERE source_count>=2)::float/nullif(count(*),0) ratio
              FROM edge_evidence GROUP BY namespace
            )
            SELECT population.namespace,population.population_count,
                   coalesce(observed.observed_count,0) observed_count,observed.as_of,
                   corroboration.ratio corroboration_ratio
            FROM population
            LEFT JOIN observed USING(namespace)
            LEFT JOIN corroboration USING(namespace)
            ORDER BY array_position(
              ARRAY['BUSINESS','ENTERPRISE','TECHNOLOGY','OSS','DEPLOYMENT'],population.namespace
            )
            """,
            tenant_id=tenant_id,
        )
        by_namespace = {row["namespace"]: row for row in rows}
        layers = []
        for key, label in _LAYER_LABELS.items():
            row = by_namespace.get(key)
            population = int(row["population_count"]) if row else 0
            observed = int(row["observed_count"]) if row else 0
            coverage = observed / population if population else None
            limitations = []
            if not population:
                limitations.append(GateReason(
                    code=f"{key}_STRATUM_NOT_COLLECTED",
                    message=f"No {label.lower()} entities are available to measure.",
                ))
            elif observed < population:
                limitations.append(GateReason(
                    code=f"{key}_COVERAGE_PARTIAL",
                    message=f"{population - observed} known {label.lower()} entities have no current supporting fact.",
                ))
            if population and row.get("corroboration_ratio") is None:
                limitations.append(GateReason(
                    code=f"{key}_CORROBORATION_NOT_MEASURED",
                    message=f"No current {label.lower()} relationships carry a corroboration reading.",
                ))
            status = (
                "NOT_COLLECTED" if not population
                else "AVAILABLE" if observed == population and row.get("corroboration_ratio") is not None
                else "PARTIAL"
            )
            layers.append(EstateStratumLayer(
                key=key, label=label, status=status,
                population_count=population, observed_count=observed,
                coverage_ratio=coverage,
                corroboration_ratio=float(row["corroboration_ratio"]) if row and row.get("corroboration_ratio") is not None else None,
                as_of=row.get("as_of") if row else None,
                limitations=limitations,
            ))
        ai_supply_chain = await self.ai_supply_chain(tenant_id=tenant_id)
        layers.append(EstateStratumLayer(
            key="AI", label="AI", status=ai_supply_chain.status,
            population_count=len(ai_supply_chain.entities) if ai_supply_chain.entities else None,
            observed_count=len(ai_supply_chain.entities) if ai_supply_chain.entities else None,
            coverage_ratio=ai_supply_chain.coverage_ratio,
            corroboration_ratio=None,
            as_of=ai_supply_chain.as_of if ai_supply_chain.entities else None,
            limitations=ai_supply_chain.limitations,
        ))
        return EstateStrata(
            as_of=max((layer.as_of for layer in layers if layer.as_of), default=datetime.now(UTC)),
            layers=layers,
        )

    async def contradiction_ledger(
        self, *, tenant_id: UUID | None, subject_id: UUID | None, limit: int,
    ) -> ContradictionLedger:
        rows = await self.database.fetch_all(
            """
            WITH claim_rows AS (
              SELECT fact.subject_entity_id,fact.predicate,
                     CASE WHEN fact.predicate='HAS_PROPERTY'
                          THEN fact.predicate||':'||((fact.object_value::jsonb)->>'property_key')
                          ELSE fact.predicate END dimension_key,
                     coalesce(object_entity.canonical_key,(fact.object_value::jsonb)->>'value',
                              (fact.object_value::jsonb#>>'{}')) claim_key,
                     coalesce(object_entity.name,(fact.object_value::jsonb)->>'display_value',
                              (fact.object_value::jsonb)->>'value',(fact.object_value::jsonb#>>'{}')) display_value,
                     fact.assertion_class,fact.confidence,fact.observed_at,fact.id fact_id,
                     fact.source_snapshot_id,fact.extractor_key
              FROM current_fact fact
              LEFT JOIN entity object_entity ON object_entity.id=fact.object_entity_id
              WHERE (%s::uuid IS NULL OR fact.subject_entity_id=%s::uuid)
                AND (fact.predicate<>'HAS_PROPERTY' OR fact.object_value::jsonb ? 'property_key')
            ), contradiction_keys AS (
              SELECT subject_entity_id,dimension_key
              FROM claim_rows
              GROUP BY subject_entity_id,dimension_key
              HAVING count(DISTINCT claim_key)>=2
              ORDER BY subject_entity_id,dimension_key
              LIMIT %s
            )
            SELECT claim_rows.*,coalesce(source.source_key,claim_rows.extractor_key) source_key,
                   subject.id,subject.entity_type,subject.name,subject.canonical_key,
                   subject.properties->>'curated_description' summary
            FROM claim_rows JOIN contradiction_keys USING(subject_entity_id,dimension_key)
            JOIN entity subject ON subject.id=claim_rows.subject_entity_id
            JOIN source_snapshot snapshot ON snapshot.id=claim_rows.source_snapshot_id
            JOIN ingest_target target ON target.id=snapshot.ingest_target_id
            LEFT JOIN source_system source ON source.id=target.source_system_id
            ORDER BY claim_rows.subject_entity_id,claim_rows.dimension_key,claim_rows.claim_key,
                     source_key,claim_rows.observed_at DESC,claim_rows.fact_id
            """,
            (subject_id, subject_id, limit + 1), tenant_id=tenant_id,
        )
        grouped: dict[tuple[UUID, str], list[dict[str, Any]]] = {}
        for row in rows:
            grouped.setdefault((row["subject_entity_id"], row["dimension_key"]), []).append(row)
        subject_ids = list({entity_id for entity_id, _ in grouped})
        affected_rows = await self.database.fetch_all(
            """
            WITH requested AS (SELECT unnest(%s::uuid[]) subject_entity_id)
            SELECT requested.subject_entity_id,
                   count(DISTINCT CASE
                     WHEN relationship.source_entity_id=requested.subject_entity_id
                       THEN relationship.target_entity_id
                     ELSE relationship.source_entity_id END)::integer affected_entity_count
            FROM requested
            LEFT JOIN current_relationship relationship
              ON relationship.source_entity_id=requested.subject_entity_id
              OR relationship.target_entity_id=requested.subject_entity_id
            GROUP BY requested.subject_entity_id
            """,
            (subject_ids,), tenant_id=tenant_id,
        ) if subject_ids else []
        affected_by_subject = {
            row["subject_entity_id"]: int(row["affected_entity_count"])
            for row in affected_rows
        }
        all_items = []
        for (entity_id, dimension), claims in grouped.items():
            first = claims[0]
            key_material = f"{entity_id}\x1f{dimension}".encode()
            claim_models = [ContradictionClaim(
                claim_key=str(row["claim_key"]),
                display_value=str(row["display_value"]),
                source_key=row["source_key"], assertion_class=row["assertion_class"],
                confidence=float(row["confidence"]), observed_at=row["observed_at"],
                evidence_fact_ids=[row["fact_id"]],
            ) for row in claims]
            all_items.append(ContradictionLedgerItem(
                id="sha256:" + hashlib.sha256(key_material).hexdigest(),
                subject=_entity(first), predicate=dimension,
                claims=claim_models,
                affected_entity_count=affected_by_subject.get(entity_id, 0),
                last_verified_at=max(claim.observed_at for claim in claim_models),
                limitations=[GateReason(
                    code="NO_AUTHORITATIVE_CLAIM_SELECTED",
                    message="The ledger presents source disagreement and does not select a true claim.",
                    evidence_fact_ids=[claim.evidence_fact_ids[0] for claim in claim_models],
                )],
            ))
        visible = all_items[:limit]
        limitations = []
        if not visible:
            limitations.append(GateReason(
                code="NO_CURRENT_CONTRADICTIONS",
                message="No current multi-source claim disagreement was detected in the requested scope.",
            ))
        limitations.append(GateReason(
            code="ASSUMPTION_REGISTRY_NOT_AVAILABLE",
            message="This ledger covers observed fact disagreement; governed assumptions and resolution history require E1 persistence.",
        ))
        return ContradictionLedger(
            as_of=max((item.last_verified_at for item in visible), default=datetime.now(UTC)),
            contradictions=visible,
            page_info=PageInfo(has_next_page=len(all_items) > limit),
            limitations=limitations,
        )
