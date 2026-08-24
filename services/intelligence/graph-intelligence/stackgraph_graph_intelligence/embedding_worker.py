from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import socket
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any, Mapping
from uuid import UUID

import psycopg
from psycopg import Connection
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from .embeddings import (
    EmbeddingAdapter,
    EmbeddingFailure,
    EmbeddingResult,
    LocalHashEmbeddingAdapter,
    OpenAICompatibleEmbeddingAdapter,
    content_hash,
    render_entity_document,
    vector_literal,
)
from .similarity import (
    ApplicationFeatures,candidate_pairs,dependency_frequencies,
    deterministic_application_similarity,hybrid_application_similarity,
)
from .evaluation import RelevanceCaseResult,evaluate_relevance


GLOBAL_SEMANTIC_ENTITY_TYPES = ("Technology","Runtime","Database","Package")


@dataclass(frozen=True, slots=True)
class ClaimedEmbeddingJob:
    id: UUID
    tenant_id: UUID
    space_id: UUID
    entity_id: UUID
    input_hash: str
    attempt_count: int
    max_attempts: int
    provider: str
    provider_base_url: str | None
    model: str
    dimensions: int
    normalization: str
    template_version: str
    external_processing_allowed: bool
    sensitive_content_allowed: bool
    api_key: str | None


@dataclass(frozen=True, slots=True)
class EmbeddingWorkerResult:
    claimed: bool
    job_id: str | None = None
    status: str = "IDLE"
    entity_id: str | None = None
    dimensions: int = 0


