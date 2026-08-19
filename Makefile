.PHONY: backend-up backend-down backend-logs backend-test backend-integration-test backend-verify database-migrate database-seed database-seed-test database-seed-verify database-project database-project-verify depsdev-enqueue depsdev-work depsdev-run depsdev-verify ai-test ai-prompts-sync

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

ai-test:
	docker compose run --rm --no-deps --entrypoint python ai-prompts -m unittest discover -s /code/tests -v

ai-prompts-sync: database-migrate
	docker compose run --rm ai-prompts
