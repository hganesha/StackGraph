from __future__ import annotations

import os
import hashlib
import hmac
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4

try:
    import psycopg
    from psycopg.rows import dict_row

    from stackgraph_discovery.github_installation import (
        InstallationRepository,
        InstallationRepositorySnapshot,
    )
    from stackgraph_discovery.github_installation_store import (
        reconcile_installation_connection,
        register_installation_connection,
        resolve_environment_credential,
        revoke_installation_connection,
        validate_credential_reference,
        validate_permissions,
    )
    from stackgraph_discovery.evidence_store import LocalEvidenceStore
    from stackgraph_discovery.github_webhook import verify_github_webhook
    from stackgraph_discovery.github_webhook_store import process_github_webhook_connection
except ImportError:
    psycopg = None


DATABASE_URL = os.environ.get("STACKGRAPH_TEST_DATABASE_URL")


def repository(repository_id: str, name: str) -> InstallationRepository:
    return InstallationRepository(
        repository_id=repository_id,
        owner="acme",
        name=name,
        full_name=f"acme/{name}",
        default_branch="main",
        visibility="PRIVATE",
        archived=False,
        disabled=False,
    )


def snapshot(*repositories: InstallationRepository) -> InstallationRepositorySnapshot:
    return InstallationRepositorySnapshot(
        installation_id="9876",
        repositories=tuple(repositories),
        page_count=1,
        observed_total=len(repositories),
        response_etag='"installation-v1"',
    )


def verified_webhook(
    payload: dict,
    *,
    delivery_id: str,
    event: str,
) -> object:
    body = json.dumps(payload, sort_keys=True).encode()
    secret = "integration-webhook-secret"
    signature = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return verify_github_webhook(
        {
            "X-Hub-Signature-256": f"sha256={signature}",
            "X-GitHub-Delivery": delivery_id,
            "X-GitHub-Event": event,
            "Content-Type": "application/json",
        },
        body,
        secret=secret,
    )


@unittest.skipUnless(psycopg, "PostgreSQL runtime dependency is unavailable")
class GitHubCredentialBoundaryTests(unittest.TestCase):
    def test_accepts_references_but_never_raw_tokens(self) -> None:
        validate_credential_reference("vault://stackgraph/github/installations/9876")
        self.assertEqual(
            resolve_environment_credential(
                "env://GITHUB_INSTALLATION_TOKEN_9876",
                {"GITHUB_INSTALLATION_TOKEN_9876": "ghs_short_lived"},
            ),
            "ghs_short_lived",
        )
        with self.assertRaisesRegex(ValueError, "secret-provider URI"):
            validate_credential_reference("ghs_raw_token")
        with self.assertRaisesRegex(ValueError, "only env"):
            resolve_environment_credential(
                "vault://stackgraph/github/installations/9876", {}
            )
        with self.assertRaisesRegex(ValueError, "missing"):
            validate_permissions(["contents:read"])


