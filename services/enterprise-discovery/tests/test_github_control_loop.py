from __future__ import annotations

import os
import base64
import hashlib
import unittest
from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from uuid import uuid4

try:
    import psycopg
    from psycopg.rows import dict_row
    from psycopg.types.json import Jsonb

    from stackgraph_discovery.github_client import GitHubApiError, GitHubTransportError
    from stackgraph_discovery.github_client import ApiResult
    from stackgraph_discovery.github_control_loop import (
        MAX_ATTEMPTS,
        _acquire_scan_publish,
        _policy_int,
        _quota_status,
        _record_github_quota,
        _retry_delay,
        claim_run,
        fail_exhausted_leases,
        reconcile_rescan_jobs,
        schedule_due_targets,
    )
    from stackgraph_discovery.github_installation import (
        InstallationRepository,
        InstallationRepositorySnapshot,
    )
    from stackgraph_discovery.github_installation_store import (
        reconcile_installation,
        register_installation,
    )
except ImportError:
    psycopg = None


DATABASE_URL = os.environ.get("STACKGRAPH_TEST_DATABASE_URL")


@unittest.skipUnless(psycopg, "PostgreSQL runtime dependency is unavailable")
class GitHubControlLoopUnitTests(unittest.TestCase):
    def test_retry_policy_honors_provider_and_exponential_delays(self) -> None:
        self.assertEqual(_retry_delay(GitHubTransportError("network"), 3), 8)
        self.assertEqual(
            _retry_delay(
                GitHubApiError(
                    "limited", status_code=429, retriable=True,
                    retry_after_seconds=42,
                ),
                1,
            ),
            42,
        )
        reset = int(datetime.now(UTC).timestamp()) + 30
        delay = _retry_delay(
            GitHubApiError(
                "limited", status_code=403, retriable=True,
                rate_limit_reset=reset,
            ),
            1,
        )
        self.assertGreaterEqual(delay, 28)
        self.assertLessEqual(delay, 30)

    def test_policy_limits_reject_boolean_and_non_positive_values(self) -> None:
        self.assertEqual(_policy_int({}, "limit", 10), 10)
        for value in (True, 0, -1, "10"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                _policy_int({"limit": value}, "limit", 10)

    def test_quota_status_distinguishes_ok_throttled_and_exhausted(self) -> None:
        self.assertEqual(_quota_status(42), "OK")
        self.assertEqual(_quota_status(None, throttled=True), "THROTTLED")
        self.assertEqual(_quota_status(0), "EXHAUSTED")


@unittest.skipUnless(
    psycopg and DATABASE_URL,
    "PostgreSQL integration dependencies are unavailable",
)
class GitHubControlLoopPersistenceTests(unittest.TestCase):
    def test_github_quota_observation_is_tenant_scoped_and_refreshes(self) -> None:
        tenant_key = f"github-quota-{uuid4()}"
        with psycopg.connect(DATABASE_URL, row_factory=dict_row) as connection:
            tenant = connection.execute(
                "INSERT INTO tenant(tenant_key,name) VALUES (%s,'GitHub quota') RETURNING id",
                (tenant_key,),
            ).fetchone()
        reset_epoch = int(datetime.now(UTC).timestamp()) + 3600
        _record_github_quota(
            DATABASE_URL, tenant_id=tenant["id"], remaining=4875,
            limit=5000, reset_epoch=reset_epoch,
        )
        with psycopg.connect(DATABASE_URL, row_factory=dict_row) as connection:
            quota = connection.execute(
                "SELECT * FROM connector_quota WHERE tenant_id=%s AND provider='GITHUB_APP'",
                (tenant["id"],),
            ).fetchone()
        self.assertEqual(quota["used"], 125)
        self.assertEqual(quota["limit_value"], 5000)
        self.assertEqual(quota["status"], "OK")
        self.assertIsNotNone(quota["resets_at"])

    def test_rescan_jobs_roll_up_shared_run_success_and_failure(self) -> None:
        tenant_key = f"github-rescan-rollup-{uuid4()}"
        with psycopg.connect(DATABASE_URL, row_factory=dict_row) as connection:
            tenant = connection.execute(
                "INSERT INTO tenant(tenant_key,name) VALUES (%s,'Rescan rollup') RETURNING id",
                (tenant_key,),
            ).fetchone()
            source = connection.execute(
                """
                INSERT INTO source_system(tenant_id,source_key,kind,base_uri)
                VALUES (%s,'github-app','GITHUB','https://api.github.com') RETURNING id
                """,
                (tenant["id"],),
            ).fetchone()
            account = connection.execute(
                """
                INSERT INTO connector_account(
                  tenant_id,source_system_id,external_account_key,
                  credential_reference,permissions
                ) VALUES (%s,%s,%s,'env://GITHUB_TOKEN',%s) RETURNING id
                """,
                (
                    tenant["id"], source["id"], f"github:repository:{uuid4()}",
                    Jsonb(["contents:read", "metadata:read"]),
                ),
            ).fetchone()
            target = connection.execute(
                """
                INSERT INTO ingest_target(
                  tenant_id,source_system_id,connector_account_id,target_kind,
                  target_key,refresh_policy,next_due_at
                ) VALUES (%s,%s,%s,'REPOSITORY',%s,%s,NULL) RETURNING id
                """,
                (
                    tenant["id"], source["id"], account["id"],
                    f"github:repo:{uuid4()}",
                    Jsonb({"full_name": "acme/rescan", "schedule_enabled": False}),
                ),
            ).fetchone()
            jobs = connection.execute(
                """
                INSERT INTO rescan_job(
                  tenant_id,idempotency_key,reason,requested_by
                ) VALUES
                  (%s,%s,'shared run one','tester'),
                  (%s,%s,'shared run two','tester')
                RETURNING id
                """,
                (tenant["id"], f"rescan-{uuid4()}", tenant["id"], f"rescan-{uuid4()}"),
            ).fetchall()
            run = connection.execute(
                """
                INSERT INTO ingest_run(
                  tenant_id,ingest_target_id,trigger_kind,stats
                ) VALUES (%s,%s,'MANUAL',%s) RETURNING id
                """,
                (
                    tenant["id"], target["id"],
                    Jsonb({"rescan_job_ids": [str(job["id"]) for job in jobs]}),
                ),
            ).fetchone()

        self.assertEqual(
            reconcile_rescan_jobs(DATABASE_URL, tenant_id=tenant["id"]), 0,
        )
        claimed = claim_run(
            DATABASE_URL, worker_id="rescan-rollup-test", lease_seconds=300,
            tenant_id=tenant["id"],
        )
        self.assertIsNotNone(claimed)
        self.assertEqual(
            reconcile_rescan_jobs(DATABASE_URL, tenant_id=tenant["id"]), 2,
        )
        with psycopg.connect(DATABASE_URL, row_factory=dict_row) as connection:
            running = connection.execute(
                "SELECT status,started_at FROM rescan_job WHERE id=ANY(%s::uuid[])",
                ([job["id"] for job in jobs],),
            ).fetchall()
            self.assertTrue(all(row["status"] == "RUNNING" for row in running))
            self.assertTrue(all(row["started_at"] is not None for row in running))
            connection.execute(
                """
                UPDATE ingest_run SET status='SUCCEEDED',completed_at=now(),
                  lease_owner=NULL,lease_expires_at=NULL WHERE id=%s
                """,
                (run["id"],),
            )

        self.assertEqual(
            reconcile_rescan_jobs(DATABASE_URL, tenant_id=tenant["id"]), 2,
        )
        with psycopg.connect(DATABASE_URL, row_factory=dict_row) as connection:
            completed = connection.execute(
                "SELECT status,completed_at FROM rescan_job WHERE id=ANY(%s::uuid[])",
                ([job["id"] for job in jobs],),
            ).fetchall()
            self.assertTrue(all(row["status"] == "SUCCEEDED" for row in completed))
            self.assertTrue(all(row["completed_at"] is not None for row in completed))
            failed_job = connection.execute(
                """
                INSERT INTO rescan_job(
                  tenant_id,idempotency_key,reason,requested_by
                ) VALUES (%s,%s,'failed run','tester') RETURNING id
                """,
                (tenant["id"], f"rescan-{uuid4()}"),
            ).fetchone()
            connection.execute(
                """
                INSERT INTO ingest_run(
                  tenant_id,ingest_target_id,trigger_kind,status,stats,error_class,
                  error_detail,started_at,completed_at
                ) VALUES (%s,%s,'MANUAL','FAILED',%s,'TestFailure',%s,now(),now())
                """,
                (
                    tenant["id"], target["id"],
                    Jsonb({"rescan_job_ids": [str(failed_job["id"])]}),
                    Jsonb({"message": "repository scan failed"}),
                ),
            )

        self.assertEqual(
            reconcile_rescan_jobs(DATABASE_URL, tenant_id=tenant["id"]), 1,
        )
        with psycopg.connect(DATABASE_URL, row_factory=dict_row) as connection:
            failed = connection.execute(
                "SELECT status,last_error,completed_at FROM rescan_job WHERE id=%s",
                (failed_job["id"],),
            ).fetchone()
            self.assertEqual(failed["status"], "FAILED")
            self.assertEqual(failed["last_error"], "repository scan failed")
            self.assertIsNotNone(failed["completed_at"])
            connection.execute(
                "UPDATE ingest_target SET enabled=false,next_due_at=NULL WHERE id=%s",
                (target["id"],),
            )

    def test_due_target_is_scheduled_once_and_expired_lease_dead_letters(self) -> None:
        tenant_key = f"github-control-{uuid4()}"
        registration = None
        with psycopg.connect(DATABASE_URL) as connection:
            connection.execute(
                "INSERT INTO tenant(tenant_key,name) VALUES (%s,'GitHub control loop')",
                (tenant_key,),
            )
        registration = register_installation(
            DATABASE_URL,
            tenant_key=tenant_key,
            installation_id=str(uuid4().int)[:12],
            credential_reference="env://GITHUB_INSTALLATION_TOKEN",
            permissions=["contents:read", "metadata:read"],
        )

        tenant_id = registration.tenant_id
        self.assertEqual(schedule_due_targets(DATABASE_URL, tenant_id=tenant_id), 1)
        self.assertEqual(schedule_due_targets(DATABASE_URL, tenant_id=tenant_id), 0)
        claimed = claim_run(
            DATABASE_URL, worker_id="control-loop-test", lease_seconds=30,
            tenant_id=tenant_id,
        )
        self.assertIsNotNone(claimed)
        assert claimed is not None
        self.assertEqual(str(claimed.target_id), registration.installation_target_id)
        self.assertEqual(claimed.target_kind, "GITHUB_INSTALLATION")

        with psycopg.connect(DATABASE_URL) as connection:
            connection.execute(
                """
                UPDATE ingest_run SET attempt=%s,lease_expires_at=now()-interval '1 second'
                WHERE id=%s
                """,
                (MAX_ATTEMPTS, claimed.run_id),
            )
        self.assertEqual(fail_exhausted_leases(DATABASE_URL), 1)
        self.assertEqual(fail_exhausted_leases(DATABASE_URL), 0)
        with psycopg.connect(DATABASE_URL, row_factory=dict_row) as connection:
            run = connection.execute(
                "SELECT status,error_class FROM ingest_run WHERE id=%s",
                (claimed.run_id,),
            ).fetchone()
            dead_letters = connection.execute(
                """
                SELECT count(*) count FROM dead_letter
                WHERE source_kind='INGEST_RUN' AND source_id=%s
                """,
                (str(claimed.run_id),),
            ).fetchone()
        self.assertEqual(run["status"], "FAILED")
        self.assertEqual(run["error_class"], "LEASE_EXHAUSTED")
        self.assertEqual(dead_letters["count"], 1)
        with psycopg.connect(DATABASE_URL) as connection:
            connection.execute(
                "UPDATE ingest_target SET enabled=false,next_due_at=NULL WHERE tenant_id=%s",
                (claimed.tenant_id,),
            )

    def test_changed_repository_publishes_once_and_unchanged_revision_skips_scan(self) -> None:
        tenant_key = f"github-pipeline-{uuid4()}"
        installation_id = str(uuid4().int)[:12]
        repository_id = str(uuid4().int)[:12]
        with psycopg.connect(DATABASE_URL) as connection:
            connection.execute(
                "INSERT INTO tenant(tenant_key,name) VALUES (%s,'GitHub pipeline')",
                (tenant_key,),
            )
        registration = register_installation(
            DATABASE_URL,
            tenant_key=tenant_key,
            installation_id=installation_id,
            credential_reference="env://GITHUB_INSTALLATION_TOKEN",
            permissions=["contents:read", "metadata:read"],
        )
        reconcile_installation(
            DATABASE_URL,
            tenant_key=tenant_key,
            snapshot=InstallationRepositorySnapshot(
                installation_id=installation_id,
                repositories=(InstallationRepository(
                    repository_id=repository_id, owner="acme", name="billing",
                    full_name="acme/billing", default_branch="main",
                    visibility="PRIVATE", archived=False, disabled=False,
                ),),
                page_count=1, observed_total=1, response_etag='"v1"',
            ),
        )
        with psycopg.connect(DATABASE_URL) as connection:
            connection.execute(
                """
                UPDATE ingest_target SET enabled=false,next_due_at=NULL
                WHERE id=%s
                """,
                (registration.installation_target_id,),
            )
        tenant_id = registration.tenant_id
        self.assertEqual(schedule_due_targets(DATABASE_URL, tenant_id=tenant_id), 1)
        claimed = claim_run(
            DATABASE_URL, worker_id="pipeline-test", lease_seconds=300,
            tenant_id=tenant_id,
        )
        self.assertIsNotNone(claimed)
        assert claimed is not None
        fake_client = _RepositoryClient(repository_id)
        with TemporaryDirectory() as snapshots, TemporaryDirectory() as evidence:
            with patch(
                "stackgraph_discovery.github_control_loop._client",
                return_value=fake_client,
            ), patch.dict(os.environ, {"GITHUB_INSTALLATION_TOKEN": "ghs_runtime"}):
                first = _acquire_scan_publish(
                    DATABASE_URL, claimed,
                    snapshot_root=Path(snapshots), evidence_root=Path(evidence),
                )
                self.assertEqual(first.status, "PUBLISHED")

                with psycopg.connect(DATABASE_URL) as connection:
                    connection.execute(
                        "UPDATE ingest_target SET next_due_at=now() WHERE id=%s",
                        (claimed.target_id,),
                    )
                self.assertEqual(
                    schedule_due_targets(DATABASE_URL, tenant_id=tenant_id), 1,
                )
                replay_claim = claim_run(
                    DATABASE_URL, worker_id="pipeline-test", lease_seconds=300,
                    tenant_id=tenant_id,
                )
                self.assertIsNotNone(replay_claim)
                assert replay_claim is not None
                replay = _acquire_scan_publish(
                    DATABASE_URL, replay_claim,
                    snapshot_root=Path(snapshots), evidence_root=Path(evidence),
                )
                self.assertEqual(replay.status, "UNCHANGED")

                # Simulate two workers acquiring before either publication was
                # visible. Scanner persistence must replay the immutable snapshot
                # and still close the second durable run.
                with psycopg.connect(DATABASE_URL) as connection:
                    connection.execute(
                        "UPDATE ingest_target SET next_due_at=now() WHERE id=%s",
                        (claimed.target_id,),
                    )
                self.assertEqual(
                    schedule_due_targets(DATABASE_URL, tenant_id=tenant_id), 1,
                )
                race_claim = claim_run(
                    DATABASE_URL, worker_id="pipeline-race-test", lease_seconds=300,
                    tenant_id=tenant_id,
                )
                self.assertIsNotNone(race_claim)
                assert race_claim is not None
                with patch(
                    "stackgraph_discovery.github_control_loop._previous_revision",
                    return_value=None,
                ):
                    race = _acquire_scan_publish(
                        DATABASE_URL, race_claim,
                        snapshot_root=Path(snapshots), evidence_root=Path(evidence),
                    )
                self.assertEqual(race.status, "REPLAYED")

        with psycopg.connect(DATABASE_URL, row_factory=dict_row) as connection:
            counts = connection.execute(
                """
                SELECT
                  (SELECT count(*) FROM source_snapshot WHERE ingest_target_id=%s) snapshots,
                  (SELECT count(*) FROM projection_outbox WHERE tenant_id=%s) projection,
                  (SELECT count(*) FROM intelligence_job WHERE tenant_id=%s) intelligence,
                  (SELECT count(*) FROM ingest_run WHERE ingest_target_id=%s
                    AND status='SUCCEEDED') succeeded_runs
                """,
                (claimed.target_id, claimed.tenant_id, claimed.tenant_id, claimed.target_id),
            ).fetchone()
            connection.execute(
                "UPDATE ingest_target SET enabled=false,next_due_at=NULL WHERE tenant_id=%s",
                (claimed.tenant_id,),
            )
        self.assertEqual(counts["snapshots"], 1)
        self.assertGreater(counts["projection"], 0)
        self.assertEqual(counts["intelligence"], 1)
        self.assertEqual(counts["succeeded_runs"], 3)

    def test_direct_repository_target_resolves_and_promotes_github_identity(self) -> None:
        tenant_key = f"github-direct-{uuid4()}"
        repository_id = str(uuid4().int)[:12]
        with psycopg.connect(DATABASE_URL, row_factory=dict_row) as connection:
            tenant = connection.execute(
                "INSERT INTO tenant(tenant_key,name) VALUES (%s,'GitHub direct') RETURNING id",
                (tenant_key,),
            ).fetchone()
            source = connection.execute(
                """
                INSERT INTO source_system(tenant_id,source_key,kind,base_uri)
                VALUES (%s,'github-app','GITHUB','https://api.github.com') RETURNING id
                """,
                (tenant["id"],),
            ).fetchone()
            account = connection.execute(
                """
                INSERT INTO connector_account(
                  tenant_id,source_system_id,external_account_key,credential_reference,permissions
                ) VALUES (%s,%s,'github:repository:acme/billing','env://GITHUB_TOKEN',%s)
                RETURNING id
                """,
                (tenant["id"], source["id"], Jsonb(["contents:read", "metadata:read"])),
            ).fetchone()
            target = connection.execute(
                """
                INSERT INTO ingest_target(
                  tenant_id,source_system_id,connector_account_id,target_kind,target_key,
                  priority,refresh_policy,next_due_at
                ) VALUES (%s,%s,%s,'REPOSITORY','github:repo-name:acme/billing','HOT',%s,now())
                RETURNING id
                """,
                (
                    tenant["id"], source["id"], account["id"],
                    Jsonb({
                        "provider": "github", "direct_repository": True,
                        "owner": "acme", "name": "billing", "full_name": "acme/billing",
                        "cadence_seconds": 86400, "schedule_enabled": True,
                    }),
                ),
            ).fetchone()
            connection.execute(
                """
                INSERT INTO ingest_run(tenant_id,ingest_target_id,trigger_kind)
                VALUES (%s,%s,'MANUAL')
                """,
                (tenant["id"], target["id"]),
            )

        claimed = claim_run(
            DATABASE_URL, worker_id="direct-repository-test", lease_seconds=300,
            tenant_id=tenant["id"],
        )
        self.assertIsNotNone(claimed)
        assert claimed is not None
        with TemporaryDirectory() as snapshots, TemporaryDirectory() as evidence:
            with patch(
                "stackgraph_discovery.github_control_loop._client",
                return_value=_RepositoryClient(repository_id),
            ), patch.dict(os.environ, {"GITHUB_TOKEN": "github-token-runtime"}):
                result = _acquire_scan_publish(
                    DATABASE_URL, claimed,
                    snapshot_root=Path(snapshots), evidence_root=Path(evidence),
                )
        self.assertEqual(result.status, "PUBLISHED")
        with psycopg.connect(DATABASE_URL, row_factory=dict_row) as connection:
            promoted = connection.execute(
                "SELECT target_key,refresh_policy,last_success_at FROM ingest_target WHERE id=%s",
                (target["id"],),
            ).fetchone()
            connection.execute(
                "UPDATE ingest_target SET enabled=false,next_due_at=NULL WHERE id=%s",
                (target["id"],),
            )
        self.assertEqual(promoted["target_key"], f"github:repo:{repository_id}")
        self.assertEqual(promoted["refresh_policy"]["repository_id"], repository_id)
        self.assertEqual(promoted["refresh_policy"]["default_branch"], "main")
        self.assertIsNotNone(promoted["last_success_at"])


class _RepositoryClient:
    api_version = "2026-03-10"
    base_url = "https://api.github.test"

    def __init__(self, repository_id: str) -> None:
        self.repository_id = repository_id
        self.revision = "a" * 40
        self.tree = "b" * 40
        self.package_content = b'{"name":"billing","dependencies":{"lodash":"4.17.21"}}'
        self.source_content = b"const lodash = require('lodash');\nconsole.log(lodash);\n"
        self.package_blob = _git_blob_sha(self.package_content)
        self.source_blob = _git_blob_sha(self.source_content)

    def get_json(self, path: str, **_: object) -> ApiResult:
        documents = {
            "/repos/acme/billing": {
                "id": int(self.repository_id), "node_id": "R_pipeline",
                "full_name": "acme/billing", "default_branch": "main",
                "visibility": "private", "archived": False,
            },
            "/repos/acme/billing/commits/main": {
                "sha": self.revision,
                "commit": {
                    "tree": {"sha": self.tree},
                    "committer": {"date": "2026-08-19T12:00:00Z"},
                },
            },
            f"/repos/acme/billing/git/trees/{self.tree}": {
                "truncated": False,
                "tree": [
                    {"path": "package.json", "type": "blob", "sha": self.package_blob, "size": len(self.package_content)},
                    {"path": "index.js", "type": "blob", "sha": self.source_blob, "size": len(self.source_content)},
                ],
            },
            f"/repos/acme/billing/git/blobs/{self.package_blob}": _blob(self.package_content),
            f"/repos/acme/billing/git/blobs/{self.source_blob}": _blob(self.source_content),
        }
        if path not in documents:
            raise AssertionError(f"unexpected GitHub path: {path}")
        return ApiResult(
            status=200,
            headers={"etag": '"pipeline"', "x-ratelimit-remaining": "4999"},
            data=documents[path],
        )


def _blob(content: bytes) -> dict[str, object]:
    return {
        "sha": _git_blob_sha(content),
        "encoding": "base64",
        "content": base64.b64encode(content).decode(),
        "size": len(content),
    }


def _git_blob_sha(content: bytes) -> str:
    return hashlib.sha1(f"blob {len(content)}\0".encode() + content).hexdigest()


if __name__ == "__main__":
    unittest.main()