class EmbeddingWorker:
    def __init__(
        self,
        database_url: str,
        *,
        encryption_key: str,
        lease_seconds: int = 300,
        worker_id: str | None = None,
        local_adapter: EmbeddingAdapter | None = None,
    ) -> None:
        self.connection: Connection[dict[str, Any]] = psycopg.connect(
            database_url, row_factory=dict_row, autocommit=True,
        )
        self.encryption_key = encryption_key
        self.lease_seconds = lease_seconds
        self.worker_id = worker_id or f"{socket.gethostname()}:{os.getpid()}"
        self.local_adapter = local_adapter or LocalHashEmbeddingAdapter()

    def close(self) -> None:
        self.connection.close()

    def _recover_expired(self) -> int:
        with self.connection.transaction():
            rows = self.connection.execute(
                """
                UPDATE embedding_job
                SET status=CASE WHEN attempt_count>=max_attempts THEN 'DEAD_LETTER' ELSE 'RETRY_WAIT' END,
                    available_at=CASE WHEN attempt_count>=max_attempts THEN available_at ELSE now() END,
                    last_error_class='LeaseExpired',last_error='Embedding worker lease expired',
                    lease_owner=NULL,lease_expires_at=NULL,heartbeat_at=NULL,updated_at=now(),
                    completed_at=CASE WHEN attempt_count>=max_attempts THEN now() ELSE completed_at END
                WHERE status='RUNNING' AND lease_expires_at<now()
                RETURNING id
                """
            ).fetchall()
        return len(rows)

    def _claim(self) -> ClaimedEmbeddingJob | None:
        with self.connection.transaction():
            row = self.connection.execute(
                """
                SELECT job.id,job.tenant_id,job.embedding_space_id AS space_id,
                       job.subject_id AS entity_id,job.input_hash,job.attempt_count,job.max_attempts,
                       policy.provider,policy.provider_base_url,policy.model,policy.dimensions,
                       policy.normalization,space.template_version,
                       policy.external_processing_allowed,policy.sensitive_content_allowed,
                       CASE WHEN secret.id IS NULL THEN NULL
                            ELSE pgp_sym_decrypt(secret.ciphertext,%s)::text END AS api_key
                FROM embedding_job job
                JOIN embedding_space space ON space.id=job.embedding_space_id
                  AND space.tenant_id=job.tenant_id
                JOIN tenant_embedding_policy policy ON policy.tenant_id=job.tenant_id
                LEFT JOIN tenant_secret secret ON secret.id=policy.credential_secret_id
                  AND secret.tenant_id=policy.tenant_id
                WHERE job.status IN ('PENDING','RETRY_WAIT') AND job.available_at<=now()
                  AND policy.enabled
                  AND space.lifecycle_state IN ('SHADOW','ACTIVE')
                  AND stackgraph_tenant_service_running(job.tenant_id,'embeddings')
                ORDER BY coalesce((
                  SELECT max(history.started_at) FROM embedding_job history
                  WHERE history.tenant_id=job.tenant_id
                ),'-infinity'::timestamptz),job.created_at,job.tenant_id
                FOR UPDATE OF job SKIP LOCKED LIMIT 1
                """,
                (self.encryption_key,),
            ).fetchone()
            if row is None:
                return None
            claimed = self.connection.execute(
                """
                UPDATE embedding_job SET status='RUNNING',attempt_count=attempt_count+1,
                  lease_owner=%s,lease_expires_at=now()+%s*interval '1 second',heartbeat_at=now(),
                  started_at=coalesce(started_at,now()),updated_at=now()
                WHERE id=%s AND status IN ('PENDING','RETRY_WAIT')
                RETURNING attempt_count
                """,
                (self.worker_id,self.lease_seconds,row["id"]),
            ).fetchone()
            if claimed is None:
                return None
            return ClaimedEmbeddingJob(
                id=row["id"],tenant_id=row["tenant_id"],space_id=row["space_id"],
                entity_id=row["entity_id"],input_hash=row["input_hash"],
                attempt_count=int(claimed["attempt_count"]),max_attempts=int(row["max_attempts"]),
                provider=row["provider"],provider_base_url=row.get("provider_base_url"),
                model=row["model"],dimensions=int(row["dimensions"]),normalization=row["normalization"],
                template_version=row["template_version"],
                external_processing_allowed=bool(row["external_processing_allowed"]),
                sensitive_content_allowed=bool(row["sensitive_content_allowed"]),api_key=row.get("api_key"),
            )

    def _document(self, job: ClaimedEmbeddingJob) -> tuple[dict[str, Any], str, list[str], str]:
        entity = self.connection.execute(
            """
            SELECT id,tenant_id,entity_type,name,canonical_key,properties,updated_at
            FROM entity
            WHERE id=%s AND (tenant_id=%s OR (
              tenant_id IS NULL AND entity_type=ANY(%s::text[])
            ))
            """,
            (job.entity_id,job.tenant_id,list(GLOBAL_SEMANTIC_ENTITY_TYPES)),
        ).fetchone()
        if entity is None:
            raise EmbeddingFailure("embedding subject no longer exists", retryable=False)
        relationships = self.connection.execute(
            """
            SELECT fact.id AS fact_id,fact.predicate,
                   CASE WHEN fact.subject_entity_id=%s THEN object_entity.name ELSE subject_entity.name END AS object_name,
                   CASE WHEN fact.subject_entity_id=%s THEN fact.object_value #>> '{}' ELSE NULL END AS object_text
            FROM fact_assertion fact
            LEFT JOIN entity subject_entity ON subject_entity.id=fact.subject_entity_id
            LEFT JOIN entity object_entity ON object_entity.id=fact.object_entity_id
            WHERE (fact.tenant_id IS NULL OR fact.tenant_id=%s) AND fact.system_to IS NULL
              AND (fact.subject_entity_id=%s OR fact.object_entity_id=%s)
            ORDER BY fact.predicate,object_name,fact.id
            """,
            (job.entity_id,job.entity_id,job.tenant_id,job.entity_id,job.entity_id),
        ).fetchall()
        content, fact_ids = render_entity_document(
            entity,relationships,template_version=job.template_version,
        )
        properties = entity.get("properties") if isinstance(entity.get("properties"), dict) else {}
        sensitivity = str(properties.get("sensitivity") or "INTERNAL").upper()
        if sensitivity not in {"PUBLIC","INTERNAL","CONFIDENTIAL","RESTRICTED"}:
            sensitivity = "INTERNAL"
        return entity,content,fact_ids,sensitivity

    def _adapter(self, job: ClaimedEmbeddingJob, sensitivity: str) -> EmbeddingAdapter:
        if job.provider == "LOCAL":
            return self.local_adapter
        if not job.external_processing_allowed:
            raise EmbeddingFailure("tenant policy forbids external embedding processing", retryable=False)
        if sensitivity in {"CONFIDENTIAL","RESTRICTED"} and not job.sensitive_content_allowed:
            raise EmbeddingFailure("tenant policy forbids sensitive external embedding content", retryable=False)
        if not job.provider_base_url or not job.api_key:
            raise EmbeddingFailure("embedding provider credentials are incomplete", retryable=False)
        return OpenAICompatibleEmbeddingAdapter(base_url=job.provider_base_url,api_key=job.api_key)

    def _cached_result(self, job: ClaimedEmbeddingJob, input_hash: str) -> EmbeddingResult | None:
        row = self.connection.execute(
            """
            SELECT embedding::text AS embedding,token_count,provider_usage
            FROM entity_embedding
            WHERE tenant_id=%s AND embedding_space_id=%s AND input_hash=%s
            ORDER BY created_at DESC,entity_id LIMIT 1
            """,
            (job.tenant_id,job.space_id,input_hash),
        ).fetchone()
        if row is None:
            return None
        values = [float(value) for value in row["embedding"].strip("[]").split(",")]
        usage = dict(row["provider_usage"] or {})
        usage["cache_hit"] = True
        return EmbeddingResult(
            values=values,token_count=int(row["token_count"] or 0),
            latency_ms=0,usage=usage,
        )

    def _succeed(
        self,job: ClaimedEmbeddingJob,entity: Mapping[str,Any],content: str,
        fact_ids: list[str],sensitivity: str,result: Any,
    ) -> None:
        current_hash = content_hash(content)
        with self.connection.transaction():
            self.connection.execute(
                """
                INSERT INTO embedding_document(
                  tenant_id,embedding_space_id,entity_id,entity_type,template_version,
                  rendered_content,input_hash,source_fact_ids,sensitivity,source_revision
                ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s::uuid[],%s,%s)
                ON CONFLICT(embedding_space_id,entity_id) DO UPDATE SET
                  entity_type=EXCLUDED.entity_type,template_version=EXCLUDED.template_version,
                  rendered_content=EXCLUDED.rendered_content,input_hash=EXCLUDED.input_hash,
                  source_fact_ids=EXCLUDED.source_fact_ids,sensitivity=EXCLUDED.sensitivity,
                  source_revision=EXCLUDED.source_revision,rendered_at=now()
                """,
                (
                    job.tenant_id,job.space_id,job.entity_id,entity["entity_type"],job.template_version,
                    content,current_hash,fact_ids,sensitivity,
                    Jsonb({"entity_updated_at":entity["updated_at"].isoformat()}),
                ),
            )
            self.connection.execute(
                """
                INSERT INTO entity_embedding(
                  tenant_id,embedding_space_id,entity_id,dimensions,input_hash,embedding,
                  token_count,provider_latency_ms,provider_usage
                ) VALUES (%s,%s,%s,%s,%s,%s::vector,%s,%s,%s)
                ON CONFLICT(embedding_space_id,entity_id) DO UPDATE SET
                  dimensions=EXCLUDED.dimensions,input_hash=EXCLUDED.input_hash,
                  embedding=EXCLUDED.embedding,token_count=EXCLUDED.token_count,
                  provider_latency_ms=EXCLUDED.provider_latency_ms,
                  provider_usage=EXCLUDED.provider_usage,created_at=now()
                """,
                (
                    job.tenant_id,job.space_id,job.entity_id,job.dimensions,current_hash,
                    vector_literal(result.values),result.token_count,result.latency_ms,Jsonb(result.usage),
                ),
            )
            self.connection.execute(
                """
                UPDATE embedding_job SET status='SUCCEEDED',provider_request_id=%s,
                  lease_owner=NULL,lease_expires_at=NULL,heartbeat_at=NULL,last_error_class=NULL,
                  last_error=NULL,completed_at=now(),updated_at=now() WHERE id=%s
                """,
                (result.request_id,job.id),
            )
            self.connection.execute(
                """
                UPDATE embedding_space space SET coverage_ratio=coverage.ratio,updated_at=now()
                FROM (
                  SELECT CASE WHEN count(DISTINCT entity.id)=0 THEN 0
                    ELSE count(DISTINCT embedding.entity_id)::double precision/count(DISTINCT entity.id) END AS ratio
                  FROM entity
                  LEFT JOIN entity_embedding embedding ON embedding.entity_id=entity.id
                    AND embedding.embedding_space_id=%s
                  WHERE entity.tenant_id=%s OR (
                    entity.tenant_id IS NULL AND entity.entity_type=ANY(%s::text[])
                  )
                ) coverage WHERE space.id=%s
                """,
                (
                    job.space_id,job.tenant_id,list(GLOBAL_SEMANTIC_ENTITY_TYPES),job.space_id,
                ),
            )

    def _fail(self,job: ClaimedEmbeddingJob,failure: Exception) -> str:
        retryable = isinstance(failure,EmbeddingFailure) and failure.retryable
        retry_after = failure.retry_after_seconds if isinstance(failure,EmbeddingFailure) else None
        dead = not retryable or job.attempt_count>=job.max_attempts
        if retry_after is None:
            retry_after = min(3600.0,2 ** min(job.attempt_count,12)) + random.random()
        status = "DEAD_LETTER" if dead else "RETRY_WAIT"
        with self.connection.transaction():
            self.connection.execute(
                """
                UPDATE embedding_job SET status=%s,available_at=CASE WHEN %s THEN available_at ELSE now()+%s*interval '1 second' END,
                  retry_after_at=CASE WHEN %s THEN NULL ELSE now()+%s*interval '1 second' END,
                  lease_owner=NULL,lease_expires_at=NULL,heartbeat_at=NULL,
                  last_error_class=%s,last_error=%s,completed_at=CASE WHEN %s THEN now() ELSE NULL END,
                  updated_at=now() WHERE id=%s
                """,
                (
                    status,dead,retry_after,dead,retry_after,
                    failure.failure_kind if isinstance(failure,EmbeddingFailure) else type(failure).__name__,
                    str(failure)[:2000],dead,job.id,
                ),
            )
        return status

    def run_once(self) -> EmbeddingWorkerResult:
        self._recover_expired()
        job = self._claim()
        if job is None:
            return EmbeddingWorkerResult(claimed=False)
        try:
            entity,content,fact_ids,sensitivity = self._document(job)
            result = self._cached_result(job,content_hash(content))
            if result is None:
                adapter = self._adapter(job,sensitivity)
                result = adapter.embed(content,dimensions=job.dimensions,model=job.model)
            self._succeed(job,entity,content,fact_ids,sensitivity,result)
            return EmbeddingWorkerResult(
                claimed=True,job_id=str(job.id),status="SUCCEEDED",
                entity_id=str(job.entity_id),dimensions=job.dimensions,
            )
        except Exception as failure:
            return EmbeddingWorkerResult(
                claimed=True,job_id=str(job.id),status=self._fail(job,failure),
                entity_id=str(job.entity_id),dimensions=job.dimensions,
            )


