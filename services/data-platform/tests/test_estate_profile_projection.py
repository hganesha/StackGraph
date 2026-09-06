"""Tests for projecting scanner records into the typed estate profile tables.

The scanner has emitted `component_profile` and `deployment_profile` records since 1.11.0, and
the API has read `estate_component_profile` / `estate_deployment_profile` since E1, but nothing
joined the two. Every component profile therefore reported COMPONENT_EVIDENCE_PARTIAL however
complete the scan was, and deployment reads fell back to untyped entities with no provider,
workload kind, or confidence. These tests hold the projection that closes that.

They use a recording connection rather than a database because what matters here is which rows
are derived from which records; the constraints themselves are covered by the migration and the
database integration suite.
"""

from __future__ import annotations

import unittest
from uuid import UUID, uuid4

from stackgraph_data.scanner_ingest import (
    _persist_component_profile,
    _persist_deployment_profiles,
)


TENANT_ID = UUID("00000000-0000-4000-8000-0000000d0001")
COMPONENT_ID = UUID("00000000-0000-4000-8000-0000000d0002")
REPOSITORY_ID = UUID("00000000-0000-4000-8000-0000000d0003")
FACT_ID = UUID("00000000-0000-4000-8000-0000000d0004")
DEPLOYMENT_ID = UUID("00000000-0000-4000-8000-0000000d0005")
PROFILE_ID = UUID("00000000-0000-4000-8000-0000000d00f0")
OBSERVED_AT = "2026-08-19T14:00:00Z"
REVISION = "a" * 40


class Result:
    def __init__(self, row):
        self.row = row

    def fetchone(self):
        return self.row


class RecordingConnection:
    def __init__(self):
        self.statements: list[tuple[str, tuple]] = []

    def execute(self, query, params=()):
        self.statements.append((query, params))
        return Result({"id": PROFILE_ID} if "RETURNING id" in query else None)

    def find(self, fragment):
        return [
            (query, params) for query, params in self.statements if fragment in query
        ]

    def one(self, fragment):
        matches = self.find(fragment)
        assert len(matches) == 1, f"expected exactly one {fragment}, got {len(matches)}"
        return matches[0][1]


COMPONENT_RECORD = {
    "record_kind": "component_profile",
    "schema_version": "1.0.0",
    "path": "apps/payment-api",
    "component_kind": "SERVICE",
    "independently_deployable": True,
    "languages": ["JavaScript"],
    "frameworks": ["express"],
    "ecosystems": ["npm"],
    "build_systems": ["DOCKER", "NPM"],
    "runtime": ["NODE"],
    "entry_points": ["src/server.js"],
    "tests": [],
    "dependency_count": 2,
    "limitations": ["component identity is path-stable within a repository"],
    "rule_version": "component-decomposition/1.0.0",
}

DEPLOYMENT_AGGREGATE = {
    "record_kind": "deployment_profile",
    "schema_version": "1.0.0",
    "providers": [],
    "workload_types": ["COMPOSE_SERVICE", "CONTAINER_BUILD"],
    "environments": ["local-compose"],
    "verification_level": "DECLARED_CONFIGURATION",
    "coverage": {
        "live_state": "NOT_VERIFIED",
        "registry_metadata": "NOT_COLLECTED",
        "configuration": "AVAILABLE",
    },
    "limitations": ["deployment configuration does not prove that a workload is deployed"],
    "rule_version": "deployment-profile/1.1.0",
}


def deployment(properties, *, entity_id=DEPLOYMENT_ID):
    return {
        "entity_id": entity_id, "fact_id": FACT_ID, "confidence": 0.9,
        "observed_at": OBSERVED_AT, "properties": properties,
    }


class ComponentProfileProjectionTests(unittest.TestCase):
    def project(self, record=None, *, repository_id=REPOSITORY_ID):
        connection = RecordingConnection()
        _persist_component_profile(
            connection, tenant_id=TENANT_ID, component_id=COMPONENT_ID,
            repository_id=repository_id, fact_id=FACT_ID, source_revision=REVISION,
            observed_at=OBSERVED_AT, confidence=0.98, value=record or COMPONENT_RECORD,
        )
        return connection

    def test_a_component_record_becomes_a_typed_profile_row(self) -> None:
        params = self.project().one("INSERT INTO estate_component_profile")
        tenant, component, repository, path, classifications, deployable = params[:6]
        self.assertEqual(TENANT_ID, tenant)
        self.assertEqual(COMPONENT_ID, component)
        self.assertEqual(REPOSITORY_ID, repository)
        self.assertEqual("apps/payment-api", path)
        self.assertEqual(["DOCKER", "NPM", "SERVICE"], classifications)
        self.assertTrue(deployable)

    def test_derived_detail_stays_in_attributes_rather_than_being_flattened(self) -> None:
        attributes = self.project().one("INSERT INTO estate_component_profile")[6].obj
        self.assertEqual(["express"], attributes["frameworks"])
        self.assertEqual(["NODE"], attributes["runtime"])
        self.assertEqual(2, attributes["dependency_count"])
        # Limitations travel with the profile so a reader sees them next to the claim.
        self.assertIn("component identity is path-stable within a repository", attributes["limitations"])

    def test_the_rule_version_is_carried_as_the_method_version(self) -> None:
        params = self.project().one("INSERT INTO estate_component_profile")
        self.assertEqual("component-decomposition/1.0.0", params[8])
        self.assertEqual(REVISION, params[9])

    def test_an_unknown_independent_deployability_stays_unknown(self) -> None:
        record = dict(COMPONENT_RECORD)
        del record["independently_deployable"]
        # Not False. A component whose deployability was never determined must not be recorded
        # as one that is known not to be independently deployable.
        self.assertIsNone(self.project(record).one("INSERT INTO estate_component_profile")[5])

    def test_a_record_without_a_path_is_refused(self) -> None:
        record = dict(COMPONENT_RECORD, path="")
        with self.assertRaises(ValueError):
            self.project(record)

    def test_an_older_revision_is_superseded_rather_than_accumulated(self) -> None:
        connection = self.project()
        params = connection.one("UPDATE estate_component_profile SET valid_to=now()")
        self.assertEqual((TENANT_ID, COMPONENT_ID, PROFILE_ID), params)

    def test_the_originating_fact_is_recorded_as_evidence(self) -> None:
        params = self.project().one("INSERT INTO estate_profile_evidence")
        self.assertEqual((TENANT_ID, PROFILE_ID, FACT_ID), params)

    def test_a_component_without_a_resolved_repository_still_projects(self) -> None:
        params = self.project(repository_id=None).one("INSERT INTO estate_component_profile")
        self.assertIsNone(params[2])


