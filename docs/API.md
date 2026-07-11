# API reference

Base URL for local development: `http://localhost:8000`

The generated OpenAPI document at `/openapi.json` is the source of truth. This guide
explains behavior that is easy to miss when reading a schema alone.

## Errors

Errors use `application/problem+json`:

```json
{
  "type": "https://ynaito.dev/problems/ops-evidence/incident-not-found",
  "title": "Incident not found",
  "status": 404,
  "detail": "Incident 00000000-0000-0000-0000-000000000000 was not found.",
  "instance": "/v1/incidents/00000000-0000-0000-0000-000000000000",
  "code": "INCIDENT_NOT_FOUND",
  "errors": []
}
```

Every response includes `X-Request-ID`. A valid caller-supplied value is preserved;
otherwise the API generates one.

## Create an incident

`POST /v1/incidents`

```bash
curl --fail-with-body http://localhost:8000/v1/incidents \
  -H 'Content-Type: application/json' \
  --data '{
    "title": "Reporting API latency",
    "scenarioId": "db-pool-exhaustion",
    "alert": {
      "id": "alert:db-pool-saturation",
      "name": "Database connection pool saturation",
      "source": "synthetic-prometheus",
      "firedAt": "2026-07-12T02:14:03Z",
      "description": "No idle connections and pending borrowers."
    },
    "logs": {
      "format": "text",
      "content": "2026-07-12T02:14:03Z pool active=20 idle=0 pending=8"
    },
    "runbook": {
      "id": "runbook:db-pool-saturation",
      "title": "Database pool saturation",
      "content": "Confirm active equals maximum, idle is zero, and pending is increasing."
    }
  }'
```

Successful responses use `201 Created` and include a `Location` header.

## Start an analysis

`POST /v1/incidents/{incidentId}/analyses`

```bash
curl --fail-with-body -X POST \
  http://localhost:8000/v1/incidents/INCIDENT_ID/analyses \
  -H 'Idempotency-Key: example-analysis-001'
```

The endpoint returns `202 Accepted`, a `Location` header for the analysis, and
`Idempotency-Replayed: false`. Retrying with the same key and incident returns the same
analysis with `Idempotency-Replayed: true`.

The key must contain 8–128 ASCII letters, numbers, `.`, `_`, `:`, or `-`.

## Get an analysis

`GET /v1/analyses/{analysisId}`

```bash
curl --fail-with-body http://localhost:8000/v1/analyses/ANALYSIS_ID
```

Possible states are `queued`, `analyzing`, `completed`, and `failed`. Only a completed
analysis contains `result`; only a failed analysis contains `failure`.

## Health endpoints

- `GET /health/live` checks that the HTTP process can respond.
- `GET /health/ready` executes `SELECT 1` against PostgreSQL and returns `503` when the
  dependency is unavailable.
