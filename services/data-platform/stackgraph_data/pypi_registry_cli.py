from __future__ import annotations

import argparse
import json
import os
from dataclasses import asdict

from stackgraph_data.depsdev import PackageVersionKey
from stackgraph_data.pypi_registry import PyPIRegistryClient, normalize_version


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch one observed PyPI package version")
    parser.add_argument("purl", help="Exact PyPI package-version purl")
    parser.add_argument("--registry-key", default="pypi-public")
    parser.add_argument("--registry-origin", default="https://pypi.org/")
    parser.add_argument("--visibility", choices=("PUBLIC", "PRIVATE", "UNKNOWN"), default="PUBLIC")
    parser.add_argument("--tenant-key")
    parser.add_argument("--etag")
    arguments = parser.parse_args()
    bundle = PyPIRegistryClient(
        registry_key=arguments.registry_key,
        registry_origin=arguments.registry_origin,
        visibility=arguments.visibility,
        token=os.environ.get("STACKGRAPH_PYPI_REGISTRY_TOKEN"),
    ).fetch(PackageVersionKey.from_purl(arguments.purl), etag=arguments.etag)
    if bundle is None:
        print(json.dumps({"status": "UNCHANGED", "etag": arguments.etag}))
        return
    print(json.dumps({
        "status": "CHANGED",
        "metadata": asdict(normalize_version(bundle)),
        "raw_observation": bundle.raw_observation(arguments.tenant_key),
    }, sort_keys=True))


if __name__ == "__main__":
    main()
