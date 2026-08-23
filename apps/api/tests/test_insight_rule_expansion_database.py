import asyncio
import json
import os
from uuid import UUID

import psycopg
import pytest

from app.config import Settings
from app.database import Database
from app.deterministic_insights import list_deterministic_insights
from tests.golden_billing import (
    REPOSITORY_ID,
    TENANT_ID,
    install_golden_billing,
    remove_golden_billing,
)


pytestmark = pytest.mark.skipif(
    "STACKGRAPH_TEST_DATABASE_URL" not in os.environ,
    reason="STACKGRAPH_TEST_DATABASE_URL is required for database integration tests",
)


SNAPSHOT_ID = "00000000-0000-4000-8000-000000007103"
ARTIFACT_ID = "00000000-0000-4000-8000-000000007104"
PUBLIC_REGISTRY_ID = "00000000-0000-4000-8000-000000007005"
PRIVATE_REGISTRY_ID = "00000000-0000-4000-8000-000000009001"
PUBLIC_PYPI_REGISTRY_ID = "00000000-0000-4000-8000-000000009006"
SECOND_REPOSITORY_ID = "00000000-0000-4000-8000-000000009002"
PRIVATE_DEPENDENCY_ID = "00000000-0000-4000-8000-000000009003"
PUBLIC_COLLISION_ID = "00000000-0000-4000-8000-000000009004"
LICENSE_DEPENDENCY_ID = "00000000-0000-4000-8000-000000009005"


def _scope(connection: psycopg.Connection) -> None:
    connection.execute("SELECT set_config('app.tenant_id', %s, true)", (TENANT_ID,))


def _insert_fact(
    connection: psycopg.Connection,
    *,
    fact_id: str,
    subject_id: str,
    predicate: str,
    object_entity_id: str | None = None,
    object_value: dict | None = None,
    properties: dict | None = None,
) -> None:
    connection.execute(
        """
        INSERT INTO fact_assertion(
          id,tenant_id,source_snapshot_id,subject_entity_id,predicate,
          object_entity_id,object_value,assertion_class,confidence,
          logical_key,idempotency_key,source_revision,extractor_key,
          extractor_version,properties,observed_at
        ) VALUES (
          %s,%s,%s,%s,%s,%s,%s::jsonb,'DECLARED',1,
          'sha256:'||encode(digest(%s,'sha256'),'hex'),
          'sha256:'||encode(digest(%s,'sha256'),'hex'),
          'phase-1-fixture','phase-1-fixture','1.0.0',%s::jsonb,now()
        )
        """,
        (
            fact_id,
            TENANT_ID,
            SNAPSHOT_ID,
            subject_id,
            predicate,
            object_entity_id,
            json.dumps(object_value) if object_value is not None else None,
            f"logical:{fact_id}",
            f"idempotency:{fact_id}",
            json.dumps(properties or {}),
        ),
    )
    connection.execute(
        """
        INSERT INTO evidence(
          tenant_id,fact_assertion_id,source_artifact_id,evidence_type,locator,observed_at
        ) VALUES (%s,%s,%s,'FIXTURE',%s::jsonb,now())
        """,
        (TENANT_ID, fact_id, ARTIFACT_ID, json.dumps({"path": f"phase-1/{fact_id}"})),
    )


