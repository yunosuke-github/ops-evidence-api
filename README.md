# OpsEvidence API

OpsEvidence turns synthetic incident evidence—alerts, logs, and runbooks—into a
structured investigation result whose claims link back to source evidence. This
repository focuses on the API and reliability boundary: validation, idempotency,
PostgreSQL persistence, and a transactional outbox.

> Status: early alpha. The bundled fake runner is deterministic development tooling,
> not an AI model and not a production worker.

## What this demonstrates

- FastAPI request and response contracts with strict validation.
- `202 Accepted` asynchronous analysis creation with `Idempotency-Key` support.
- Incident, analysis, and outbox records committed in reliable transaction boundaries.
- RFC 9457-style `application/problem+json` errors.
- Versioned OpenAPI, result, and cross-language event contracts.
- A synthetic incident fixture with evidence-reference validation.
- A replaceable fake consumer that will later be implemented by Spring Boot and Pulsar.

## Quick start

### Requirements

- Docker with Docker Compose v2
- Optional for host development: Python 3.12+ and [uv](https://docs.astral.sh/uv/)

Start PostgreSQL and the API:

```bash
docker compose up --build -d
docker compose ps
```

When both services are healthy, submit the bundled database-pool scenario:

```bash
docker compose exec api python scripts/post_fixture.py \
  --base-url http://localhost:8000
```

The command exits successfully after the analysis reaches `completed` and prints a
result containing ranked hypotheses, evidence references, gaps, and next checks.

Useful endpoints:

- Swagger UI: <http://localhost:8080/docs>
- OpenAPI: <http://localhost:8080/openapi.json>
- Readiness: <http://localhost:8080/health/ready>

Docker publishes port `8080` by default because port `8000` is commonly used by local
API processes. Set `OPS_API_PORT` in `.env` to change the host port; the container still
listens on `8000`.

Stop the stack with `docker compose down`. Add `--volumes` if you also want to remove
local database data.

## Local development

```bash
uv sync
cp .env.example .env
docker compose up -d db
uv run alembic upgrade head
uv run uvicorn ops_evidence_api.main:app --reload
```

In another terminal:

```bash
uv run python scripts/post_fixture.py
```

No model API key is required. `OPS_FAKE_RUNNER_ENABLED=true` makes a local relay read
`analysis.requested` events from the outbox and load the validated result bundled in
`fixtures/`. Set it to `false` when testing the API/worker boundary without local
completion.

## Request flow

```mermaid
flowchart LR
    Client["Client"] -->|"POST /v1/incidents"| API["FastAPI"]
    Client -->|"POST .../analyses + Idempotency-Key"| API
    API -->|"one transaction"| DB["PostgreSQL"]
    DB --> Analysis["queued analysis"]
    DB --> Outbox["analysis.requested outbox event"]
    Outbox --> Fake["Development-only fake relay"]
    Fake -->|"validated fixture result"| DB
    Client -->|"GET /v1/analyses/{id}"| API
```

The fake relay is deliberately an adapter. The application service depends on storage
ports, not SQLAlchemy or a concrete message broker. A later repository will replace the
adapter with a Spring Boot consumer over Apache Pulsar while preserving the contracts in
`contracts/events/v1/`.

## API summary

| Method | Path | Result |
| --- | --- | --- |
| `POST` | `/v1/incidents` | Creates validated incident evidence; returns `201` |
| `GET` | `/v1/incidents/{incidentId}` | Returns incident metadata |
| `POST` | `/v1/incidents/{incidentId}/analyses` | Requires `Idempotency-Key`; returns `202` |
| `GET` | `/v1/analyses/{analysisId}` | Returns queued, analyzing, completed, or failed state |
| `GET` | `/health/live` | Process liveness |
| `GET` | `/health/ready` | PostgreSQL readiness |

See [API.md](docs/API.md) for working requests, responses, and error behavior.

## Project structure

```text
.
├── contracts/                 # Generated, reviewed HTTP and event contracts
├── fixtures/                  # Synthetic incidents and expected analysis results
├── migrations/                # Alembic database migrations
├── scripts/                   # Contract export and end-to-end demo commands
├── src/ops_evidence_api/
│   ├── api/                   # HTTP routes, dependencies, middleware, problem responses
│   ├── application/           # Use cases, domain-shaped models, and storage ports
│   ├── contracts/             # Pydantic source of truth for public schemas
│   └── infrastructure/        # PostgreSQL and development fake-runner adapters
├── tests/                     # Unit, contract, fixture, and PostgreSQL integration tests
├── compose.yaml               # Local API and PostgreSQL stack
└── pyproject.toml             # Dependencies and quality-tool configuration
```

## Design decisions

### Transactional outbox

Creating an analysis also creates `analysis.requested` in the same database transaction.
The API therefore cannot acknowledge an analysis whose publication intent was lost. The
development relay marks the outbox row published only after the deterministic result is
stored.

### Idempotent creation

`Idempotency-Key` is required for analysis creation. Repeating the same logical request
returns the original analysis and `Idempotency-Replayed: true`. Reusing the key for a
different incident returns `409 IDEMPOTENCY_KEY_REUSED`.

### Evidence scores, not model confidence

Results expose an `evidenceScore` constrained to 0–100. It represents deterministic
evidence coverage and contradiction signals; it is not presented as a probability or as
the model's confidence.

## Quality checks

```bash
make lint
make typecheck
make test
```

PostgreSQL integration tests use the test database created by Docker Compose:

```bash
docker compose up -d db
OPS_DATABASE_URL=postgresql+psycopg://ops_evidence:ops_evidence@localhost:5432/ops_evidence_test \
  uv run alembic upgrade head
make test-integration
```

Run the same complete check as CI:

```bash
make verify
```

`scripts/export_contracts.py` regenerates checked-in schemas. Contract snapshot tests fail
when generated and committed documents differ.

## Security and scope

- All bundled evidence is synthetic.
- The API currently has no end-user authentication; bind it only to trusted development
  environments until authentication and abuse controls are implemented.
- Request bodies have explicit size limits.
- Raw logs and prompts are not emitted as telemetry.
- The application never executes generated shell commands or remediation actions.

See [SECURITY.md](SECURITY.md) for reporting guidance and [ARCHITECTURE.md](docs/ARCHITECTURE.md)
for boundaries and failure behavior.

## License

MIT. See [LICENSE](LICENSE).
