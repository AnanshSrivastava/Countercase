-include .env
export DB_PORT

# Requires GNU make (Windows: `winget install GnuWin32.Make` or use Git Bash + make). Each target is
# a thin wrapper, so you can also run the docker compose / uv / pnpm commands directly.
.PHONY: env up up-memory down logs migrate seed-fixtures seed seed-core demo-reset test lint eval

env:
	@test -f .env || cp .env.example .env

up: env
	docker compose up -d --build db api web
	@echo "web: http://localhost:3000  api: http://localhost:8000/health"

up-memory: env
	docker compose --profile memory up -d --build

down:
	docker compose --profile memory down

logs:
	docker compose logs -f

migrate:
	docker compose exec api alembic upgrade head

# Load fixtures/disputes/*.json into the DB (idempotent). For fixture-mode demos.
seed-fixtures:
	docker compose exec api python -m app.core.disputes

# Load the synthetic dispute history into core's tables (for the insights page). Needs `make up`.
# Wipe live demo disputes and re-create 3 collected ones (needs DEMO_TOOLS=1). Leaves seeded history and agent memory alone.
demo-reset:
	docker compose exec api python -m app.core.demo_reset --yes

seed-core:
	cd apps/api && DATABASE_URL=postgresql://countercase:countercase@localhost:$(DB_PORT)/countercase python -m app.agent.seed_core

seed:
	cd apps/api && python -m app.agent.seed_loader --backend hindsight --reset --pace 25 --url http://localhost:8888

# Core tests need Postgres (`make up` first). Uses DB_PORT if set, else 5432.
DB_PORT ?= 5432
test:
	cd apps/api && TEST_DATABASE_URL=postgresql://countercase:countercase@localhost:$(DB_PORT)/countercase_test uv run pytest -q
	cd apps/web && pnpm lint

lint:
	cd apps/api && uv run ruff check . && uv run ruff format --check .
	cd apps/web && pnpm lint

eval:
	python eval/run_eval.py --sellers 40 | tee eval/results.md