@unittest.skipUnless(psycopg and DATABASE_URL, "PostgreSQL integration dependencies are unavailable")
class GitHubInstallationPersistenceTests(unittest.TestCase):
    def test_registration_reconciliation_removal_and_revocation(self) -> None:
        tenant_key = f"github-installation-{uuid4()}"
        other_tenant_key = f"github-installation-other-{uuid4()}"
        with psycopg.connect(DATABASE_URL, row_factory=dict_row) as connection:
            tenant = connection.execute(
                "INSERT INTO tenant(tenant_key,name) VALUES (%s,'GitHub installation test') RETURNING id",
                (tenant_key,),
            ).fetchone()
            connection.execute(
                "INSERT INTO tenant(tenant_key,name) VALUES (%s,'Other tenant')",
                (other_tenant_key,),
            )
            registration = register_installation_connection(
                connection,
                tenant_key=tenant_key,
                installation_id="9876",
                credential_reference="env://GITHUB_INSTALLATION_TOKEN_9876",
                permissions=["metadata:read", "contents:read"],
            )
            replay = register_installation_connection(
                connection,
                tenant_key=tenant_key,
                installation_id="9876",
                credential_reference="env://GITHUB_INSTALLATION_TOKEN_9876",
                permissions=["contents:read", "metadata:read"],
            )
            self.assertTrue(registration.created)
            self.assertFalse(replay.created)
            with self.assertRaisesRegex(ValueError, "another tenant"):
                register_installation_connection(
                    connection,
                    tenant_key=other_tenant_key,
                    installation_id="9876",
                    credential_reference="env://OTHER_TOKEN",
                    permissions=["contents:read", "metadata:read"],
                )

            connector = connection.execute(
                """
                SELECT external_account_key,credential_reference,permissions,status
                FROM connector_account WHERE id=%s
                """,
                (registration.connector_account_id,),
            ).fetchone()
            self.assertEqual(connector["external_account_key"], "github:installation:9876")
            self.assertEqual(connector["credential_reference"], "env://GITHUB_INSTALLATION_TOKEN_9876")
            self.assertNotIn("ghs_", str(connector))
            installation_target = connection.execute(
                "SELECT target_kind,target_key,enabled FROM ingest_target WHERE id=%s",
                (registration.installation_target_id,),
            ).fetchone()
            self.assertEqual(installation_target["target_kind"], "GITHUB_INSTALLATION")
            self.assertTrue(installation_target["enabled"])

            first = reconcile_installation_connection(
                connection,
                tenant_key=tenant_key,
                snapshot=snapshot(repository("10", "billing"), repository("20", "worker")),
            )
            self.assertEqual(first.created_count, 2)
            self.assertEqual(first.removed_count, 0)
            targets = connection.execute(
                """
                SELECT id,target_key,enabled FROM ingest_target
                WHERE tenant_id=%s AND target_kind='REPOSITORY' ORDER BY target_key
                """,
                (tenant["id"],),
            ).fetchall()
            self.assertEqual(
                [row["target_key"] for row in targets],
                ["github:repo:9876/10", "github:repo:9876/20"],
            )
            run = connection.execute(
                """
                INSERT INTO ingest_run(
                  tenant_id,ingest_target_id,trigger_kind,requested_source_revision
                ) VALUES (%s,%s,'RECONCILIATION','revision-1') RETURNING id
                """,
                (tenant["id"], targets[0]["id"]),
            ).fetchone()

            second = reconcile_installation_connection(
                connection,
                tenant_key=tenant_key,
                snapshot=snapshot(repository("20", "worker"), repository("30", "web")),
            )
            self.assertEqual(second.created_count, 1)
            self.assertEqual(second.updated_count, 1)
            self.assertEqual(second.removed_count, 1)
            self.assertEqual(second.cancelled_run_count, 1)
            cancelled = connection.execute(
                "SELECT status,error_class FROM ingest_run WHERE id=%s",
                (run["id"],),
            ).fetchone()
            self.assertEqual(cancelled["status"], "CANCELLED")
            self.assertEqual(cancelled["error_class"], "INSTALLATION_REPOSITORY_REMOVED")
            cursor = connection.execute(
                """
                SELECT source_revision,cursor_value FROM ingest_cursor
                WHERE ingest_target_id=%s AND cursor_kind='GITHUB_INSTALLATION_RECONCILIATION'
                """,
                (registration.installation_target_id,),
            ).fetchone()
            self.assertEqual(cursor["source_revision"], second.source_revision)
            self.assertEqual(cursor["cursor_value"]["repository_count"], 2)

            worker_target = connection.execute(
                """
                SELECT id FROM ingest_target
                WHERE tenant_id=%s AND target_key='github:repo:9876/20'
                """,
                (tenant["id"],),
            ).fetchone()
            pending = connection.execute(
                """
                INSERT INTO ingest_run(
                  tenant_id,ingest_target_id,trigger_kind,requested_source_revision
                ) VALUES (%s,%s,'RECONCILIATION','revision-2') RETURNING id
                """,
                (tenant["id"], worker_target["id"]),
            ).fetchone()
            revoked = revoke_installation_connection(
                connection, tenant_key=tenant_key, installation_id="9876",
            )
            revoked_replay = revoke_installation_connection(
                connection, tenant_key=tenant_key, installation_id="9876",
            )
            self.assertEqual(revoked.disabled_target_count, 3)
            self.assertEqual(revoked.cancelled_run_count, 1)
            self.assertEqual(revoked_replay.disabled_target_count, 0)
            self.assertEqual(revoked_replay.cancelled_run_count, 0)
            self.assertEqual(
                connection.execute(
                    "SELECT status FROM ingest_run WHERE id=%s", (pending["id"],)
                ).fetchone()["status"],
                "CANCELLED",
            )
            self.assertEqual(
                connection.execute(
                    "SELECT status FROM connector_account WHERE id=%s",
                    (registration.connector_account_id,),
                ).fetchone()["status"],
                "REVOKED",
            )
            connection.rollback()

    def test_webhook_dedupe_push_routing_and_repository_removal(self) -> None:
        tenant_key = f"github-webhook-{uuid4()}"
        with psycopg.connect(DATABASE_URL, row_factory=dict_row) as connection:
            tenant = connection.execute(
                "INSERT INTO tenant(tenant_key,name) VALUES (%s,'GitHub webhook test') RETURNING id",
                (tenant_key,),
            ).fetchone()
            registration = register_installation_connection(
                connection,
                tenant_key=tenant_key,
                installation_id="9876",
                credential_reference="env://GITHUB_INSTALLATION_TOKEN_9876",
                permissions=["contents:read", "metadata:read"],
            )
            repository_payload = {
                "id": 10,
                "name": "billing",
                "full_name": "acme/billing",
                "owner": {"login": "acme"},
                "default_branch": "main",
                "visibility": "private",
            }
            push = verified_webhook(
                {
                    "installation": {"id": 9876},
                    "repository": repository_payload,
                    "ref": "refs/heads/main",
                    "after": "a" * 40,
                },
                delivery_id="delivery-push-1",
                event="push",
            )
            with TemporaryDirectory() as directory:
                evidence_store = LocalEvidenceStore(Path(directory))
                first = process_github_webhook_connection(
                    connection, push, evidence_store=evidence_store,
                )
                replay = process_github_webhook_connection(
                    connection, push, evidence_store=evidence_store,
                )
                self.assertEqual(first.status, "PROCESSED")
                self.assertIsNotNone(first.run_id)
                self.assertTrue(replay.replayed)
                target = connection.execute(
                    """
                    SELECT id,desired_source_revision,enabled FROM ingest_target
                    WHERE tenant_id=%s AND target_key='github:repo:9876/10'
                    """,
                    (tenant["id"],),
                ).fetchone()
                self.assertEqual(target["desired_source_revision"], "a" * 40)
                delivery = connection.execute(
                    """
                    SELECT status,signature_verified,headers,blob_uri
                    FROM webhook_delivery WHERE provider_delivery_id='delivery-push-1'
                    """
                ).fetchone()
                self.assertTrue(delivery["signature_verified"])
                self.assertNotIn("x-hub-signature-256", delivery["headers"])
                self.assertTrue(delivery["blob_uri"].startswith("stackgraph-evidence://local/"))

                removed = verified_webhook(
                    {
                        "action": "removed",
                        "installation": {"id": 9876},
                        "repositories_added": [],
                        "repositories_removed": [{"id": 10}],
                    },
                    delivery_id="delivery-repositories-2",
                    event="installation_repositories",
                )
                removal_result = process_github_webhook_connection(
                    connection, removed, evidence_store=evidence_store,
                )
                self.assertEqual(removal_result.status, "PROCESSED")
                self.assertFalse(
                    connection.execute(
                        "SELECT enabled FROM ingest_target WHERE id=%s", (target["id"],)
                    ).fetchone()["enabled"]
                )
                self.assertEqual(
                    connection.execute(
                        "SELECT status FROM ingest_run WHERE id=%s", (first.run_id,)
                    ).fetchone()["status"],
                    "CANCELLED",
                )
                self.assertIsNotNone(
                    connection.execute(
                        "SELECT next_due_at FROM ingest_target WHERE id=%s",
                        (registration.installation_target_id,),
                    ).fetchone()["next_due_at"]
                )
                suspended = verified_webhook(
                    {"action": "suspend", "installation": {"id": 9876}},
                    delivery_id="delivery-installation-suspend-3",
                    event="installation",
                )
                process_github_webhook_connection(
                    connection, suspended, evidence_store=evidence_store,
                )
                self.assertEqual(
                    connection.execute(
                        "SELECT status FROM connector_account WHERE id=%s",
                        (registration.connector_account_id,),
                    ).fetchone()["status"],
                    "DISABLED",
                )
                self.assertFalse(
                    connection.execute(
                        "SELECT enabled FROM ingest_target WHERE id=%s",
                        (registration.installation_target_id,),
                    ).fetchone()["enabled"]
                )
                unsuspended = verified_webhook(
                    {"action": "unsuspend", "installation": {"id": 9876}},
                    delivery_id="delivery-installation-unsuspend-4",
                    event="installation",
                )
                process_github_webhook_connection(
                    connection, unsuspended, evidence_store=evidence_store,
                )
                self.assertEqual(
                    connection.execute(
                        "SELECT status FROM connector_account WHERE id=%s",
                        (registration.connector_account_id,),
                    ).fetchone()["status"],
                    "ACTIVE",
                )
                self.assertTrue(
                    connection.execute(
                        "SELECT enabled FROM ingest_target WHERE id=%s",
                        (registration.installation_target_id,),
                    ).fetchone()["enabled"]
                )
            connection.rollback()


if __name__ == "__main__":
    unittest.main()
