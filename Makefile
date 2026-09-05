.PHONY: app-up app-down app-logs backend-up backend-down backend-logs backend-test backend-integration-test backend-verify backend-graph-benchmark phase2-api-benchmark database-migrate database-seed database-seed-test database-seed-verify database-project database-project-verify database-graph-intelligence-verify neo4j-register neo4j-project neo4j-verify neo4j-rebuild graph-intelligence-test graph-embeddings-benchmark oss-catalog-import depsdev-enqueue depsdev-work depsdev-run depsdev-verify npm-registry-fetch osv-enqueue osv-sync osv-work osv-run osv-verify ai-test ai-prompts-sync capabilities-sync capabilities-analyze intelligence-run intelligence-requeue intelligence-work github-installation-register github-installation-reconcile github-installation-revoke github-webhook-up github-webhook-down github-pipeline-work pipeline-up pipeline-down pipeline-logs repository-acquire repository-scan scanner-enqueue scanner-persist api-surface-extract api-surface-persist pilot-100 pilot-live operations-snapshot recovery-drill fresh-integration production-config production-up production-down production-alert-test

app-up:
	./scripts/start_docker.sh

app-down:
	docker compose --profile pipeline down

app-logs:
	docker compose --profile pipeline logs -f database neo4j api web mcp-server github-webhook github-control-loop \
		depsdev-continuous osv-continuous neo4j-projection-continuous graph-intelligence-continuous embeddings-continuous intelligence-continuous simulation-continuous

PRODUCTION_COMPOSE = docker compose --env-file .env.production -f compose.yaml -f compose.production.yaml --profile pipeline

production-config:
	$(PRODUCTION_COMPOSE) config --quiet

production-up: production-config
	$(PRODUCTION_COMPOSE) up -d database object-storage
	$(PRODUCTION_COMPOSE) run --rm object-storage-init
	$(PRODUCTION_COMPOSE) run --rm migrate
	$(PRODUCTION_COMPOSE) up -d --remove-orphans

production-down:
	$(PRODUCTION_COMPOSE) down

production-alert-test:
	$(PRODUCTION_COMPOSE) exec -T alertmanager amtool alert add StackGraphPagingTest owner=platform-on-call severity=critical

backend-up:
	docker compose up --build -d database api

backend-down:
	docker compose down

backend-logs:
	docker compose logs -f database api

backend-test:
	docker compose run --rm --no-deps api python -m pytest

backend-integration-test:
	docker compose run --rm -e STACKGRAPH_TEST_DATABASE_URL=postgresql://stackgraph_app:stackgraph_app@database:5432/stackgraph api python -m pytest -q tests/test_database_integration.py

backend-verify:
	docker compose exec -T database sh -c 'psql -v ON_ERROR_STOP=1 -U "$$POSTGRES_USER" -d "$$POSTGRES_DB" -f /stackgraph/tests/smoke.sql'

backend-graph-benchmark:
	test -n "$(GRAPH_CENTER_ID)"
	python3 scripts/benchmark_graph_api.py "$(GRAPH_CENTER_ID)" --requests "$${GRAPH_REQUESTS:-50}" $${GRAPH_BENCHMARK_ARGS:-}

phase2-api-benchmark:
	@test -n "$(PACKAGE_ID)" || (echo "PACKAGE_ID is required" >&2; exit 2)
	python3 scripts/benchmark_phase2_api.py "$(PACKAGE_ID)" --requests "$${PHASE2_BENCHMARK_REQUESTS:-10000}" --concurrency "$${PHASE2_BENCHMARK_CONCURRENCY:-20}" $${PHASE2_BENCHMARK_ARGS:-}

database-migrate:
	docker compose run --rm migrate

database-seed: database-migrate
	docker compose run --rm seed

database-seed-test:
	docker compose run --rm --no-deps seed python -m unittest discover -s tests -v

