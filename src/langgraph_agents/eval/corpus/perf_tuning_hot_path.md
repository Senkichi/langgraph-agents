# Task: Develop a performance tuning plan for a degraded JVM service

Review the following profiler output and system constraints for a Java 21 Spring Boot service responsible for real-time bid evaluations. Under peak load (approx 15,000 RPS), p99 latency degrades from 45ms to over 800ms, and throughput plateaus.

The service runs on Kubernetes with a hard limit of 4 vCPUs and 8GB RAM per pod. The infrastructure budget is frozen; you cannot increase pod count or request larger instances.

Profiler breakdown during load testing:
- CPU utilization hits 98%.
- 42% of CPU time is spent in `java.util.concurrent.ConcurrentHashMap.computeIfAbsent`.
- 28% of CPU time is spent in `java.lang.String.format` and underlying `StringBuilder` allocations.
- 15% in application logic (`evaluateBid`).
- GC logs show Young Gen allocation rates exceeding 4GB/sec, causing frequent minor GC pauses averaging 80ms, but no Full GCs.

Produce a concrete tuning plan. Identify the measured root causes of the degradation, map them to the specific profiler data, and rank your interventions by expected latency gain.

## Expected response shape (for eval reference only, not shown to pipeline)
- Length: long
- Key concepts:
  - lock contention
  - escape analysis
  - string concatenation
  - object pool
  - thread contention
  - concurrent map
  - TLAB
  - stop-the-world
  - pre-allocation
- Failure modes:
  - recommends horizontal or vertical scaling (violates constraints)
  - suggests tuning garbage collector instead of addressing the high allocation rate root cause
  - misses the lock contention issue inherent in heavily accessed ConcurrentHashMap buckets
  - fails to identify String.format as the primary driver of the high GC allocation rate
