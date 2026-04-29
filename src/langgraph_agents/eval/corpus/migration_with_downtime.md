# Task: Design a zero-data-loss database migration plan

Design a schema and database migration plan to move our core `Transactions` dataset from MongoDB to an existing PostgreSQL cluster. 

Current state: 
- MongoDB collection is 4.5TB. 
- Traffic profile: 12,000 reads/sec, 800 writes/sec consistently.
- The business has approved a strict maximum downtime window of exactly 15 minutes for the final cutover.

Your plan must cover the end-to-end process, including data backfill, dual-write windows, data validation/parity checking, the cutover sequence, and an explicit rollback mechanism. Detail the specific tooling or patterns you would use to achieve the synchronization within the downtime budget.

## Expected response shape (for eval reference only, not shown to pipeline)
- Length: long
- Key concepts:
  - change data capture
  - dual-write
  - backfill script
  - logical replication
  - tombstone record
  - data parity
  - cutover window
  - rollback plan
  - idempotent write
  - read repair
- Failure modes:
  - assumes a 4.5TB static dump and restore will execute within the 15-minute downtime window
  - fails to account for updates or deletes happening in MongoDB during the initial backfill phase
  - missing a concrete strategy for verifying data parity before flipping the switch
  - lacks a viable rollback plan if the PostgreSQL database fails immediately after cutover
