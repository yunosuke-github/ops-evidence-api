# Database connection pool saturation

This runbook is synthetic and exists only for the OpsEvidence demo.

## Confirm saturation

Evidence ID: `runbook:db-pool-saturation`

Treat the pool as saturated when all of the following are true:

- `active` equals `maximum` for more than one sampling interval.
- `idle` is zero.
- `pending` is greater than zero and increasing.

Connection checkout timeouts are symptoms of saturation, not proof that the database server is down.

## Check long-running work

Evidence ID: `runbook:long-running-query-check`

Compare the start and completion time of long-running queries with the saturation window. Capture the query plan and lock waits before changing the pool size. Increasing the pool without understanding database capacity can move the bottleneck downstream.

## Recovery signal

Evidence ID: `runbook:pool-recovery`

Recovery requires both pending borrowers returning to zero and idle connections becoming available. A successful query alone is not sufficient.