class DeploymentProfileProjectionTests(unittest.TestCase):
    def project(self, deployments, aggregate=DEPLOYMENT_AGGREGATE):
        connection = RecordingConnection()
        _persist_deployment_profiles(
            connection, tenant_id=TENANT_ID, repository_id=REPOSITORY_ID,
            source_revision=REVISION, deployments=deployments, aggregate=aggregate,
        )
        return connection

    def test_compose_workloads_name_their_platform_from_their_own_source(self) -> None:
        params = self.project([
            deployment({"source_kind": "COMPOSE", "service": "shipping"}),
        ]).one("INSERT INTO estate_deployment_profile")
        self.assertEqual("DOCKER_COMPOSE", params[3])
        self.assertEqual("COMPOSE_SERVICE", params[4])
        self.assertEqual("local-compose", params[5])

    def test_a_dockerfile_stage_is_a_container_build_not_a_cloud_deployment(self) -> None:
        params = self.project([
            deployment({"source_kind": "DOCKERFILE", "stage": 1}),
        ]).one("INSERT INTO estate_deployment_profile")
        self.assertEqual("CONTAINER_BUILD", params[3])
        self.assertEqual("CONTAINER_BUILD", params[4])

    def test_a_kubernetes_workload_carries_its_kind_and_namespace(self) -> None:
        params = self.project([
            deployment({"source_kind": "KUBERNETES", "kind": "Deployment", "namespace": "payments"}),
        ]).one("INSERT INTO estate_deployment_profile")
        self.assertEqual("KUBERNETES", params[3])
        self.assertEqual("KUBERNETES_DEPLOYMENT", params[4])
        self.assertEqual("payments", params[5])

    def test_terraform_takes_the_provider_the_repository_profile_resolved(self) -> None:
        aggregate = dict(DEPLOYMENT_AGGREGATE, providers=["AWS"], environments=[])
        params = self.project(
            [deployment({"source_kind": "TERRAFORM", "resource_type": "aws_db_instance"})],
            aggregate,
        ).one("INSERT INTO estate_deployment_profile")
        self.assertEqual("AWS", params[3])
        self.assertEqual("TERRAFORM_RESOURCE", params[4])

    def test_an_ambiguous_provider_names_the_source_rather_than_guessing_a_cloud(self) -> None:
        aggregate = dict(DEPLOYMENT_AGGREGATE, providers=["AWS", "GCP"], environments=[])
        params = self.project(
            [deployment({"source_kind": "TERRAFORM", "resource_type": "aws_db_instance"})],
            aggregate,
        ).one("INSERT INTO estate_deployment_profile")
        # Two providers in one repository does not make either one this workload's provider.
        self.assertEqual("TERRAFORM", params[3])

    def test_declared_configuration_is_never_recorded_as_a_verified_deployment(self) -> None:
        params = self.project([
            deployment({"source_kind": "COMPOSE", "service": "shipping"}),
        ]).one("INSERT INTO estate_deployment_profile")
        resources = params[6].obj
        self.assertEqual("DECLARED_CONFIGURATION", resources[0]["verification_level"])
        self.assertEqual("NOT_VERIFIED", resources[0]["coverage"]["live_state"])
        limitations = params[8].obj
        self.assertIn(
            "deployment configuration does not prove that a workload is deployed", limitations,
        )

    def test_every_observed_workload_gets_its_own_row(self) -> None:
        connection = self.project([
            deployment({"source_kind": "COMPOSE", "service": "shipping"}, entity_id=uuid4()),
            deployment({"source_kind": "COMPOSE", "service": "database"}, entity_id=uuid4()),
            deployment({"source_kind": "DOCKERFILE", "stage": 1}, entity_id=uuid4()),
        ])
        self.assertEqual(3, len(connection.find("INSERT INTO estate_deployment_profile")))
        self.assertEqual(3, len(connection.find("INSERT INTO estate_profile_evidence")))

    def test_nothing_is_written_when_no_workload_was_observed(self) -> None:
        self.assertEqual([], self.project([]).statements)

    def test_a_repository_with_workloads_but_no_aggregate_record_still_projects(self) -> None:
        params = self.project(
            [deployment({"source_kind": "COMPOSE", "service": "shipping"})], None,
        ).one("INSERT INTO estate_deployment_profile")
        self.assertEqual("DOCKER_COMPOSE", params[3])
        self.assertEqual([], params[8].obj)


if __name__ == "__main__":
    unittest.main()