database-seed-verify:
	docker compose exec -T database sh -c 'psql -v ON_ERROR_STOP=1 -U "$$POSTGRES_USER" -d "$$POSTGRES_DB" -f /stackgraph/tests/seed-smoke.sql'

database-project: neo4j-project

neo4j-register: database-migrate
	docker compose up -d --wait database neo4j
	docker compose run --rm neo4j-register

neo4j-project: neo4j-register
	docker compose run --rm neo4j-projection

neo4j-rebuild: neo4j-register
	@test -n "$(TENANT_ID)" || (echo "TENANT_ID is required" >&2; exit 2)
	@test -n "$(CANDIDATE_DATABASE)" || (echo "CANDIDATE_DATABASE is required" >&2; exit 2)
	docker compose run --rm neo4j-projection rebuild --tenant-id "$(TENANT_ID)" --candidate-database "$(CANDIDATE_DATABASE)"

graph-embeddings-benchmark: neo4j-register
	@test -n "$(TENANT_ID)" || (echo "TENANT_ID is required" >&2; exit 2)
	docker compose run --rm --entrypoint python neo4j-projection -m stackgraph_data.benchmark_graph_embeddings --tenant-id "$(TENANT_ID)" --iterations "$${ITERATIONS:-20}" --synthetic-vector-count "$${SYNTHETIC_VECTOR_COUNT:-0}" --synthetic-vector-dimensions "$${SYNTHETIC_VECTOR_DIMENSIONS:-128}"

database-project-verify:
	docker compose exec -T database sh -c 'psql -v ON_ERROR_STOP=1 -U "$$POSTGRES_USER" -d "$$POSTGRES_DB" -f /stackgraph/tests/neo4j-projection-smoke.sql'
	docker compose exec -T database sh -c 'psql -v ON_ERROR_STOP=1 -U "$$POSTGRES_USER" -d "$$POSTGRES_DB" -c "SELECT tenant_id,deployment_state,desired_outbox_id,projected_outbox_id FROM tenant_graph_deployment"'
	docker compose exec -T neo4j cypher-shell -u neo4j -p "$${STACKGRAPH_NEO4J_PASSWORD:-stackgraph_neo4j}" 'MATCH (entity:Entity) OPTIONAL MATCH ()-[relationship:Relationship]->() RETURN count(DISTINCT entity) AS graph_entities,count(DISTINCT relationship) AS graph_relationships'

database-graph-intelligence-verify:
	docker compose exec -T database sh -c 'psql -v ON_ERROR_STOP=1 -U "$$POSTGRES_USER" -d "$$POSTGRES_DB" -f /stackgraph/tests/graph-analysis-control-plane-smoke.sql'
	docker compose exec -T database sh -c 'psql -v ON_ERROR_STOP=1 -U "$$POSTGRES_USER" -d "$$POSTGRES_DB" -f /stackgraph/tests/embedding-control-plane-smoke.sql'

graph-intelligence-test:
	docker compose --profile tools build neo4j-projection graph-intelligence
	docker compose --profile tools run --rm --no-deps --entrypoint python neo4j-projection -m unittest tests.test_neo4j_project -v
	docker compose --profile tools run --rm --no-deps --entrypoint python graph-intelligence -m unittest discover -s tests -v

neo4j-verify: database-project-verify

oss-catalog-import: database-migrate
	docker compose run --rm oss-catalog $(OSS_CATALOG_ARGS)

depsdev-enqueue:
	@test -n "$(PURL)" || (echo "PURL is required" >&2; exit 2)
	docker compose run --rm depsdev enqueue "$(PURL)"

depsdev-work:
	docker compose run --rm depsdev work

depsdev-run:
	@test -n "$(PURL)" || (echo "PURL is required" >&2; exit 2)
	docker compose run --rm depsdev run "$(PURL)"

