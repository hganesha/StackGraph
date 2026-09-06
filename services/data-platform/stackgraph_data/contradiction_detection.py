"""Turn observed source disagreements into governed contradictions.

§32 asks StackGraph to maintain the assumptions embedded across code, configuration, and
documentation. §33 asks it to detect where those sources disagree — its worked example being a
runtime whose version is stated one way by code, another by the container, and a third by the
documentation. Both existed only as an API a human could type into: `estate_assumption` and
`estate_contradiction` had no writer but `POST /assumptions`, so nothing was ever detected.

The scanner now emits a `runtime_contradiction` observation whenever it sees such a
disagreement. This module promotes those observations into the governed ledger, which is what
makes them consequential: the compiler already refuses to compile a mutation whose subject or
scope has an open contradiction, so a repository that cannot agree with itself about its own
runtime stops being simulatable until somebody resolves it.

Two principles, both from §33:

* StackGraph does not decide which source is right. Every claim is recorded with its source and
  its evidence, and the assumption is stored at OPEN with the majority reading as its statement
  only because a statement is structurally required — never as a verdict.
* Re-running is idempotent and non-destructive. An existing contradiction is left alone rather
  than recreated, so a human resolution is never silently reopened by the next scan.
"""

from __future__ import annotations

import argparse
import os
from collections import Counter
from typing import Any, Mapping
from uuid import UUID

import psycopg
from psycopg import Connection
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb


DETECTION_METHOD = "contradiction-detection/1.0.0"
# A disagreement between declared sources is a strong observation, but the sources themselves
# vary in authority, so the assumption it produces is not asserted with certainty.
ASSUMPTION_CONFIDENCE = 0.75
CLAIM_CONFIDENCE = {
    # What production actually runs, and what a developer actually runs, outrank what prose says.
    "CONTAINER_BASE_IMAGE": 0.95,
    "VERSION_PIN": 0.9,
    "MANIFEST_ENGINE": 0.85,
    "DOCUMENTATION": 0.5,
}


def _observations(
    connection: Connection[dict[str, Any]], tenant_id: UUID, *, limit: int,
) -> list[Mapping[str, Any]]:
    return connection.execute(
        """
        SELECT fact.id fact_id, fact.subject_entity_id, fact.object_value, fact.observed_at,
               entity.name repository_name
        FROM fact_assertion fact
        JOIN entity ON entity.id=fact.subject_entity_id
        WHERE fact.tenant_id=%s AND fact.predicate='HAS_PROPERTY'
          AND fact.system_to IS NULL
          AND fact.object_value->>'record_kind'='runtime_contradiction'
        ORDER BY fact.observed_at DESC, fact.id
        LIMIT %s
        """,
        (tenant_id, limit),
    ).fetchall()


def _existing_contradiction(
    connection: Connection[dict[str, Any]], tenant_id: UUID, subject_id: UUID, dimension: str,
) -> Mapping[str, Any] | None:
    return connection.execute(
        """
        SELECT contradiction.id, contradiction.status
        FROM estate_contradiction contradiction
        JOIN estate_assumption assumption ON assumption.id=contradiction.assumption_id
        WHERE contradiction.tenant_id=%s AND assumption.subject_entity_id=%s
          AND assumption.dimension=%s
        ORDER BY contradiction.created_at DESC LIMIT 1
        """,
        (tenant_id, subject_id, dimension),
    ).fetchone()


