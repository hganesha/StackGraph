from __future__ import annotations

import argparse
import json
import os
from dataclasses import asdict

from stackgraph_data.depsdev import PackageVersionKey
from stackgraph_data.npm_registry import NpmRegistryClient, normalize_version


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Fetch one observed npm package version from its resolved registry"
    )
    parser.add_argument("purl", help="Exact npm package-version purl")
    parser.add_argument("--registry-key", default="npm-public")
    parser.add_argument(
        "--registry-origin", default="https://registry.npmjs.org/"
    )
    parser.add_argument(
        "--visibility",
        choices=("PUBLIC", "PRIVATE", "UNKNOWN"),
        default="PUBLIC",
    )
    parser.add_argument("--tenant-key")
    parser.add_argument("--etag")
    arguments = parser.parse_args()

    client = NpmRegistryClient(
        registry_key=arguments.registry_key,
        registry_origin=arguments.registry_origin,
        visibility=arguments.visibility,
        token=os.environ.get("STACKGRAPH_NPM_REGISTRY_TOKEN"),
    )
    bundle = client.fetch(
        PackageVersionKey.from_purl(arguments.purl), etag=arguments.etag
    )
    if bundle is None:
        print(json.dumps({"status": "UNCHANGED", "etag": arguments.etag}))
        return
    metadata = normalize_version(bundle)
    print(
        json.dumps(
            {
                "status": "CHANGED",
                "metadata": asdict(metadata),
                "raw_observation": bundle.raw_observation(arguments.tenant_key),
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
