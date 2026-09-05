import os
from uuid import uuid4

import psycopg
import pytest


pytestmark = pytest.mark.skipif(
    "STACKGRAPH_TEST_DATABASE_URL" not in os.environ,
    reason="STACKGRAPH_TEST_DATABASE_URL is required for database integration tests",
)


def _expect_database_error(connection, statement, params=()) -> None:
    connection.execute("SAVEPOINT expected_phase2_error")
    with pytest.raises(psycopg.Error):
        connection.execute(statement, params)
    connection.execute("ROLLBACK TO SAVEPOINT expected_phase2_error")
    connection.execute("RELEASE SAVEPOINT expected_phase2_error")


def test_phase2_terminal_immutability_tenant_integrity_and_evidence_fks() -> None:
    database_url = os.getenv(
        "STACKGRAPH_TEST_ADMIN_DATABASE_URL", os.environ["STACKGRAPH_TEST_DATABASE_URL"],
    )
    tenant_id = uuid4()
    other_tenant_id = uuid4()
    entity_id = uuid4()
    change_set_id = uuid4()
    other_change_set_id = uuid4()
    mutation_id = uuid4()
    simulation_id = uuid4()
    finding_id = uuid4()

    with psycopg.connect(database_url) as connection:
        try:
            connection.execute("SELECT set_config('app.tenant_id',%s,true)", (str(tenant_id),))
            connection.execute(
                "INSERT INTO tenant(id,tenant_key,name) VALUES (%s,%s,'Phase 2 DB test')",
                (tenant_id, f"phase2-db-{tenant_id}"),
            )
            connection.execute("SELECT set_config('app.tenant_id',%s,true)", (str(other_tenant_id),))
            connection.execute(
                "INSERT INTO tenant(id,tenant_key,name) VALUES (%s,%s,'Other tenant')",
                (other_tenant_id, f"phase2-db-{other_tenant_id}"),
            )
            connection.execute("SELECT set_config('app.tenant_id',%s,true)", (str(tenant_id),))
            connection.execute(
                """
                INSERT INTO entity(id,tenant_id,namespace,entity_type,canonical_key,name,properties)
                VALUES (%s,%s,'TECHNOLOGY','Package',%s,'test-package','{}')
                """,
                (entity_id, tenant_id, f"pkg:npm/test-{entity_id}"),
            )
            connection.execute(
                """
                INSERT INTO change_set(
                  id,tenant_id,lifecycle,input_fingerprint,idempotency_key,provenance,created_by
                ) VALUES (%s,%s,'VALIDATED',%s,%s,'{}','test')
                """,
                (change_set_id, tenant_id, "sha256:" + "1" * 64, f"compile-{change_set_id}"),
            )
            connection.execute(
                """
                INSERT INTO mutation(
                  id,tenant_id,change_set_id,ordinal,predicate,subject_entity_id,
                  subject_resolution,before_state,after_state,scope,constraints,provenance,
                  input_fingerprint,lifecycle
                ) VALUES (
                  %s,%s,%s,0,'UPGRADE',%s,'RESOLVED','{}','{}',%s,'{}','{}',%s,'VALIDATED'
                )
                """,
                (
                    mutation_id, tenant_id, change_set_id, entity_id,
                    '{"id":"estate","kind":"ESTATE","label":"Estate","affected_count":1,"version_distribution":[{"version":"1","count":1}],"evidence_fact_ids":["00000000-0000-0000-0000-000000000001"]}',
                    "sha256:" + "2" * 64,
                ),
            )

            _expect_database_error(
                connection, "UPDATE change_set SET atomic=false WHERE id=%s", (change_set_id,),
            )
            _expect_database_error(
                connection, "UPDATE mutation SET before_state='{}' WHERE id=%s", (mutation_id,),
            )

            connection.execute(
                """
                INSERT INTO simulation_run(
                  id,tenant_id,change_set_id,idempotency_key,status,estate_watermark,
                  policy_version,provider_version,input_fingerprint,created_by
                ) VALUES (%s,%s,%s,%s,'QUEUED','facts:test','policy/1','provider/1',%s,'test')
                """,
                (
                    simulation_id, tenant_id, change_set_id, f"simulate-{simulation_id}",
                    "sha256:" + "3" * 64,
                ),
            )
            connection.execute(
                """
                INSERT INTO simulation_finding(
                  id,tenant_id,simulation_run_id,rule_key,rule_version,classification,
                  severity,title,detail,confidence,deterministic_key
                ) VALUES (%s,%s,%s,'test.rule','1','INFORMATIONAL','INFO','Test','Test',1,'test')
                """,
                (finding_id, tenant_id, simulation_id),
            )
            connection.execute(
                "UPDATE simulation_run SET status='SUCCEEDED',result_hash=%s WHERE id=%s",
                ("sha256:" + "4" * 64, simulation_id),
            )
            _expect_database_error(
                connection, "UPDATE simulation_run SET result_hash=%s WHERE id=%s",
                ("sha256:" + "5" * 64, simulation_id),
            )
            _expect_database_error(
                connection, "UPDATE simulation_finding SET title='Changed' WHERE id=%s", (finding_id,),
            )

            _expect_database_error(
                connection,
                """
                INSERT INTO observed_mutation(
                  tenant_id,correlation_key,source_kind,predicate,subject_entity_id,
                  before_state,after_state,scope,observed_impact,evidence_fact_ids,
                  confidence,input_fingerprint,observed_at,created_by
                ) VALUES (%s,%s,'MANUAL','UPGRADE',%s,'{}','{}','{}','{}',%s,1,%s,now(),'test')
                """,
                (
                    tenant_id, f"outcome-{uuid4()}", entity_id, [uuid4()],
                    "sha256:" + "6" * 64,
                ),
            )

            connection.execute("SELECT set_config('app.tenant_id',%s,true)", (str(other_tenant_id),))
            connection.execute(
                """
                INSERT INTO change_set(
                  id,tenant_id,lifecycle,input_fingerprint,idempotency_key,provenance,created_by
                ) VALUES (%s,%s,'VALIDATED',%s,%s,'{}','test')
                """,
                (
                    other_change_set_id, other_tenant_id, "sha256:" + "7" * 64,
                    f"compile-{other_change_set_id}",
                ),
            )
            connection.execute("SELECT set_config('app.tenant_id',%s,true)", (str(tenant_id),))
            _expect_database_error(
                connection,
                """
                INSERT INTO mutation(
                  tenant_id,change_set_id,ordinal,predicate,subject_entity_id,subject_resolution,
                  before_state,after_state,scope,provenance,input_fingerprint,lifecycle
                ) VALUES (%s,%s,1,'UPGRADE',%s,'RESOLVED','{}','{}','{}','{}',%s,'VALIDATED')
                """,
                (tenant_id, other_change_set_id, entity_id, "sha256:" + "8" * 64),
            )
        finally:
            connection.rollback()