def ensure_space(connection: Connection[Any],tenant_id: UUID) -> UUID:
    policy = connection.execute(
        """
        INSERT INTO tenant_embedding_policy(tenant_id) VALUES (%s)
        ON CONFLICT(tenant_id) DO UPDATE SET updated_at=tenant_embedding_policy.updated_at
        RETURNING *
        """,
        (tenant_id,),
    ).fetchone()
    configuration = {
        "provider":policy["provider"],"model":policy["model"],
        "dimensions":policy["dimensions"],"normalization":policy["normalization"],
        "template_version":"semantic-entity/v1",
        "global_entity_types":list(GLOBAL_SEMANTIC_ENTITY_TYPES),
    }
    digest = "sha256:" + hashlib.sha256(json.dumps(configuration,sort_keys=True).encode()).hexdigest()
    row = connection.execute(
        """
        INSERT INTO embedding_space(
          tenant_id,space_key,space_kind,provider,model_or_algorithm,dimensions,
          normalization,template_version,configuration,content_hash
        ) VALUES (%s,%s,'SEMANTIC_ENTITY',%s,%s,%s,%s,'semantic-entity/v1',%s,%s)
        ON CONFLICT(tenant_id,space_key) DO UPDATE SET updated_at=now()
        RETURNING id
        """,
        (
            tenant_id,f"semantic-entity-{digest[7:19]}",policy["provider"],policy["model"],
            policy["dimensions"],policy["normalization"],Jsonb(configuration),digest,
        ),
    ).fetchone()
    space_id = row["id"]
    connection.execute(
        """
        INSERT INTO embedding_job(tenant_id,embedding_space_id,subject_id,input_hash)
        SELECT %s,%s,entity.id,
          'sha256:'||encode(digest(concat_ws(E'\n',entity.entity_type,entity.name,entity.canonical_key,entity.properties::text,'semantic-entity/v1'),'sha256'),'hex')
        FROM entity
        WHERE entity.tenant_id=%s OR (
          entity.tenant_id IS NULL AND entity.entity_type=ANY(%s::text[])
        )
        ON CONFLICT DO NOTHING
        """,
        (tenant_id,space_id,tenant_id,list(GLOBAL_SEMANTIC_ENTITY_TYPES)),
    )
    return space_id


