# Architecture

## Boundaries

The repository uses four explicit layers:

1. `contracts` is the shared, dependency-light source of externally visible HTTP, result,
   and event shapes.
2. `api` translates HTTP requests into application commands and maps failures to problem
   responses.
3. `application` owns use cases and ports. It has no SQLAlchemy or FastAPI imports.
4. `infrastructure` implements PostgreSQL persistence and the local fake-runner adapter.

API and infrastructure depend on the application layer. The application layer knows only
protocols, domain-shaped data, and versioned contract models; it has no FastAPI, SQLAlchemy,
or broker imports.

## Transaction flow

Starting an analysis performs the following operations in one PostgreSQL transaction:

1. Verify that the incident exists.
2. Resolve or reserve the idempotency key.
3. Insert the queued analysis.
4. Insert the versioned `analysis.requested` outbox event.

The unique database constraint is authoritative for concurrent idempotency requests. Code
handles the race by reading the committed winner after a constraint conflict.

## Development fake runner

The fake relay is enabled only by configuration. It claims one pending requested event,
marks its analysis `analyzing`, validates a bundled result against `AnalysisResult`, and
atomically stores the terminal result before marking the outbox row published.

The adapter is intentionally single-process. It makes local development deterministic;
it is not presented as a durable broker. The production path will publish the same event
contract to Apache Pulsar and receive versioned progress or terminal events from a Spring
Boot worker.

## Failure behavior

- Expected application failures become stable problem codes.
- Request validation failures include field-level reasons without echoing submitted values.
- The fake relay retries unexpected fixture I/O failures with bounded exponential delays.
- Permanent fixture or contract errors fail the analysis without consuming all retries.
- Unexpected server exceptions are logged with a request ID; clients receive a generic
  response without stack traces or database details.

## Extension points

- Implement the event publisher without changing `IncidentService`.
- Add the authenticated internal input endpoint for the worker.
- Consume `analysis.progressed`, `analysis.completed`, and `analysis.failed` using the
  versioned JSON Schemas.
- Add SSE after progress events exist; polling is sufficient for this initial vertical slice.