depsdev-verify:
	docker compose exec -T database sh -c 'psql -v ON_ERROR_STOP=1 -U "$$POSTGRES_USER" -d "$$POSTGRES_DB" -f /stackgraph/tests/depsdev-smoke.sql'

npm-registry-fetch:
	@test -n "$(PURL)" || (echo "PURL is required" >&2; exit 2)
	docker compose run --rm npm-registry "$(PURL)" $(NPM_REGISTRY_ARGS)
osv-enqueue:
	@test -n "$(PURL)" || (echo "PURL is required" >&2; exit 2)
	docker compose run --rm osv enqueue "$(PURL)"

osv-sync:
	docker compose run --rm osv sync

osv-work:
	docker compose run --rm osv work

osv-run:
	@test -n "$(PURL)" || (echo "PURL is required" >&2; exit 2)
	docker compose run --rm osv run "$(PURL)"

osv-verify:
	docker compose exec -T database sh -c 'psql -v ON_ERROR_STOP=1 -U "$$POSTGRES_USER" -d "$$POSTGRES_DB" -f /stackgraph/tests/osv-smoke.sql'
ai-test:
	docker compose run --rm --no-deps --entrypoint python ai-prompts -m unittest discover -s /code/tests -v

ai-prompts-sync: database-migrate
	docker compose run --rm ai-prompts

capabilities-sync: database-migrate
	docker compose run --rm --entrypoint python ai-prompts -m stackgraph_ai.sync_capabilities --catalog-dir /code/capabilities

capabilities-analyze: capabilities-sync
	@test -n "$(TENANT_ID)" || (echo "TENANT_ID is required" >&2; exit 2)
	@test -n "$(REPOSITORY_ID)" || (echo "REPOSITORY_ID is required" >&2; exit 2)
	docker compose run --rm capability-intelligence --tenant-id "$(TENANT_ID)" --repository-id "$(REPOSITORY_ID)" --catalog-dir /code/capabilities $(if $(AI_UNMAPPED),--ai-unmapped --ai-route "$${AI_ROUTE:-default}",)

intelligence-run: database-migrate
	@test -n "$(TENANT_ID)" || (echo "TENANT_ID is required" >&2; exit 2)
	@test -n "$(REPOSITORY_ID)" || (echo "REPOSITORY_ID is required" >&2; exit 2)
	docker compose run --rm modernization-intelligence run --tenant-id "$(TENANT_ID)" --repository-id "$(REPOSITORY_ID)" $(if $(AI_UNMAPPED),--ai-unmapped --ai-route "$${AI_ROUTE:-default}",)

intelligence-work: database-migrate
	docker compose run --rm modernization-intelligence work --ai-unmapped --max-jobs "$${MAX_JOBS:-10}"

intelligence-requeue: database-migrate
	@test -n "$(TENANT_ID)" || (echo "TENANT_ID is required" >&2; exit 2)
	@test -n "$(REPOSITORY_ID)" || (echo "REPOSITORY_ID is required" >&2; exit 2)
	docker compose run --rm modernization-intelligence requeue --tenant-id "$(TENANT_ID)" --repository-id "$(REPOSITORY_ID)"

github-installation-register: database-migrate
	@test -n "$(TENANT_KEY)" || (echo "TENANT_KEY is required" >&2; exit 2)
	@test -n "$(INSTALLATION_ID)" || (echo "INSTALLATION_ID is required" >&2; exit 2)
	docker compose run --rm github-lifecycle register --tenant-key "$(TENANT_KEY)" --installation-id "$(INSTALLATION_ID)" --credential-reference "$${CREDENTIAL_REFERENCE:-github-app://installation/$(INSTALLATION_ID)}" --permission contents:read --permission metadata:read