def evaluate_space(
    connection: Connection[Any],space_id: UUID,*,encryption_key: str,
) -> Mapping[str,Any]:
    row = connection.execute(
        """
        SELECT space.tenant_id,space.coverage_ratio,space.dimensions,space.provider,
          space.model_or_algorithm,space.space_kind,count(*) AS vector_count,
          count(*) FILTER (WHERE vector_dims(embedding.embedding)=space.dimensions) AS valid_dimensions,
          count(DISTINCT embedding.entity_id) AS unique_entities
        FROM embedding_space space
        LEFT JOIN entity_embedding embedding ON embedding.embedding_space_id=space.id
        WHERE space.id=%s GROUP BY space.id
        """,
        (space_id,),
    ).fetchone()
    if row is None:
        raise ValueError("embedding space was not found")
    integrity_passed = bool(
        row["coverage_ratio"]>=0.95 and row["vector_count"]>0
        and row["vector_count"]==row["valid_dimensions"]==row["unique_entities"]
    )
    case_results: list[RelevanceCaseResult] = []
    cases = connection.execute(
        """
        SELECT query_text,relevant_entity_ids,hard_negative_entity_ids,evaluation_k
        FROM embedding_relevance_case
        WHERE tenant_id=%s AND status='ACTIVE' ORDER BY case_key
        """,
        (row["tenant_id"],),
    ).fetchall()
    if row["space_kind"]=="SEMANTIC_ENTITY" and cases:
        policy = connection.execute(
            """
            SELECT policy.*,
              CASE WHEN secret.id IS NULL THEN NULL
                ELSE pgp_sym_decrypt(secret.ciphertext,%s)::text END AS api_key
            FROM tenant_embedding_policy policy
            LEFT JOIN tenant_secret secret ON secret.id=policy.credential_secret_id
              AND secret.tenant_id=policy.tenant_id
            WHERE policy.tenant_id=%s
            """,
            (encryption_key,row["tenant_id"]),
        ).fetchone()
        if policy is None:
            raise ValueError("tenant embedding policy was not found")
        if policy["provider"]=="LOCAL":
            adapter: EmbeddingAdapter = LocalHashEmbeddingAdapter()
        else:
            if not policy["external_processing_allowed"] or not policy["provider_base_url"] or not policy["api_key"]:
                raise ValueError("external evaluation is not permitted or configured")
            adapter = OpenAICompatibleEmbeddingAdapter(
                base_url=policy["provider_base_url"],api_key=policy["api_key"],
            )
        for case in cases:
            query = adapter.embed(
                case["query_text"],dimensions=int(row["dimensions"]),model=row["model_or_algorithm"],
            )
            ranked = connection.execute(
                """
                SELECT entity_id FROM entity_embedding
                WHERE tenant_id=%s AND embedding_space_id=%s
                ORDER BY embedding<=>%s::vector,entity_id LIMIT %s
                """,
                (row["tenant_id"],space_id,vector_literal(query.values),case["evaluation_k"]),
            ).fetchall()
            case_results.append(RelevanceCaseResult(
                ranked_entity_ids=tuple(str(item["entity_id"]) for item in ranked),
                relevant_entity_ids=frozenset(str(item) for item in case["relevant_entity_ids"]),
                hard_negative_entity_ids=frozenset(str(item) for item in case["hard_negative_entity_ids"]),
            ))
    relevance = evaluate_relevance(case_results)
    relevance_passed = bool(
        relevance["case_count"]>=3 and relevance["recall_at_k"]>=0.8
        and relevance["ndcg_at_k"]>=0.75 and relevance["hard_negative_rate"]<=0.1
    ) if row["space_kind"]=="SEMANTIC_ENTITY" else False
    passed = integrity_passed and relevance_passed
    evaluation = {
        "passed":passed,"method_version":"embedding-space-relevance/v2",
        "coverage_ratio":float(row["coverage_ratio"]),"vector_count":int(row["vector_count"]),
        "dimensions":int(row["dimensions"]),"integrity_passed":integrity_passed,
        "relevance_passed":relevance_passed,"relevance":relevance,
        "reason":None if passed else "REVIEWED_RELEVANCE_OR_INTEGRITY_GATE_NOT_MET",
        "evaluated_at":datetime.now(timezone.utc).isoformat(),
    }
    connection.execute(
        "UPDATE embedding_space SET evaluation=%s,updated_at=now() WHERE id=%s",
        (Jsonb(evaluation),space_id),
    )
    return evaluation