def detect_contradictions(
    connection: Connection[dict[str, Any]], *, tenant_id: UUID, limit: int = 500,
) -> dict[str, int]:
    """Promote observed source disagreements into the governed ledger. Returns counts."""
    connection.execute("SELECT set_config('app.tenant_id',%s,true)", (str(tenant_id),))
    examined = 0
    created = 0
    already_recorded = 0
    for observation in _observations(connection, tenant_id, limit=limit):
        examined += 1
        value = observation["object_value"]
        dimension = str(value.get("dimension") or "")
        claims = list(value.get("claims") or ())
        if not dimension or len(claims) < 2:
            continue
        subject_id = observation["subject_entity_id"]
        existing = _existing_contradiction(connection, tenant_id, subject_id, dimension)
        if existing is not None:
            # A resolved contradiction stays resolved. Recreating it on every scan would make
            # human adjudication worthless.
            already_recorded += 1
            continue

        runtime = str(value.get("runtime") or "runtime")
        majors = Counter(str(claim.get("major_version")) for claim in claims)
        # A statement is structurally required, so the most-claimed version fills it. The
        # status stays OPEN and every competing claim is recorded, because §33 is explicit that
        # surfacing the conflict is the job and deciding it is not.
        leading = majors.most_common(1)[0][0]
        assumption = connection.execute(
            """
            INSERT INTO estate_assumption(
              tenant_id,subject_entity_id,dimension,statement,status,authority,confidence,
              last_verified_at,created_by
            ) VALUES (%s,%s,%s,%s,'OPEN',%s,%s,%s,%s)
            RETURNING id
            """,
            (
                tenant_id, subject_id, dimension,
                f"{observation['repository_name']} targets {runtime} major version {leading}.",
                DETECTION_METHOD, ASSUMPTION_CONFIDENCE, observation["observed_at"],
                "contradiction-detection",
            ),
        ).fetchone()
        assumption_id = assumption["id"]
        connection.execute(
            """
            INSERT INTO estate_assumption_dependent(tenant_id,assumption_id,entity_id)
            VALUES (%s,%s,%s) ON CONFLICT DO NOTHING
            """,
            (tenant_id, assumption_id, subject_id),
        )

        claim_ids: list[UUID] = []
        for claim in claims:
            source_kind = str(claim.get("source_kind"))
            row = connection.execute(
                """
                INSERT INTO estate_assumption_claim(
                  tenant_id,assumption_id,claim_key,display_value,source_key,assertion_class,
                  confidence,observed_at
                ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT(assumption_id,claim_key,source_key) DO NOTHING
                RETURNING id
                """,
                (
                    tenant_id, assumption_id, str(claim.get("major_version")),
                    f"{claim.get('path')} declares {runtime} {claim.get('declared_version')}",
                    f"{source_kind}:{claim.get('path')}",
                    # Documentation is prose about the estate, not a reading of it.
                    "INFERRED" if source_kind == "DOCUMENTATION" else "DECLARED",
                    CLAIM_CONFIDENCE.get(source_kind, 0.6), observation["observed_at"],
                ),
            ).fetchone()
            if row is None:
                continue
            claim_ids.append(row["id"])
            connection.execute(
                """
                INSERT INTO estate_assumption_claim_evidence(
                  tenant_id,claim_id,fact_assertion_id,polarity
                ) VALUES (%s,%s,%s,%s) ON CONFLICT DO NOTHING
                """,
                (
                    tenant_id, row["id"], observation["fact_id"],
                    "SUPPORTING" if str(claim.get("major_version")) == leading else "OPPOSING",
                ),
            )

        contradiction = connection.execute(
            """
            INSERT INTO estate_contradiction(
              tenant_id,assumption_id,subject_entity_id,dimension,status,severity,created_by
            ) VALUES (%s,%s,%s,%s,'OPEN',%s,%s)
            RETURNING id
            """,
            (
                tenant_id, assumption_id, subject_id, dimension,
                # Three or more competing versions is a governance problem, not a drift.
                "HIGH" if len(majors) > 2 else "MEDIUM",
                "contradiction-detection",
            ),
        ).fetchone()
        for claim_id in claim_ids:
            connection.execute(
                """
                INSERT INTO estate_contradiction_claim(tenant_id,contradiction_id,claim_id)
                VALUES (%s,%s,%s) ON CONFLICT DO NOTHING
                """,
                (tenant_id, contradiction["id"], claim_id),
            )
        created += 1
    return {
        "examined": examined,
        "contradictions_created": created,
        "already_recorded": already_recorded,
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
        counts = detect_contradictions(
            connection, tenant_id=UUID(arguments.tenant_id), limit=arguments.limit,
        )
        connection.commit()
    for key in sorted(counts):
        print(f"{key}={counts[key]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
