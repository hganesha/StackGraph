"""Derive ObservedMutation records from the estate's own history.

Phase 2D asks StackGraph to capture not just what exists but what changed and what happened
afterwards. The `observed_mutation` table has been correct since migration 053, but its only
writer was `POST /observed-mutations`, so change memory stayed empty unless an operator typed
outcomes in one at a time — and a simulation's history finding needs three comparable outcomes
before it will say anything at all.

The estate already records the change. A repository's `DEPENDS_ON` fact is superseded when a
rescan sees a different resolved version, and `system_from` / `system_to` bracket exactly when
that happened. That transition *is* an observed mutation; this module reads it and writes it
down, correlating it to the pull request that carried it when activity collection saw one.

Three lines are held deliberately:

* Only an increase becomes an `UPGRADE`. The ontology has no `DOWNGRADE`, and recording a
  rollback as an upgrade would poison the very history the simulator cites.
* `success` stays NULL. Observing that a version moved says nothing about whether it went well;
  claiming success from the absence of evidence is exactly the partial-data failure §9.1
  forbids. Incident and rollback correlation fills it in later, or a human does.
* Confidence is lower without a correlated pull request, because a change nobody can attribute
  to a merge is a weaker outcome than one that can be traced to a review.
"""

from __future__ import annotations

import argparse
import os
import re
from typing import Any, Iterator, Mapping
from uuid import UUID

import psycopg
from psycopg import Connection
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from .catalog import sha256_key


# A correlated pull request is a materially stronger outcome record than a bare version move.
CORRELATED_CONFIDENCE = 0.9
UNCORRELATED_CONFIDENCE = 0.8
# How far either side of a version transition a merged dependency change may sit and still be
# considered the thing that caused it.
CORRELATION_WINDOW_HOURS = 72
_NUMERIC = re.compile(r"\d+")


def _split_version(value: str) -> tuple[tuple[int, ...], tuple[tuple[int, Any], ...]]:
    """Split a version into its numeric release segments and everything after them.

    `2.0.0-rc1` becomes `((2, 0, 0), ((1, 'rc1'),))`; `2.0.0` becomes `((2, 0, 0), ())`. Keeping
    the two apart is what lets a prerelease sort *below* its own release, which a single
    lexical key cannot express: `('2','0','0')` is a prefix of `('2','0','0','rc1')`, so a plain
    tuple comparison ranks the release candidate higher than the release.
    """
    parts = [part for part in re.split(r"[.+\-_]", value) if part]
    release: list[int] = []
    index = 0
    while index < len(parts) and parts[index].isdigit():
        release.append(int(parts[index]))
        index += 1
    suffix = tuple(
        (0, int(part)) if part.isdigit() else (1, part.lower())
        for part in parts[index:]
    )
    return tuple(release), suffix


def is_upgrade(before: str, after: str) -> bool:
    """Report whether `after` is a later version than `before`.

    Anything that is not clearly an increase — equal, a downgrade, or a pair with no numeric
    content to compare — is not an upgrade, because a wrong direction here would teach the
    simulator the opposite of what actually happened.

    A prerelease precedes its own release: `2.0.0-rc1` to `2.0.0` is an upgrade, and the
    reverse is not. Treating them as equal would silently drop every release-cutting change
    out of change memory.
    """
    if not before or not after or before == after:
        return False
    if not _NUMERIC.search(before) or not _NUMERIC.search(after):
        return False
    before_release, before_suffix = _split_version(before)
    after_release, after_suffix = _split_version(after)
    if before_release != after_release:
        return after_release > before_release
    if bool(before_suffix) != bool(after_suffix):
        # Same release numbers, and exactly one carries a prerelease suffix. The bare one wins.
        return not after_suffix
    return after_suffix > before_suffix


