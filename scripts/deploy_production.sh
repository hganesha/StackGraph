#!/usr/bin/env bash
set -Eeuo pipefail

: "${STACKGRAPH_RELEASE_TAG:?STACKGRAPH_RELEASE_TAG is required}"
: "${STACKGRAPH_REGISTRY_OWNER:?STACKGRAPH_REGISTRY_OWNER is required}"

export STACKGRAPH_API_IMAGE="ghcr.io/${STACKGRAPH_REGISTRY_OWNER}/stackgraph-api:${STACKGRAPH_RELEASE_TAG}"
export STACKGRAPH_WEB_IMAGE="ghcr.io/${STACKGRAPH_REGISTRY_OWNER}/stackgraph-web:${STACKGRAPH_RELEASE_TAG}"
export STACKGRAPH_DATA_IMAGE="ghcr.io/${STACKGRAPH_REGISTRY_OWNER}/stackgraph-data:${STACKGRAPH_RELEASE_TAG}"
export STACKGRAPH_DISCOVERY_IMAGE="ghcr.io/${STACKGRAPH_REGISTRY_OWNER}/stackgraph-discovery:${STACKGRAPH_RELEASE_TAG}"
export STACKGRAPH_CONTROL_LOOP_IMAGE="ghcr.io/${STACKGRAPH_REGISTRY_OWNER}/stackgraph-control-loop:${STACKGRAPH_RELEASE_TAG}"
export STACKGRAPH_INTELLIGENCE_IMAGE="ghcr.io/${STACKGRAPH_REGISTRY_OWNER}/stackgraph-intelligence:${STACKGRAPH_RELEASE_TAG}"

compose=(docker compose --env-file .env.production -f compose.yaml -f compose.production.yaml --profile pipeline)
"${compose[@]}" pull
"${compose[@]}" up -d database object-storage
"${compose[@]}" run --rm object-storage-init
"${compose[@]}" run --rm migrate
"${compose[@]}" up -d --remove-orphans
"${compose[@]}" exec -T api python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health/ready', timeout=5)"