github-installation-reconcile: database-migrate
	@test -n "$(TENANT_KEY)" || (echo "TENANT_KEY is required" >&2; exit 2)
	@test -n "$(INSTALLATION_ID)" || (echo "INSTALLATION_ID is required" >&2; exit 2)
	@test -n "$$GITHUB_INSTALLATION_TOKEN" || { test -n "$$GITHUB_APP_ID" && { test -n "$$GITHUB_APP_PRIVATE_KEY" || test -n "$$GITHUB_APP_PRIVATE_KEY_FILE"; }; } || (echo "set GitHub App credentials or GITHUB_INSTALLATION_TOKEN" >&2; exit 2)
	docker compose run --rm github-lifecycle reconcile --tenant-key "$(TENANT_KEY)" --installation-id "$(INSTALLATION_ID)"

github-installation-revoke: database-migrate
	@test -n "$(TENANT_KEY)" || (echo "TENANT_KEY is required" >&2; exit 2)
	@test -n "$(INSTALLATION_ID)" || (echo "INSTALLATION_ID is required" >&2; exit 2)
	docker compose run --rm github-lifecycle revoke --tenant-key "$(TENANT_KEY)" --installation-id "$(INSTALLATION_ID)"

github-webhook-up:
	@test -n "$$GITHUB_WEBHOOK_SECRET" || (echo "GITHUB_WEBHOOK_SECRET is required" >&2; exit 2)
	docker compose --profile github up --build -d github-webhook

github-webhook-down:
	docker compose --profile github stop github-webhook

github-pipeline-work: database-migrate
	docker compose run --rm github-control-loop work

pipeline-up: database-migrate
	@test -n "$$GITHUB_WEBHOOK_SECRET" || (echo "GITHUB_WEBHOOK_SECRET is required" >&2; exit 2)
	@test -n "$$GITHUB_INSTALLATION_TOKEN" || { test -n "$$GITHUB_APP_ID" && { test -n "$$GITHUB_APP_PRIVATE_KEY" || test -n "$$GITHUB_APP_PRIVATE_KEY_FILE"; }; } || (echo "set GitHub App credentials or GITHUB_INSTALLATION_TOKEN" >&2; exit 2)
	docker compose --profile pipeline up --build -d neo4j github-webhook github-control-loop depsdev-continuous osv-continuous neo4j-projection-continuous graph-intelligence-continuous embeddings-continuous intelligence-continuous simulation-continuous

pipeline-down:
	docker compose --profile pipeline stop github-webhook github-control-loop depsdev-continuous osv-continuous neo4j-projection-continuous graph-intelligence-continuous embeddings-continuous intelligence-continuous simulation-continuous

pipeline-logs:
	docker compose --profile pipeline logs -f neo4j github-webhook github-control-loop depsdev-continuous osv-continuous neo4j-projection-continuous graph-intelligence-continuous embeddings-continuous intelligence-continuous simulation-continuous

pilot-100:
	mkdir -p artifacts/pilot
	docker compose build -q repository-scanner
	docker compose run --rm --no-deps -v "$(CURDIR)/artifacts/pilot:/artifacts" --entrypoint python repository-scanner -m stackgraph_discovery.pilot --repositories "$${PILOT_REPOSITORIES:-100}" --output /artifacts/pilot-100-repositories.json

pilot-live:
	@test -n "$(TENANT_KEY)" || (echo "TENANT_KEY is required" >&2; exit 2)
	mkdir -p artifacts/pilot
	docker compose build -q seed
	docker compose run --rm --no-deps \
	  -e STACKGRAPH_PILOT_BEARER_TOKEN \
	  -v "$(CURDIR)/artifacts/pilot:/artifacts" \
	  seed python -m stackgraph_data.pilot_readiness \
	  --tenant-key "$(TENANT_KEY)" \
	  --api-base-url "$${STACKGRAPH_PILOT_API_BASE_URL:-http://api:8000}" \
	  --output /artifacts/pilot-live-$$(date -u +%Y%m%d%H%M%S).json

operations-snapshot:
	docker compose run --rm --no-deps seed python -m stackgraph_data.operations

recovery-drill:
	./scripts/recovery_drill.sh

