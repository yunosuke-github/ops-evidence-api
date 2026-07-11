.PHONY: contracts db-down db-up format lint migrate run test test-all test-integration typecheck verify

run:
	uv run uvicorn ops_evidence_api.main:app --reload

db-up:
	docker compose up -d db

db-down:
	docker compose down

migrate:
	uv run alembic upgrade head

contracts:
	uv run python scripts/export_contracts.py

format:
	uv run ruff format .
	uv run ruff check --fix .

lint:
	uv run ruff format --check .
	uv run ruff check .

typecheck:
	uv run mypy src scripts

test:
	uv run pytest -m "not integration"

test-integration:
	OPS_TEST_DATABASE_URL=$${OPS_TEST_DATABASE_URL:-postgresql+psycopg://ops_evidence:ops_evidence@localhost:5432/ops_evidence_test} uv run pytest -m integration

test-all:
	OPS_TEST_DATABASE_URL=$${OPS_TEST_DATABASE_URL:-postgresql+psycopg://ops_evidence:ops_evidence@localhost:5432/ops_evidence_test} uv run pytest --cov=ops_evidence_api --cov-report=term-missing --cov-report=xml --cov-fail-under=85

verify: lint typecheck test-all
