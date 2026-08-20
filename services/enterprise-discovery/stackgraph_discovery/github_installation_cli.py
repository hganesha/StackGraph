from __future__ import annotations

import argparse
import json
import os

from .github_client import GitHubClient
from .github_app_auth import resolve_runtime_credential
from .github_installation import InstallationRepositoryDiscovery
from .github_installation_store import (
    as_json,
    connector_binding,
    reconcile_installation,
    register_installation,
    revoke_installation,
)


def _database_url() -> str:
    value = os.environ.get("STACKGRAPH_DATABASE_URL")
    if not value:
        raise ValueError("STACKGRAPH_DATABASE_URL is required")
    return value


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Register and reconcile tenant-scoped GitHub App installations"
    )
    commands = parser.add_subparsers(dest="command", required=True)

    register = commands.add_parser("register")
    register.add_argument("--tenant-key", required=True)
    register.add_argument("--installation-id", required=True)
    register.add_argument("--credential-reference", required=True)
    register.add_argument(
        "--permission",
        action="append",
        default=[],
        help="GitHub App permission in name:read/name:write form; repeat as needed",
    )

    reconcile = commands.add_parser("reconcile")
    reconcile.add_argument("--tenant-key", required=True)
    reconcile.add_argument("--installation-id", required=True)
    reconcile.add_argument("--api-version", default="2026-03-10")
    reconcile.add_argument("--max-pages", type=int, default=100)

    revoke = commands.add_parser("revoke")
    revoke.add_argument("--tenant-key", required=True)
    revoke.add_argument("--installation-id", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    database_url = _database_url()
    if args.command == "register":
        result = register_installation(
            database_url,
            tenant_key=args.tenant_key,
            installation_id=args.installation_id,
            credential_reference=args.credential_reference,
            permissions=args.permission,
        )
    elif args.command == "reconcile":
        binding = connector_binding(
            database_url,
            tenant_key=args.tenant_key,
            installation_id=args.installation_id,
        )
        token = resolve_runtime_credential(
            binding.credential_reference, installation_id=args.installation_id,
        )
        snapshot = InstallationRepositoryDiscovery(
            GitHubClient(token=token, api_version=args.api_version),
            max_pages=args.max_pages,
        ).discover(args.installation_id)
        result = reconcile_installation(
            database_url,
            tenant_key=args.tenant_key,
            snapshot=snapshot,
        )
    else:
        result = revoke_installation(
            database_url,
            tenant_key=args.tenant_key,
            installation_id=args.installation_id,
        )
    print(json.dumps(as_json(result), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