def rebuild_similarity_candidates(
    connection: Connection[Any],tenant_id: UUID,*,minimum_score: float=0.2,max_pairs: int=100_000,
) -> Mapping[str,Any]:
    rows = connection.execute(
        """
        WITH applications AS (
          SELECT id FROM entity WHERE tenant_id=%s AND namespace='ENTERPRISE' AND entity_type='Application'
        ), direct AS (
          SELECT application.id AS application_id,
            CASE WHEN relationship.source_entity_id=application.id
              THEN relationship.target_entity_id ELSE relationship.source_entity_id END AS related_id,
            relationship.relationship_type
          FROM applications application
          JOIN current_relationship relationship ON relationship.tenant_id=%s
            AND (relationship.source_entity_id=application.id OR relationship.target_entity_id=application.id)
        ), repositories AS (
          SELECT direct.application_id,direct.related_id AS repository_id
          FROM direct JOIN entity ON entity.id=direct.related_id
          WHERE entity.entity_type='Repository'
            AND direct.relationship_type IN ('IMPLEMENTED_BY','IMPLEMENTS','CONTAINS')
        ), expanded AS (
          SELECT * FROM direct
          UNION ALL
          SELECT repositories.application_id,
            CASE WHEN relationship.source_entity_id=repositories.repository_id
              THEN relationship.target_entity_id ELSE relationship.source_entity_id END,
            relationship.relationship_type
          FROM repositories JOIN current_relationship relationship
            ON relationship.tenant_id=%s AND (
              relationship.source_entity_id=repositories.repository_id
              OR relationship.target_entity_id=repositories.repository_id
            )
        )
        SELECT applications.id AS application_id,expanded.relationship_type,related.id AS related_id,
          related.namespace,related.entity_type,related.canonical_key
        FROM applications
        LEFT JOIN expanded ON expanded.application_id=applications.id
        LEFT JOIN entity related ON related.id=expanded.related_id
        ORDER BY applications.id,related.id,expanded.relationship_type
        """,
        (tenant_id,tenant_id,tenant_id),
    ).fetchall()
    mutable: dict[str,dict[str,set[str]]] = {}
    for row in rows:
        app = mutable.setdefault(str(row["application_id"]),{
            "dependencies":set(),"transitive_dependencies":set(),"capabilities":set(),
            "technologies":set(),"owners":set(),"deployments":set(),
        })
        if row["related_id"] is None:
            continue
        identity = str(row["canonical_key"] or row["related_id"])
        if row["namespace"] in {"TECHNOLOGY","OSS"}:
            app["technologies"].add(identity)
            if row["relationship_type"] in {"DEPENDS_ON","USES","BUILT_ON","RUNS_ON","HAS_VERSION"}:
                app["dependencies"].add(identity)
        elif row["namespace"]=="BUSINESS":
            if row["entity_type"] in {"BusinessCapability","BusinessFunction","BusinessProcess"}:
                app["capabilities"].add(identity)
            if row["entity_type"] in {"Organization","BusinessUnit","Team"}:
                app["owners"].add(identity)
        elif row["namespace"]=="DEPLOYMENT":
            app["deployments"].add(identity)
    features = {key:ApplicationFeatures(**{name:frozenset(values) for name,values in groups.items()}) for key,groups in mutable.items()}
    frequencies = dependency_frequencies(features)
    vector_signals: dict[str,tuple[UUID | None,dict[tuple[str,str],float]]] = {}
    for space_kind,signal_key in (
        ("SEMANTIC_ENTITY","semantic"),("STRUCTURAL_GRAPH","structural"),
    ):
        active = connection.execute(
            """
            SELECT active.embedding_space_id
            FROM active_embedding_space active
            WHERE active.tenant_id=%s AND active.space_kind=%s
            """,
            (tenant_id,space_kind),
        ).fetchone()
        space_id = active["embedding_space_id"] if active else None
        scores: dict[tuple[str,str],float] = {}
        if space_id is not None:
            neighbors = connection.execute(
                """
                WITH application_vectors AS (
                  SELECT embedding.entity_id,embedding.embedding
                  FROM entity_embedding embedding
                  JOIN entity ON entity.id=embedding.entity_id
                  WHERE embedding.tenant_id=%s AND embedding.embedding_space_id=%s
                    AND entity.namespace='ENTERPRISE' AND entity.entity_type='Application'
                )
                SELECT source.entity_id AS left_id,neighbor.entity_id AS right_id,neighbor.score
                FROM application_vectors source
                CROSS JOIN LATERAL (
                  SELECT target.entity_id,
                    greatest(0,least(1,1-(target.embedding<=>source.embedding))) AS score
                  FROM application_vectors target
                  WHERE target.entity_id<>source.entity_id
                  ORDER BY target.embedding<=>source.embedding,target.entity_id
                  LIMIT 20
                ) neighbor
                WHERE source.entity_id<neighbor.entity_id
                """,
                (tenant_id,space_id),
            ).fetchall()
            for neighbor in neighbors:
                pair = (str(neighbor["left_id"]),str(neighbor["right_id"]))
                scores[pair] = max(scores.get(pair,0),float(neighbor["score"]))
        vector_signals[signal_key] = (space_id,scores)
    pair_set = set(candidate_pairs(features,max_pairs=max_pairs))
    pair_set.update(vector_signals["semantic"][1])
    pair_set.update(vector_signals["structural"][1])
    if len(pair_set)>max_pairs:
        raise ValueError(f"similarity candidate budget exceeded ({max_pairs})")
    persisted = 0
    evaluated = 0
    for left,right in sorted(pair_set):
        deterministic = deterministic_application_similarity(
            features[left],features[right],dependency_frequency=frequencies,corpus_size=len(features),
        )
        result = hybrid_application_similarity(
            deterministic,
            semantic_score=vector_signals["semantic"][1].get((left,right)),
            structural_score=vector_signals["structural"][1].get((left,right)),
        )
        evaluated += 1
        if float(result["score"])<minimum_score:
            continue
        connection.execute(
            """
            INSERT INTO application_similarity_candidate(
              tenant_id,left_application_id,right_application_id,score,method_version,
              components,overlap_features,differences,coverage,limitations,
              semantic_space_id,structural_space_id
            ) VALUES (%s,%s,%s,%s,'application-similarity/v1',%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT(tenant_id,left_application_id,right_application_id,method_version)
            DO UPDATE SET score=EXCLUDED.score,components=EXCLUDED.components,
              overlap_features=EXCLUDED.overlap_features,differences=EXCLUDED.differences,
              coverage=EXCLUDED.coverage,limitations=EXCLUDED.limitations,
              semantic_space_id=EXCLUDED.semantic_space_id,
              structural_space_id=EXCLUDED.structural_space_id,updated_at=now()
            """,
            (
                tenant_id,left,right,result["score"],Jsonb(result["components"]),
                Jsonb(result["overlaps"]),Jsonb(result["differences"]),
                Jsonb(result["coverage"]),Jsonb(result["limitations"]),
                vector_signals["semantic"][0],vector_signals["structural"][0],
            ),
        )
        persisted += 1
    return {"applications":len(features),"pairs_evaluated":evaluated,"candidates_persisted":persisted}


