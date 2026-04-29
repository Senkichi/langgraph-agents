# Task: Design a caching architecture for a high-skew workload

Design a caching and consistency strategy for a new Golang-based user profile service. 

Workload constraints:
- 75,000 read QPS, 500 write QPS.
- Extreme hot-key skew: 1% of user profiles (celebrities) receive 90% of the read traffic.
- Maximum acceptable data staleness is 5 seconds.
- Hard infrastructure constraint: Due to a security compliance freeze, you cannot deploy or use any shared distributed cache clusters (no Redis, Memcached, or Hazelcast). You only have the memory of the application pods (limited to 2GB cache overhead per pod).

Detail your chosen coherency strategy, the exact cache topology, and explicit mechanisms to defend against the pitfalls invited by your design.

## Expected response shape (for eval reference only, not shown to pipeline)
- Length: long
- Key concepts:
  - thundering herd
  - local cache
  - cache stampede
  - singleflight
  - jitter
  - cache invalidation
  - background refresh
  - eviction policy
  - memory limit
  - stale-while-revalidate
- Failure modes:
  - recommends a distributed cache like Redis despite the explicit negative constraint
  - fails to implement singleflight or similar request coalescing to prevent thundering herds on hot key expiration
  - ignores the 2GB memory limit and proposes unbounded in-memory maps
  - suggests a write-through strategy that requires broadcasting invalidations, which is unworkable without external infra
