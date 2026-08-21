from __future__ import annotations

import argparse
from dataclasses import dataclass
from uuid import UUID

import psycopg
from psycopg.rows import dict_row

from stackgraph_ai.governance import EcosystemDemand, evaluate_ecosystem_admission


ECOSYSTEM_SEQUENCE = {"PYPI": 1, "MAVEN": 2, "CARGO": 3, "NUGET": 4}
PURL_TYPE = {"PYPI": "pypi", "MAVEN": "maven", "CARGO": "cargo", "NUGET": "nuget"}
METADATA_PARITY = {"PYPI": True, "MAVEN": False, "CARGO": False, "NUGET": False}


@dataclass(frozen=True, slots=True)
class RecordedAdmission:
    ecosystem: str
    admitted: bool
    observed_repositories: int
    observed_dependency_share: float
    reasons: tuple[str, ...]
    decision_fingerprint: str


def evaluate_and_record(
    database_url: str,
    *,
    tenant_id: UUID,
    ecosystem: str,
    actor_key: str,
    minimum_repositories: int = 10,
    minimum_dependency_share: float = 0.02,
) -> RecordedAdmission:
    normalized = ecosystem.upper()
    if normalized not in ECOSYSTEM_SEQUENCE:
        raise ValueError("ecosystem must be one of PYPI, MAVEN, CARGO, or NUGET")
    sequence = ECOSYSTEM_SEQUENCE[normalized]
    with psycopg.connect(database_url, row_factory=dict_row) as connection:
        demand = connection.execute(
            """
            SELECT count(DISTINCT fact.subject_entity_id)
                     FILTER (WHERE package.canonical_key LIKE %s) observed_repositories,
                   count(*) FILTER (WHERE package.canonical_key LIKE %s)::numeric
                     /nullif(count(*),0) observed_dependency_share
            FROM dependency_usage_summary usage
            JOIN fact_assertion fact ON fact.id=usage.dependency_fact_assertion_id
            JOIN source_snapshot snapshot ON snapshot.id=fact.source_snapshot_id
            JOIN entity package ON package.id=fact.object_entity_id
            WHERE usage.tenant_id=%s AND fact.tenant_id=%s
              AND fact.system_to IS NULL AND snapshot.status='PUBLISHED'
              AND (usage.referenced OR usage.runtime_observed='OBSERVED')
            """,
            (
                f"pkg:{PURL_TYPE[normalized]}/%", f"pkg:{PURL_TYPE[normalized]}/%",
                tenant_id, tenant_id,
            ),
        ).fetchone()
        predecessor_admitted = True
        if sequence > 1:
            predecessor = next(
                key for key, value in ECOSYSTEM_SEQUENCE.items() if value == sequence - 1
            )
            predecessor_admitted = connection.execute(
                "SELECT 1 FROM ecosystem_admission WHERE tenant_id=%s AND ecosystem=%s AND status='ADMITTED'",
                (tenant_id, predecessor),
            ).fetchone() is not None
        calibration_gate_passed = connection.execute(
            """
            SELECT 1 FROM modernization_calibration_corpus
            WHERE tenant_id=%s AND status='ACTIVE' AND promotion_passed
            """,
            (tenant_id,),
        ).fetchone() is not None
        observed_repositories = int(demand["observed_repositories"] or 0)
        observed_dependency_share = float(demand["observed_dependency_share"] or 0)
        decision = evaluate_ecosystem_admission(
            EcosystemDemand(
                ecosystem=normalized,
                observed_repositories=observed_repositories,
                observed_dependency_share=observed_dependency_share,
                metadata_parity=METADATA_PARITY[normalized],
                calibration_gate_passed=calibration_gate_passed,
            ),
            predecessor_admitted=predecessor_admitted,
            minimum_repositories=minimum_repositories,
            minimum_dependency_share=minimum_dependency_share,
        )
        connection.execute(
            """
            INSERT INTO ecosystem_admission(
              tenant_id,ecosystem,sequence,status,observed_repositories,
              observed_dependency_share,minimum_repositories,minimum_dependency_share,
              metadata_parity,calibration_gate_passed,decision_fingerprint,reasons,decided_by
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT(tenant_id,ecosystem) DO UPDATE SET
              status=EXCLUDED.status,observed_repositories=EXCLUDED.observed_repositories,
              observed_dependency_share=EXCLUDED.observed_dependency_share,
              minimum_repositories=EXCLUDED.minimum_repositories,
              minimum_dependency_share=EXCLUDED.minimum_dependency_share,
              metadata_parity=EXCLUDED.metadata_parity,
              calibration_gate_passed=EXCLUDED.calibration_gate_passed,
              decision_fingerprint=EXCLUDED.decision_fingerprint,reasons=EXCLUDED.reasons,
              decided_by=EXCLUDED.decided_by,decided_at=now()
            """,
            (
                tenant_id, normalized, sequence,
                "ADMITTED" if decision.admitted else "PROPOSED",
                observed_repositories, observed_dependency_share,
                minimum_repositories, minimum_dependency_share,
                METADATA_PARITY[normalized], calibration_gate_passed,
                decision.fingerprint, list(decision.reasons), actor_key,
            ),
        )
    return RecordedAdmission(
        ecosystem=normalized, admitted=decision.admitted,
        observed_repositories=observed_repositories,
        observed_dependency_share=observed_dependency_share,
        reasons=decision.reasons, decision_fingerprint=decision.fingerprint,
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Evaluate one ecosystem against measured-demand admission gates"
    )
    parser.add_argument("--database-url", required=True)
    parser.add_argument("--tenant-id", required=True, type=UUID)
    parser.add_argument("--ecosystem", required=True, choices=tuple(ECOSYSTEM_SEQUENCE))
    parser.add_argument("--actor-key", required=True)
    arguments = parser.parse_args()
    result = evaluate_and_record(
        arguments.database_url, tenant_id=arguments.tenant_id,
        ecosystem=arguments.ecosystem, actor_key=arguments.actor_key,
    )
    print(result)


if __name__ == "__main__":
    main()
