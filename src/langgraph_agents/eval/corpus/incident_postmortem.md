# Task: Write an incident postmortem for this outage timeline

Produce a structured incident postmortem based on the following timeline of a recent P1 outage. Include a chronology, the true root cause, contributing factors, and a prioritized list of action items divided into "prevent recurrence" and "improve detection".

Outage Timeline (all times UTC):
- 09:00 - Datadog alerts fire for High P99 Latency on the primary PostgreSQL database.
- 09:05 - On-call engineer scales the PostgreSQL read replicas from 3 to 6. DB CPU utilization drops, but API latency remains high.
- 09:15 - Customer support reports users cannot log in.
- 09:22 - Logs reveal the Node.js API gateway is timing out on all requests to the downstream Auth service and Redis cache.
- 09:30 - Engineer notices CPU on the API gateway pods is pegged at 100%.
- 09:35 - Traffic inspection shows a sudden spike in requests containing highly complex, nested user-agent strings from a newly released third-party integration.
- 09:45 - Engineer adds a WAF rule to block the specific user-agent pattern. CPU on the gateway immediately drops to normal. API latency recovers.
- 10:00 - Incident resolved.

## Expected response shape (for eval reference only, not shown to pipeline)
- Length: long
- Key concepts:
  - event loop lag
  - ReDoS
  - regular expression
  - red herring
  - connection pool
  - single-threaded
  - WAF rule
  - cascade failure
  - MTTR
  - CPU starvation
- Failure modes:
  - names the database latency as the primary root cause rather than a symptom
  - fails to identify regular expression denial of service (ReDoS) or event loop blocking in Node.js
  - action items focus only on database scaling rather than API gateway resilience
  - misses the distinction between the symptom (redis/auth timeouts) and the cause (blocked event loop)