fresh-integration:
	./scripts/fresh_integration_matrix.sh

repository-acquire:
	@test -n "$(REPOSITORY)" || (echo "REPOSITORY is required (owner/name)" >&2; exit 2)
	@test -n "$(TENANT_KEY)" || (echo "TENANT_KEY is required" >&2; exit 2)
	docker compose run --rm repository-acquirer "$(REPOSITORY)" --tenant-key "$(TENANT_KEY)" --output-dir /snapshots --evidence-store-root /evidence $(if $(INSTALLATION_ID),--installation-id "$(INSTALLATION_ID)",) $(if $(PREVIOUS_REVISION),--previous-revision "$(PREVIOUS_REVISION)",)

repository-scan:
	@test -n "$(SCANNER_REQUEST)" || (echo "SCANNER_REQUEST is required (container path under /snapshots)" >&2; exit 2)
	@test -n "$(SCANNER_RESULT)" || (echo "SCANNER_RESULT is required (container path under /snapshots)" >&2; exit 2)
	docker compose run --rm repository-scanner "$(SCANNER_REQUEST)" --output "$(SCANNER_RESULT)"

scanner-enqueue: database-migrate
	@test -n "$(TENANT_KEY)" || (echo "TENANT_KEY is required" >&2; exit 2)
	@test -n "$(REPOSITORY_KEY)" || (echo "REPOSITORY_KEY is required" >&2; exit 2)
	@test -n "$(SOURCE_REVISION)" || (echo "SOURCE_REVISION is required" >&2; exit 2)
	docker compose run --rm scanner-ingest enqueue --tenant-key "$(TENANT_KEY)" --repository-key "$(REPOSITORY_KEY)" --source-revision "$(SOURCE_REVISION)" --priority "$${PRIORITY:-HOT}"

scanner-persist: database-migrate
	@test -n "$(SCANNER_RESULT)" || (echo "SCANNER_RESULT is required (container path under /snapshots)" >&2; exit 2)
	@test -n "$(TARGET_ID)" || (echo "TARGET_ID is required" >&2; exit 2)
	@test -n "$(RUN_ID)" || (echo "RUN_ID is required" >&2; exit 2)
	docker compose run --rm scanner-ingest persist "$(SCANNER_RESULT)" --target-id "$(TARGET_ID)" --run-id "$(RUN_ID)" $(if $(RAW_OBSERVATION),--raw-observation "$(RAW_OBSERVATION)",)

api-surface-extract:
	@test -n "$(ARTIFACT_ROOT)" || (echo "ARTIFACT_ROOT is required (container path under /snapshots)" >&2; exit 2)
	@test -n "$(ECOSYSTEM)" || (echo "ECOSYSTEM is required (npm or pypi)" >&2; exit 2)
	@test -n "$(PACKAGE_PURL)" || (echo "PACKAGE_PURL is required" >&2; exit 2)
	@test -n "$(ARTIFACT_CHECKSUM)" || (echo "ARTIFACT_CHECKSUM is required" >&2; exit 2)
	@test -n "$(API_SURFACE_RESULT)" || (echo "API_SURFACE_RESULT is required (container path under /snapshots)" >&2; exit 2)
	docker compose run --rm --entrypoint python repository-scanner -m stackgraph_discovery.api_surface "$(ARTIFACT_ROOT)" --ecosystem "$(ECOSYSTEM)" --package-purl "$(PACKAGE_PURL)" --artifact-checksum "$(ARTIFACT_CHECKSUM)" --output "$(API_SURFACE_RESULT)"

api-surface-persist: database-migrate
	@test -n "$(API_SURFACE_RESULT)" || (echo "API_SURFACE_RESULT is required (container path under /snapshots)" >&2; exit 2)
	docker compose run --rm scanner-ingest api-surface "$(API_SURFACE_RESULT)" $(if $(TENANT_ID),--tenant-id "$(TENANT_ID)",)