def _install_expanded_rule_fixture(database_url: str) -> None:
    install_golden_billing(database_url)
    with psycopg.connect(database_url) as connection:
        _scope(connection)
        connection.execute(
            """
            INSERT INTO source_system(id,tenant_id,source_key,kind,base_uri)
            VALUES (
              '00000000-0000-4000-8000-000000009000',%s,
              'npm-private','PACKAGE_REGISTRY','https://npm.acme.test/'
            )
            """,
            (TENANT_ID,),
        )
        connection.execute(
            """
            INSERT INTO package_registry(
              id,tenant_id,source_system_id,registry_key,origin_uri,
              normalized_origin_uri,ecosystem,visibility,auth_mode
            ) VALUES (
              %s,%s,'00000000-0000-4000-8000-000000009000','npm-private',
              'https://npm.acme.test/','https://npm.acme.test/','NPM','PRIVATE','TOKEN'
            ),(
              %s,%s,'00000000-0000-4000-8000-000000009000','pypi-public',
              'https://pypi.org/','https://pypi.org/','PYPI','PUBLIC','NONE'
            )
            """,
            (PRIVATE_REGISTRY_ID, TENANT_ID, PUBLIC_PYPI_REGISTRY_ID, TENANT_ID),
        )
        connection.execute(
            """
            INSERT INTO entity(
              id,tenant_id,namespace,entity_type,canonical_key,name,properties,last_seen_at
            ) VALUES
              (%s,%s,'ENTERPRISE','Repository','github:repo:phase-1-copy','phase-1-copy','{}',now()),
              (%s,%s,'TECHNOLOGY','PackageVersion','pkg:npm/%%40acme/shared@1.0.0','@acme/shared 1.0.0','{}',now()),
              (%s,%s,'TECHNOLOGY','PackageVersion','pkg:npm/%%40acme/shared@1.0.0-public','@acme/shared public 1.0.0','{}',now()),
              (%s,%s,'TECHNOLOGY','PackageVersion','pkg:pypi/copyleft-lib@1.0.0','copyleft-lib 1.0.0','{}',now())
            """,
            (
                SECOND_REPOSITORY_ID,
                TENANT_ID,
                PRIVATE_DEPENDENCY_ID,
                TENANT_ID,
                PUBLIC_COLLISION_ID,
                TENANT_ID,
                LICENSE_DEPENDENCY_ID,
                TENANT_ID,
            ),
        )
        connection.execute(
            """
            INSERT INTO package_registry_identity(
              id,tenant_id,entity_id,package_registry_id,package_name,package_version,purl,
              visibility,last_seen_at
            ) VALUES
              ('00000000-0000-4000-8000-000000009010',%s,%s,%s,'@acme/shared','1.0.0','pkg:npm/%%40acme/shared@1.0.0','PRIVATE',now()),
              ('00000000-0000-4000-8000-000000009011',%s,%s,%s,'@acme/shared','1.0.0','pkg:npm/%%40acme/shared@1.0.0','PUBLIC',now()),
              ('00000000-0000-4000-8000-000000009012',%s,%s,%s,'copyleft-lib','1.0.0','pkg:pypi/copyleft-lib@1.0.0','PUBLIC',now())
            """,
            (
                TENANT_ID,
                PRIVATE_DEPENDENCY_ID,
                PRIVATE_REGISTRY_ID,
                TENANT_ID,
                PUBLIC_COLLISION_ID,
                PUBLIC_REGISTRY_ID,
                TENANT_ID,
                LICENSE_DEPENDENCY_ID,
                PUBLIC_PYPI_REGISTRY_ID,
            ),
        )

        confusion_fact = "00000000-0000-4000-8000-000000009101"
        license_fact = "00000000-0000-4000-8000-000000009102"
        metadata_fact = "00000000-0000-4000-8000-000000009103"
        clone_fact_left = "00000000-0000-4000-8000-000000009104"
        clone_fact_right = "00000000-0000-4000-8000-000000009105"
        vendored_fact = "00000000-0000-4000-8000-000000009106"
        _insert_fact(
            connection,
            fact_id=confusion_fact,
            subject_id=REPOSITORY_ID,
            predicate="DEPENDS_ON",
            object_entity_id=PRIVATE_DEPENDENCY_ID,
            properties={"direct": True},
        )
        _insert_fact(
            connection,
            fact_id=license_fact,
            subject_id=REPOSITORY_ID,
            predicate="DEPENDS_ON",
            object_entity_id=LICENSE_DEPENDENCY_ID,
            properties={"direct": True},
        )
        _insert_fact(
            connection,
            fact_id=metadata_fact,
            subject_id=LICENSE_DEPENDENCY_ID,
            predicate="HAS_PROPERTY",
            object_value={
                "record_kind": "deps_dev_version_metadata",
                "licenses": ["GPL-3.0-only"],
            },
        )
        for fact_id, repository_id, path in (
            (clone_fact_left, REPOSITORY_ID, "src/shared.py"),
            (clone_fact_right, SECOND_REPOSITORY_ID, "lib/shared.py"),
            (vendored_fact, REPOSITORY_ID, "vendor/legacy.py"),
        ):
            _insert_fact(
                connection,
                fact_id=fact_id,
                subject_id=repository_id,
                predicate="HAS_PROPERTY",
                object_value={
                    "record_kind": "code_implementation_summary",
                    "path": path,
                    **({
                        "vendored_package_key": "pkg:pypi/legacy",
                        "vendored_package_version": "2.4.1",
                        "vendored_identity_source": "pyproject.toml",
                    } if fact_id == vendored_fact else {}),
                },
            )
        connection.execute(
            """
            INSERT INTO dependency_resolution(
              tenant_id,fact_assertion_id,package_registry_id,resolution_source,
              requested_spec,resolved_version,npm_scope,custom_registry,
              lockfile_behavior,visibility,observed_at
            ) VALUES
              (%s,%s,%s,'NPMRC_SCOPE','1.0.0','1.0.0','@acme',true,'CUSTOM_PINNED','PRIVATE',now()),
              (%s,%s,%s,'LOCKFILE','1.0.0','1.0.0',NULL,false,'CONFIGURED_DEFAULT','PUBLIC',now())
            """,
            (
                TENANT_ID,
                confusion_fact,
                PRIVATE_REGISTRY_ID,
                TENANT_ID,
                license_fact,
                PUBLIC_PYPI_REGISTRY_ID,
            ),
        )
        clone_fingerprint = "sha256:" + "a" * 64
        connection.execute(
            """
            INSERT INTO code_implementation_summary(
              tenant_id,source_snapshot_id,repository_entity_id,fact_assertion_id,
              source_revision,language,symbol_kind,qualified_name,path,line_start,line_end,
              structural_fingerprint,vendored,completeness
            ) VALUES
              (%s,%s,%s,%s,'phase-1','python','FUNCTION','shared_logic','src/shared.py',1,12,%s,false,'COMPLETE'),
              (%s,%s,%s,%s,'phase-1','python','FUNCTION','shared_logic','lib/shared.py',1,12,%s,false,'COMPLETE'),
              (%s,%s,%s,%s,'phase-1','python','FUNCTION','legacy_logic','vendor/legacy.py',1,20,%s,true,'COMPLETE')
            """,
            (
                TENANT_ID,
                SNAPSHOT_ID,
                REPOSITORY_ID,
                clone_fact_left,
                clone_fingerprint,
                TENANT_ID,
                SNAPSHOT_ID,
                SECOND_REPOSITORY_ID,
                clone_fact_right,
                clone_fingerprint,
                TENANT_ID,
                SNAPSHOT_ID,
                REPOSITORY_ID,
                vendored_fact,
                "sha256:" + "b" * 64,
            ),
        )