def record_embedding_heartbeat(database_url: str,worker_id: str,metadata: Mapping[str,object]) -> None:
    with psycopg.connect(database_url) as connection:
        connection.execute(
            """
            INSERT INTO service_heartbeat(service_key,instance_id,status,metadata)
            VALUES ('embeddings',%s,'RUNNING',%s)
            ON CONFLICT(service_key) DO UPDATE SET instance_id=EXCLUDED.instance_id,
              status='RUNNING',metadata=EXCLUDED.metadata,last_heartbeat_at=now()
            """,
            (worker_id,Jsonb(dict(metadata))),
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="Build tenant-scoped semantic entity embeddings")
    parser.add_argument("command",choices=("ensure-space","work","serve","evaluate","activate","similarity"))
    parser.add_argument("--tenant-id",type=UUID)
    parser.add_argument("--space-id",type=UUID)
    parser.add_argument("--poll-seconds",type=float,default=2.0)
    parser.add_argument("--max-jobs",type=int)
    args = parser.parse_args()
    database_url = os.environ.get("STACKGRAPH_DATABASE_URL")
    if not database_url:
        parser.error("STACKGRAPH_DATABASE_URL is required")
    encryption_key = os.environ.get("STACKGRAPH_CREDENTIAL_ENCRYPTION_KEY","stackgraph-local-development-credential-key")
    if args.command in {"ensure-space","similarity"} and args.tenant_id is None:
        parser.error("--tenant-id is required")
    if args.command in {"evaluate","activate"} and args.space_id is None:
        parser.error("--space-id is required")
    if args.command == "ensure-space":
        with psycopg.connect(database_url,row_factory=dict_row) as connection:
            print(json.dumps({"space_id":str(ensure_space(connection,args.tenant_id))},sort_keys=True))
        return
    if args.command == "evaluate":
        with psycopg.connect(database_url,row_factory=dict_row) as connection:
            print(json.dumps(dict(evaluate_space(connection,args.space_id,encryption_key=encryption_key)),sort_keys=True))
        return
    if args.command == "similarity":
        with psycopg.connect(database_url,row_factory=dict_row) as connection:
            print(json.dumps(dict(rebuild_similarity_candidates(connection,args.tenant_id)),sort_keys=True))
        return
    if args.command == "activate":
        with psycopg.connect(database_url,row_factory=dict_row) as connection:
            row = connection.execute("SELECT tenant_id,space_kind FROM embedding_space WHERE id=%s",(args.space_id,)).fetchone()
            if row is None:
                parser.error("embedding space not found")
            connection.execute(
                """INSERT INTO active_embedding_space(tenant_id,space_kind,embedding_space_id)
                VALUES (%s,%s,%s) ON CONFLICT(tenant_id,space_kind) DO UPDATE SET
                embedding_space_id=EXCLUDED.embedding_space_id,activated_at=now()""",
                (row["tenant_id"],row["space_kind"],args.space_id),
            )
            print(json.dumps({"activated":str(args.space_id)},sort_keys=True))
        return
    worker = EmbeddingWorker(database_url,encryption_key=encryption_key)
    completed = 0
    try:
        while True:
            if args.command == "serve":
                record_embedding_heartbeat(database_url,worker.worker_id,{"poll_seconds":args.poll_seconds})
            result = worker.run_once()
            print(json.dumps(asdict(result),sort_keys=True),flush=True)
            if result.claimed:
                completed += 1
            if args.command == "work" and (not result.claimed or (args.max_jobs and completed>=args.max_jobs)):
                break
            if args.command == "serve" and not result.claimed:
                time.sleep(args.poll_seconds)
    finally:
        worker.close()


if __name__ == "__main__":
    main()
