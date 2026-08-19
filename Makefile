.PHONY: backend-up backend-down backend-logs backend-test backend-integration-test backend-verify backend-graph-benchmark database-migrate database-seed database-seed-test database-seed-verify database-project database-project-verify depsdev-enqueue depsdev-work depsdev-run depsdev-verify npm-registry-fetch osv-enqueue osv-sync osv-work osv-run osv-verify ai-test ai-prompts-sync repository-scan scanner-enqueue scanner-persist api-surface-extract api-surface-persist

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

database-migrate:
	docker compose run --rm migrate

database-seed: database-migrate
	docker compose run --rm seed

database-seed-test:
	docker compose run --rm --no-deps seed python -m unittest discover -s tests -v

database-seed-verify:
	docker compose exec -T database sh -c 'psql -v ON_ERROR_STOP=1 -U "$$POSTGRES_USER" -d "$$POSTGRES_DB" -f /stackgraph/tests/seed-smoke.sql'

database-project: database-migrate
	docker compose run --rm projection

database-project-verify:
	docker compose exec -T database sh -c 'psql -v ON_ERROR_STOP=1 -U "$$POSTGRES_USER" -d "$$POSTGRES_DB" -f /stackgraph/tests/projection-smoke.sql'

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
	docker compose run --rm scanner-ingest persist "$(SCANNER_RESULT)" --target-id "$(TARGET_ID)" --run-id "$(RUN_ID)"

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