async def _read_expanded_rules(database_url: str):
    database = Database(Settings(environment="test", database_url=database_url))
    await database.open()
    try:
        return {
            key: await list_deterministic_insights(
                database,
                tenant_id=UUID(TENANT_ID),
                rule_key=key,
                limit=20,
            )
            for key in (
                "supplychain.dependency-confusion",
                "oss.license-obligation",
                "code.cross-repository-clone",
                "code.vendored-third-party",
            )
        }
    finally:
        await database.close()


def test_expanded_rules_query_seeded_database_with_evidence() -> None:
    database_url = os.environ["STACKGRAPH_TEST_DATABASE_URL"]
    admin_database_url = os.getenv("STACKGRAPH_TEST_ADMIN_DATABASE_URL", database_url)
    _install_expanded_rule_fixture(admin_database_url)
    try:
        results = asyncio.run(_read_expanded_rules(database_url))

        assert results["supplychain.dependency-confusion"].summary.total == 1
        license_insight = results["oss.license-obligation"].insights[0]
        assert license_insight.kind == "LICENSE_OBLIGATION"
        assert "PYPI dependency" in license_insight.summary
        assert any("No active license allow-list" in value for value in license_insight.missing_inputs)
        clone_insight = results["code.cross-repository-clone"].insights[0]
        assert clone_insight.affected_repository_count == 2
        assert {item.id for item in clone_insight.affected_repositories} == {
            UUID(REPOSITORY_ID),
            UUID(SECOND_REPOSITORY_ID),
        }
        vendored_insight = results["code.vendored-third-party"].insights[0]
        assert vendored_insight.kind == "VENDORED_SOURCE_OUTSIDE_MANAGEMENT"
        assert "pkg:pypi/legacy@2.4.1" in vendored_insight.title
        assert "no matching current DEPENDS_ON" in vendored_insight.summary
        assert vendored_insight.supporting_fact_ids
    finally:
        remove_golden_billing(admin_database_url)
