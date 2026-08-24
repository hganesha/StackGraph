#!/usr/bin/env bash
set -Eeuo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repository_root="$(cd "$script_dir/.." && pwd)"
cd "$repository_root"

build_images=true
seed_database=true
follow_logs=false
env_file=""
startup_timeout="${STACKGRAPH_STARTUP_TIMEOUT_SECONDS:-180}"

usage() {
  cat <<'EOF'
Start the complete local StackGraph application in Docker, including the UI and continuous pipeline.

Usage: ./scripts/start_docker.sh [options]

Options:
  --env-file PATH  Use an explicit Compose environment file.
  --no-build       Reuse existing images instead of rebuilding them.
  --no-seed        Preserve existing data without loading the reference cohort.
  --logs           Follow application and pipeline logs after startup.
  -h, --help       Show this help.

Environment:
  STACKGRAPH_STARTUP_TIMEOUT_SECONDS  Health-wait timeout (default: 180).

The script leaves containers running. Stop them with `make app-down` or
`docker compose down`. Named database data is preserved by default.
EOF
}

while (($#)); do
  case "$1" in
    --env-file)
      if (($# < 2)); then
        echo "error: --env-file requires a path" >&2
        exit 2
      fi
      env_file="$2"
      shift 2
      ;;
    --no-build)
      build_images=false
      shift
      ;;
    --no-seed)
      seed_database=false
      shift
      ;;
    --logs)
      follow_logs=true
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "error: unknown option: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

if ! command -v docker >/dev/null 2>&1; then
  echo "error: Docker is not installed or is not on PATH" >&2
  exit 1
fi
if ! docker compose version >/dev/null 2>&1; then
  echo 'error: Docker Compose v2 is required (docker compose)' >&2
  exit 1
fi
if ! docker info >/dev/null 2>&1; then
  echo "error: the Docker daemon is not running or is not accessible" >&2
  exit 1
fi
if ! [[ "$startup_timeout" =~ ^[1-9][0-9]*$ ]]; then
  echo "error: STACKGRAPH_STARTUP_TIMEOUT_SECONDS must be a positive integer" >&2
  exit 2
fi

compose=(docker compose)
if [[ -n "$env_file" ]]; then
  if [[ ! -f "$env_file" ]]; then
    echo "error: environment file does not exist: $env_file" >&2
    exit 2
  fi
  compose+=(--env-file "$env_file")
fi
compose+=(--profile pipeline)

show_failure_context() {
  local exit_code=$?
  echo >&2
  echo "StackGraph startup failed. Current container state:" >&2
  "${compose[@]}" ps >&2 || true
  echo >&2
  echo "Inspect logs with: docker compose --profile pipeline logs database neo4j api web github-control-loop neo4j-projection-continuous graph-intelligence-continuous embeddings-continuous" >&2
  exit "$exit_code"
}
trap show_failure_context ERR

echo "Validating the Docker Compose configuration..."
"${compose[@]}" config --quiet

if [[ "$build_images" == true ]]; then
  echo "Building application and continuous pipeline images..."
  "${compose[@]}" build migrate seed neo4j-register neo4j-projection ai-prompts api web github-webhook github-control-loop \
    depsdev-continuous osv-continuous neo4j-projection-continuous graph-intelligence-continuous embeddings-continuous intelligence-continuous
fi

up_options=(-d --wait --wait-timeout "$startup_timeout")
if [[ "$build_images" == false ]]; then
  up_options+=(--no-build)
fi

echo "Starting PostgreSQL and the local tenant Neo4j deployment..."
"${compose[@]}" up "${up_options[@]}" database neo4j

echo "Applying database migrations..."
"${compose[@]}" run --rm migrate

echo "Synchronizing the versioned AI prompt catalog..."
"${compose[@]}" run --rm ai-prompts

if [[ "$seed_database" == true ]]; then
  echo "Loading the reference data cohort..."
  "${compose[@]}" run --rm seed
fi

echo "Registering the local tenant graph deployment..."
"${compose[@]}" run --rm neo4j-register

echo "Projecting pending graph changes into Neo4j..."
"${compose[@]}" run --rm neo4j-projection

echo "Starting the API, containerized UI, and continuous pipeline..."
"${compose[@]}" up "${up_options[@]}" api web github-webhook github-control-loop \
  depsdev-continuous osv-continuous neo4j-projection-continuous graph-intelligence-continuous \
  embeddings-continuous intelligence-continuous

web_binding="$("${compose[@]}" port web 3000)"
api_binding="$("${compose[@]}" port api 8000)"
web_port="${web_binding##*:}"
api_port="${api_binding##*:}"

trap - ERR
echo
echo "StackGraph is ready."
echo "  UI:  http://localhost:${web_port}"
echo "  API: http://localhost:${api_port}"
echo
"${compose[@]}" ps database neo4j api web github-webhook github-control-loop \
  depsdev-continuous osv-continuous neo4j-projection-continuous graph-intelligence-continuous \
  embeddings-continuous intelligence-continuous

if [[ "$follow_logs" == true ]]; then
  echo
  echo "Following logs; Ctrl-C stops log streaming but leaves the app running."
  "${compose[@]}" logs --follow database neo4j api web github-webhook github-control-loop \
    depsdev-continuous osv-continuous neo4j-projection-continuous graph-intelligence-continuous \
    embeddings-continuous intelligence-continuous
fi