def _transitions(
    connection: Connection[dict[str, Any]], tenant_id: UUID, *, limit: int,
) -> Iterator[Mapping[str, Any]]:
    """Yield superseded-to-current dependency version transitions for one tenant.

    A transition is a pair of `DEPENDS_ON` facts on the same repository and package where the
    older one has been closed off (`system_to` set) and the resolved version differs.
    """
    rows = connection.execute(
        """
        WITH resolved AS (
          SELECT fact.id, fact.subject_entity_id repository_entity_id,
                 fact.object_entity_id package_entity_id,
                 fact.system_from, fact.system_to, fact.observed_at, fact.source_revision,
                 fact.confidence,
                 coalesce(
                   resolution.resolved_version,
                   identity.package_version,
                   fact.properties->>'resolved_version'
                 ) version,
                 identity.package_name
          FROM fact_assertion fact
          JOIN entity repository ON repository.id=fact.subject_entity_id
                                AND repository.entity_type='Repository'
          JOIN package_registry_identity identity ON identity.entity_id=fact.object_entity_id
          LEFT JOIN dependency_resolution resolution
                 ON resolution.fact_assertion_id=fact.id
          WHERE fact.tenant_id=%s AND fact.predicate='DEPENDS_ON'
        ), paired AS (
          SELECT before.repository_entity_id, before.package_entity_id, before.package_name,
                 before.id before_fact_id, after.id after_fact_id,
                 before.version before_version, after.version after_version,
                 before.system_to changed_at, after.source_revision,
                 least(before.confidence, after.confidence) confidence
          FROM resolved before
          JOIN LATERAL (
            SELECT * FROM resolved candidate
            WHERE candidate.repository_entity_id=before.repository_entity_id
              AND candidate.package_entity_id=before.package_entity_id
              AND candidate.system_from>=before.system_to
            ORDER BY candidate.system_from, candidate.id LIMIT 1
          ) after ON true
          WHERE before.system_to IS NOT NULL
            AND before.version IS NOT NULL AND after.version IS NOT NULL
            AND before.version<>after.version
        )
        SELECT paired.*, repository.canonical_key repository_key, repository.name repository_name
        FROM paired
        JOIN entity repository ON repository.id=paired.repository_entity_id
        ORDER BY paired.changed_at DESC, paired.after_fact_id
        LIMIT %s
        """,
        (tenant_id, limit),
    ).fetchall()
    yield from rows


def _correlated_pull_request(
    connection: Connection[dict[str, Any]], tenant_id: UUID, transition: Mapping[str, Any],
) -> Mapping[str, Any] | None:
    return connection.execute(
        """
        SELECT provider_event_key, pull_request_number, occurred_at, title, source_url,
               actor_classification, metadata
        FROM repository_activity_event
        WHERE tenant_id=%s AND repository_entity_id=%s AND event_type='DEPENDENCY_CHANGE'
          AND occurred_at BETWEEN %s - make_interval(hours => %s)
                              AND %s + make_interval(hours => %s)
        ORDER BY abs(extract(epoch FROM occurred_at - %s)), provider_event_key
        LIMIT 1
        """,
        (
            tenant_id, transition["repository_entity_id"],
            transition["changed_at"], CORRELATION_WINDOW_HOURS,
            transition["changed_at"], CORRELATION_WINDOW_HOURS,
            transition["changed_at"],
        ),
    ).fetchone()


