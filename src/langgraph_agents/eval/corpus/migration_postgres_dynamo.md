# Task: Plan a migration from PostgreSQL to DynamoDB for a high-write workload

A mid-sized SaaS app currently stores all data in a PostgreSQL cluster. The
event ingestion table has grown past 2 billion rows and writes are becoming
the operational bottleneck — lock contention and vacuum pressure dominate
oncall pages. Reads on that table are almost entirely keyed by
``(tenant_id, event_timestamp)`` lookups and range scans over a short window.

Produce a migration plan from PostgreSQL to DynamoDB for the event-ingestion
table only. Other tables stay on Postgres. Cover: schema design (partition
key, sort key, secondary indexes), dual-write cutover strategy, backfill,
consistency guarantees given the ingestion pattern, rollback plan, and
observability. Flag any assumptions you had to make.

## Expected response shape (for eval reference only, not shown to pipeline)
- Length: long
- Key concepts:
  - partition key
  - sort key
  - composite key
  - GSI
  - LSI
  - dual-write
  - backfill
  - consistency
  - rollback
  - capacity
  - on-demand
  - hot partition
  - observability
  - cloudwatch
  - canary
  - cutover
- Failure modes:
  - no rollback plan
  - picks a partition key that creates a hot partition under the workload
  - ignores tenant_id in the partition strategy
  - hand-waves backfill for 2B rows
  - no flagged assumptions