def derive_observed_mutations(
    connection: Connection[dict[str, Any]], *, tenant_id: UUID, limit: int = 500,
) -> dict[str, int]:
    """Write an ObservedMutation for every attributable dependency upgrade. Returns counts."""
    connection.execute("SELECT set_config('app.tenant_id',%s,true)", (str(tenant_id),))
    examined = 0
    written = 0
    correlated = 0
    skipped_not_upgrade = 0
    for transition in _transitions(connection, tenant_id, limit=limit):
        examined += 1
        before = str(transition["before_version"])
        after = str(transition["after_version"])
        if not is_upgrade(before, after):
            skipped_not_upgrade += 1
            continue
        pull_request = _correlated_pull_request(connection, tenant_id, transition)
        if pull_request is not None:
            correlated += 1
        correlation_key = (
            f"dependency-change:{transition['repository_entity_id']}:"
            f"{transition['package_entity_id']}:{transition['before_fact_id']}:"
            f"{transition['after_fact_id']}"
        )
        scope = {
            "kind": "REPOSITORY",
            "entity_id": str(transition["repository_entity_id"]),
            "label": transition["repository_name"],
        }
        observed_impact = {
            "repositories": 1,
            "package_name": transition["package_name"],
            "source_revision": transition["source_revision"],
        }
        payload = {
            "schema_version": "observed-mutation/1.0.0",
            "source_kind": "PULL_REQUEST" if pull_request else "COMMIT",
            "predicate": "UPGRADE",
            "subject_entity_id": str(transition["package_entity_id"]),
            "before": {"version": before},
            "after": {"version": after},
            "scope": scope,
            "observed_impact": observed_impact,
            "unexpected_impact": {},
            # Not False. Nothing here observed whether the change went well.
            "success": None,
            "intervention_required": False,
            "rolled_back": False,
            "evidence_fact_ids": sorted(
                {str(transition["before_fact_id"]), str(transition["after_fact_id"])}
            ),
            "graph_watermark_before": None,
            "predicted_simulation_run_id": None,
            "resolution": None,
            "confidence": CORRELATED_CONFIDENCE if pull_request else UNCORRELATED_CONFIDENCE,
            "observed_at": transition["changed_at"].isoformat(),
        }
        provenance = {
            "derived_by": "change-memory-derivation/1.0.0",
            "correlation_window_hours": CORRELATION_WINDOW_HOURS,
        }
        if pull_request is not None:
            provenance |= {
                "pull_request_number": pull_request["pull_request_number"],
                "pull_request_event_key": pull_request["provider_event_key"],
                "actor_classification": pull_request["actor_classification"],
                "manifest_paths": (pull_request["metadata"] or {}).get("manifest_paths") or [],
            }
        observed_impact["provenance"] = provenance
        inserted = connection.execute(
            """
            INSERT INTO observed_mutation(
              tenant_id,correlation_key,source_kind,predicate,subject_entity_id,
              before_state,after_state,scope,observed_impact,unexpected_impact,
              success,intervention_required,rolled_back,evidence_fact_ids,
              graph_watermark_before,predicted_simulation_run_id,resolution,confidence,
              input_fingerprint,observed_at,created_by
            ) VALUES (
              %s,%s,%s,'UPGRADE',%s,%s,%s,%s,%s,'{}',NULL,false,false,%s,
              NULL,NULL,NULL,%s,%s,%s,'change-memory-derivation'
            )
            ON CONFLICT DO NOTHING RETURNING id
            """,
            (
                tenant_id, correlation_key, payload["source_kind"],
                transition["package_entity_id"],
                Jsonb(payload["before"]), Jsonb(payload["after"]), Jsonb(scope),
                Jsonb(observed_impact),
                [UUID(value) for value in payload["evidence_fact_ids"]],
                payload["confidence"], sha256_key(payload), transition["changed_at"],
            ),
        ).fetchone()
        written += int(inserted is not None)
    return {
        "examined": examined,
        "written": written,
        "correlated_to_pull_request": correlated,
        "skipped_not_an_upgrade": skipped_not_upgrade,
    }


def _database_url() -> str:
    url = os.environ.get("STACKGRAPH_DATABASE_URL")
    if not url:
        raise SystemExit("STACKGRAPH_DATABASE_URL is required")
    return url


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tenant-id", required=True)
    parser.add_argument("--limit", type=int, default=500)
    arguments = parser.parse_args(argv)
    with psycopg.connect(_database_url(), row_factory=dict_row) as connection:
        counts = derive_observed_mutations(
            connection, tenant_id=UUID(arguments.tenant_id), limit=arguments.limit,
        )
        connection.commit()
    for key in sorted(counts):
        print(f"{key}={counts[key]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
